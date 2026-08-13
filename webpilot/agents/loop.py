from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Literal

from webpilot.agents.actor import BrowserActor
from webpilot.browser.observation import BrowserObservation, ObservationEngine
from webpilot.browser.locator import ElementSignature, SelfHealingLocator
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.safety.gate import ApprovalRequiredError


RunStatus = Literal[
    "completed",
    "max_steps_reached",
    "actor_error",
    "tool_error",
    "cancelled",
]


@dataclass(frozen=True)
class ActionRecord:
    step: int
    tool_name: str
    arguments: dict[str, Any]
    duration_ms: int
    outcome: dict[str, Any] | None = None
    error: str | None = None
    semantic_target: dict[str, Any] | None = None
    healing: dict[str, Any] | None = None

    def history_item(self) -> dict[str, Any]:
        """Return compact context for the next Actor call."""
        item: dict[str, Any] = {
            "step": self.step,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "duration_ms": self.duration_ms,
        }
        if self.outcome is not None:
            item["outcome"] = {
                key: value
                for key, value in self.outcome.items()
                if key in {"ok", "tool", "ref", "url"}
            }
        if self.error is not None:
            item["error"] = self.error
        return item


@dataclass(frozen=True)
class AgentRunResult:
    status: RunStatus
    goal: str
    target_url: str
    final_observation: BrowserObservation
    action_history: list[ActionRecord]
    duration_ms: int
    message: str = ""
    error: str | None = None

    @property
    def tool_calls(self) -> int:
        return len(self.action_history)

    @property
    def steps(self) -> int:
        return len(self.action_history)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "goal": self.goal,
            "target_url": self.target_url,
            "final_observation": self.final_observation.model_dump(),
            "action_history": [
                {
                    "step": record.step,
                    "tool_name": record.tool_name,
                    "arguments": record.arguments,
                    "duration_ms": record.duration_ms,
                    "outcome": record.outcome,
                    "error": record.error,
                    "semantic_target": record.semantic_target,
                    "healing": record.healing,
                }
                for record in self.action_history
            ],
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "error": self.error,
        }


class SingleBrowserAgent:
    """Day 3's minimal Observe -> Think -> Act -> Observe control loop.

    This intentionally has no Planner, Verifier, retry policy, recovery, or
    persistent state. Those modules begin after the Day 3 single-agent baseline
    is measured.
    """

    def __init__(
        self,
        *,
        actor: BrowserActor,
        observation_engine: ObservationEngine,
        tools: BrowserToolExecutor,
        max_steps: int = 6,
        cancellation_check: Callable[[], bool] | None = None,
        self_healing_locator: SelfHealingLocator | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive.")
        self.actor = actor
        self.observation_engine = observation_engine
        self.tools = tools
        self.max_steps = max_steps
        self.cancellation_check = cancellation_check
        self.self_healing_locator = self_healing_locator

    async def run(
        self,
        *,
        goal: str,
        target_url: str,
        completion_check: Callable[[BrowserObservation], bool] | None = None,
    ) -> AgentRunResult:
        if not goal.strip():
            raise ValueError("goal must not be empty.")
        if not target_url.strip():
            raise ValueError("target_url must not be empty.")

        started_at = perf_counter()
        action_history: list[ActionRecord] = []
        observation = await self.observation_engine.observe(self.tools.runtime)

        if completion_check is not None and completion_check(observation):
            return self._result(
                status="completed",
                goal=goal,
                target_url=target_url,
                observation=observation,
                action_history=action_history,
                started_at=started_at,
                message="Verified completion from the current browser state.",
            )

        for step in range(1, self.max_steps + 1):
            if self._is_cancelled():
                return self._result(
                    status="cancelled",
                    goal=goal,
                    target_url=target_url,
                    observation=observation,
                    action_history=action_history,
                    started_at=started_at,
                    error="Run was cancelled before the next action.",
                )
            try:
                decision = await self.actor.decide(
                    goal=goal,
                    target_url=target_url,
                    observation=observation,
                    history=[
                        record.history_item()
                        for record in action_history
                    ],
                )
            except Exception as exc:
                return self._result(
                    status="actor_error",
                    goal=goal,
                    target_url=target_url,
                    observation=observation,
                    action_history=action_history,
                    started_at=started_at,
                    error=f"{type(exc).__name__}: {exc}",
                )

            if decision.kind == "done":
                return self._result(
                    status="completed",
                    goal=goal,
                    target_url=target_url,
                    observation=observation,
                    action_history=action_history,
                    started_at=started_at,
                    message=decision.message,
                )

            assert decision.tool_name is not None
            assert decision.arguments is not None
            action_started_at = perf_counter()
            semantic_target = self._semantic_target(
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            )
            signature = await self._capture_signature(
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            )
            healing: dict[str, Any] | None = None
            try:
                outcome = await self.tools.execute(
                    decision.tool_name,
                    decision.arguments,
                )
            except Exception as exc:
                if (
                    signature is not None
                    and self.self_healing_locator is not None
                    and not isinstance(
                    exc, ApprovalRequiredError
                    )
                ):
                    try:
                        observation = await self.observation_engine.observe(
                            self.tools.runtime
                        )
                        repaired = await self.self_healing_locator.heal(
                            engine=self.observation_engine,
                            observation=observation,
                            target=signature,
                        )
                        repaired_arguments = dict(decision.arguments)
                        repaired_arguments["ref"] = repaired.healed_ref
                        outcome = await self.tools.execute(
                            decision.tool_name,
                            repaired_arguments,
                        )
                        healing = repaired.model_dump(mode="json")
                    except Exception:
                        outcome = None
                else:
                    outcome = None

                if outcome is not None:
                    action_history.append(
                        ActionRecord(
                            step=step,
                            tool_name=decision.tool_name,
                            arguments=decision.arguments,
                            duration_ms=self._elapsed_ms(action_started_at),
                            outcome=outcome,
                            semantic_target=semantic_target,
                            healing=healing,
                        )
                    )
                    observation = await self.observation_engine.observe(
                        self.tools.runtime
                    )
                    if completion_check is not None and completion_check(observation):
                        return self._result(
                            status="completed",
                            goal=goal,
                            target_url=target_url,
                            observation=observation,
                            action_history=action_history,
                            started_at=started_at,
                            message="Verified completion after a healed action.",
                        )
                    continue
                action_history.append(
                    ActionRecord(
                        step=step,
                        tool_name=decision.tool_name,
                        arguments=decision.arguments,
                        duration_ms=self._elapsed_ms(action_started_at),
                        error=f"{type(exc).__name__}: {exc}",
                        semantic_target=semantic_target,
                    )
                )
                return self._result(
                    status="tool_error",
                    goal=goal,
                    target_url=target_url,
                    observation=observation,
                    action_history=action_history,
                    started_at=started_at,
                    error=action_history[-1].error,
                )

            action_history.append(
                ActionRecord(
                    step=step,
                    tool_name=decision.tool_name,
                    arguments=decision.arguments,
                    duration_ms=self._elapsed_ms(action_started_at),
                    outcome=outcome,
                    semantic_target=semantic_target,
                    healing=healing,
                )
            )
            observation = await self.observation_engine.observe(
                self.tools.runtime
            )
            if completion_check is not None and completion_check(observation):
                return self._result(
                    status="completed",
                    goal=goal,
                    target_url=target_url,
                    observation=observation,
                    action_history=action_history,
                    started_at=started_at,
                    message="Verified completion after browser action.",
                )

        return self._result(
            status="max_steps_reached",
            goal=goal,
            target_url=target_url,
            observation=observation,
            action_history=action_history,
            started_at=started_at,
            error=(
                f"Agent reached the Day 3 max_steps limit ({self.max_steps}) "
                "without a DONE response."
            ),
        )

    def _result(
        self,
        *,
        status: RunStatus,
        goal: str,
        target_url: str,
        observation: BrowserObservation,
        action_history: list[ActionRecord],
        started_at: float,
        message: str = "",
        error: str | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(
            status=status,
            goal=goal,
            target_url=target_url,
            final_observation=observation,
            action_history=action_history,
            duration_ms=self._elapsed_ms(started_at),
            message=message,
            error=error,
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return round((perf_counter() - started_at) * 1000)

    def _is_cancelled(self) -> bool:
        return bool(
            self.cancellation_check is not None
            and self.cancellation_check()
        )

    def _semantic_target(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        if tool_name == "open_url":
            url = arguments.get("url")
            return {"url": url} if isinstance(url, str) else None
        ref = arguments.get("ref")
        if not isinstance(ref, str):
            return None
        try:
            element = self.observation_engine.element_for(ref)
        except KeyError:
            return None
        return {
            "role": element.role,
            "name": element.name,
            "placeholder": element.placeholder,
            "tag": element.tag,
        }

    async def _capture_signature(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ElementSignature | None:
        if self.self_healing_locator is None or tool_name not in {"click", "fill"}:
            return None
        ref = arguments.get("ref")
        if not isinstance(ref, str):
            return None
        try:
            element = self.observation_engine.element_for(ref)
            return await self.self_healing_locator.capture(
                engine=self.observation_engine,
                element=element,
            )
        except Exception:
            return None

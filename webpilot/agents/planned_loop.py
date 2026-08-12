from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from webpilot.agents.loop import AgentRunResult, SingleBrowserAgent
from webpilot.agents.planner import BrowserPlanner, PlanStep, TestPlan
from webpilot.browser.observation import ObservationEngine
from webpilot.graph.state import (
    Day4RunState,
    StepVerification,
    summarize_observation,
)
from webpilot.verifier.rules import RuleVerifier, VerificationResult


Day4Status = Literal[
    "passed",
    "plan_error",
    "execution_error",
    "verification_failed",
]


@dataclass(frozen=True)
class Day4RunResult:
    """Immutable record for one Plan -> Act -> Verify Day 4 run.

    The Actor is never the final authority: every completed plan step is
    independently verified from the newly observed browser state.
    """

    status: Day4Status
    state: Day4RunState | None
    step_runs: list[AgentRunResult]
    failed_step_id: str | None
    duration_ms: int
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "passed": self.passed,
            "failed_step_id": self.failed_step_id,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "state": (
                self.state.model_dump(mode="json")
                if self.state is not None
                else None
            ),
            "step_runs": [run.as_dict() for run in self.step_runs],
        }


class PlannedBrowserAgent:
    """Day 4 orchestration: plan once, execute, then verify each milestone."""

    def __init__(
        self,
        *,
        planner: BrowserPlanner,
        agent: SingleBrowserAgent,
        observation_engine: ObservationEngine,
        verifier: RuleVerifier,
    ) -> None:
        if agent.observation_engine is not observation_engine:
            raise ValueError(
                "PlannedBrowserAgent requires the same ObservationEngine "
                "for execution and verification."
            )
        self.planner = planner
        self.agent = agent
        self.observation_engine = observation_engine
        self.verifier = verifier

    async def run(
        self,
        *,
        goal: str,
        target_url: str,
    ) -> Day4RunResult:
        if not goal.strip():
            raise ValueError("goal must not be empty.")
        if not target_url.strip():
            raise ValueError("target_url must not be empty.")

        started_at = perf_counter()
        try:
            plan = await self.planner.plan(
                goal=goal,
                target_url=target_url,
            )
        except Exception as exc:
            return self._result(
                status="plan_error",
                state=None,
                step_runs=[],
                failed_step_id=None,
                started_at=started_at,
                error=f"{type(exc).__name__}: {exc}",
            )

        state = Day4RunState(
            task=goal,
            target_url=target_url,
            plan=plan,
            status="running",
        )
        step_runs: list[AgentRunResult] = []
        for index, step in enumerate(plan.steps):
            execution = await self.agent.run(
                goal=step.goal,
                target_url=target_url,
            )
            step_runs.append(execution)
            state.current_step_index = index
            state.observation = summarize_observation(
                execution.final_observation
            )
            state.history.extend(
                self._to_action_record(record, step_id=step.id)
                for record in execution.action_history
            )

            if execution.status != "completed":
                state.status = "failed"
                return self._result(
                    status="execution_error",
                    state=state,
                    step_runs=step_runs,
                    failed_step_id=step.id,
                    started_at=started_at,
                    error=(
                        f"Actor execution for {step.id} did not complete: "
                        f"{execution.status}; "
                        f"{execution.error or execution.message}"
                    ),
                )

            verification = self.verifier.verify(
                observation=execution.final_observation,
                criteria=step.success_criteria,
            )
            state.verification = verification
            state.step_verifications.append(
                StepVerification(
                    plan_step_id=step.id,
                    result=verification,
                )
            )
            if verification.status != "PASS":
                state.status = "failed"
                return self._result(
                    status="verification_failed",
                    state=state,
                    step_runs=step_runs,
                    failed_step_id=step.id,
                    started_at=started_at,
                    error=self._verification_error(step, verification),
                )

        state.current_step_index = len(plan.steps)
        state.status = "completed"
        return self._result(
            status="passed",
            state=state,
            step_runs=step_runs,
            failed_step_id=None,
            started_at=started_at,
        )

    @staticmethod
    def _to_action_record(record: object, *, step_id: str):
        from webpilot.graph.state import ActionRecord

        return ActionRecord(
            plan_step_id=step_id,
            action_index=record.step,
            tool_name=record.tool_name,
            arguments=record.arguments,
            result=(
                record.outcome
                if record.outcome is not None
                else {"ok": False, "error": record.error or "unknown error"}
            ),
        )

    def _result(
        self,
        *,
        status: Day4Status,
        state: Day4RunState | None,
        step_runs: list[AgentRunResult],
        failed_step_id: str | None,
        started_at: float,
        error: str | None = None,
    ) -> Day4RunResult:
        return Day4RunResult(
            status=status,
            state=state,
            step_runs=step_runs,
            failed_step_id=failed_step_id,
            duration_ms=round((perf_counter() - started_at) * 1000),
            error=error,
        )

    @staticmethod
    def _verification_error(
        step: PlanStep,
        verification: VerificationResult,
    ) -> str:
        return (
            f"Verification failed for {step.id} ({step.goal}): "
            f"{verification.failure_reason or 'unknown verification failure'}"
        )

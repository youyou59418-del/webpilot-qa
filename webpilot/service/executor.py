from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from webpilot.agents.actor import BrowserActor
from webpilot.agents.loop import SingleBrowserAgent
from webpilot.agents.planned_loop import PlannedBrowserAgent
from webpilot.agents.planner import BrowserPlanner
from webpilot.artifacts.store import ArtifactStore
from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.locator import SelfHealingLocator
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.llm.adapter import OpenAICompatibleLLM
from webpilot.runs.models import RunRecord, RunStatus, WorkerExecutionResult
from webpilot.safety.gate import SafetyGate
from webpilot.verifier.rules import RuleVerifier


class RunExecutor(Protocol):
    async def execute(
        self,
        record: RunRecord,
        *,
        cancel_requested: Callable[[], bool],
    ) -> WorkerExecutionResult:
        ...


class WebPilotRunExecutor:
    """Production adapter from a durable Day 8 run to the Day 7 workflow."""

    def __init__(self, *, artifact_store: ArtifactStore) -> None:
        self.artifact_store = artifact_store

    async def execute(
        self,
        record: RunRecord,
        *,
        cancel_requested: Callable[[], bool],
    ) -> WorkerExecutionResult:
        if cancel_requested():
            return WorkerExecutionResult(
                status=RunStatus.CANCELLED,
                result={"reason": "cancelled before browser startup"},
            )

        try:
            llm = OpenAICompatibleLLM.from_env()
        except RuntimeError as exc:
            return WorkerExecutionResult(
                status=RunStatus.FAILED,
                result={"error": f"LLM configuration error: {exc}"},
            )

        runtime = BrowserRuntime()
        artifact_dir = self.artifact_store.create_run(record.run_id)
        variant = record.request.variant
        observation_engine = ObservationEngine()
        safety_gate = SafetyGate(
            approved_fingerprints=set(record.approved_fingerprints)
        )
        agent = SingleBrowserAgent(
            actor=BrowserActor(llm),
            observation_engine=observation_engine,
            tools=BrowserToolExecutor(
                runtime,
                observation_engine,
                safety_gate=safety_gate,
            ),
            max_steps=record.request.max_steps,
            cancellation_check=cancel_requested,
            self_healing_locator=(
                None
                if variant == "no_self_healing"
                else SelfHealingLocator()
            ),
        )
        if variant == "single_agent":
            await runtime.start()
            trace_started = False
            shopbench_state: dict[str, object] | None = None
            try:
                await runtime.start_trace()
                trace_started = True
                single_result = await agent.run(
                    goal=record.request.goal,
                    target_url=record.request.target_url,
                )
                shopbench_state = await self._shopbench_state(runtime)
            finally:
                try:
                    await runtime.screenshot(artifact_dir / "final.png")
                except Exception:
                    pass
                if trace_started:
                    try:
                        await runtime.stop_trace(artifact_dir / "trace.zip")
                    except Exception:
                        pass
                await runtime.close()

            payload = single_result.as_dict()
            payload["status"] = (
                "passed" if single_result.status == "completed" else "execution_error"
            )
            payload["variant"] = variant
            payload["shopbench_state"] = shopbench_state
            self.artifact_store.write_json(
                run_id=record.run_id,
                name="workflow.json",
                payload=payload,
            )
            self.artifact_store.write_json(
                run_id=record.run_id,
                name="safety.json",
                payload=[item.model_dump(mode="json") for item in safety_gate.audit_records],
            )
            return WorkerExecutionResult(
                status=(
                    RunStatus.COMPLETED
                    if payload["status"] == "passed"
                    else RunStatus.FAILED
                ),
                result=payload,
            )

        workflow = PlannedBrowserAgent(
            planner=BrowserPlanner(llm),
            agent=agent,
            observation_engine=observation_engine,
            verifier=RuleVerifier(),
            enable_verifier=variant != "no_verifier",
            enable_recovery=variant != "no_recovery",
            max_retries=record.request.max_retries,
            bootstrap_target=True,
        )

        await runtime.start()
        trace_started = False
        shopbench_state: dict[str, object] | None = None
        try:
            await runtime.start_trace()
            trace_started = True
            result = await workflow.run(
                goal=record.request.goal,
                target_url=record.request.target_url,
            )
            shopbench_state = await self._shopbench_state(runtime)
        finally:
            try:
                await runtime.screenshot(artifact_dir / "final.png")
            except Exception:
                # An unavailable/closed page must not hide the workflow result.
                pass
            if trace_started:
                try:
                    await runtime.stop_trace(artifact_dir / "trace.zip")
                except Exception:
                    pass
            await runtime.close()

        payload = result.as_dict()
        payload["shopbench_state"] = shopbench_state
        self.artifact_store.write_json(
            run_id=record.run_id,
            name="workflow.json",
            payload=payload,
        )
        self.artifact_store.write_json(
            run_id=record.run_id,
            name="safety.json",
            payload=[item.model_dump(mode="json") for item in safety_gate.audit_records],
        )

        if result.status == "passed":
            return WorkerExecutionResult(
                status=RunStatus.COMPLETED,
                result=payload,
            )
        if result.status == "approval_required" and result.state is not None:
            assert result.state.approval is not None
            return WorkerExecutionResult(
                status=RunStatus.APPROVAL_REQUIRED,
                result=payload,
                approval=result.state.approval,
            )
        if result.status == "cancelled":
            return WorkerExecutionResult(
                status=RunStatus.CANCELLED,
                result=payload,
            )
        return WorkerExecutionResult(
            status=RunStatus.FAILED,
            result=payload,
        )

    @staticmethod
    async def _shopbench_state(runtime: BrowserRuntime) -> dict[str, object] | None:
        """Read ShopBench's public controlled-state oracle when available."""
        try:
            value = await runtime.page.evaluate(
                """() => (
                    typeof window.__shopbench_state === "function"
                        ? window.__shopbench_state()
                        : null
                )"""
            )
        except Exception:
            return None
        return value if isinstance(value, dict) else None

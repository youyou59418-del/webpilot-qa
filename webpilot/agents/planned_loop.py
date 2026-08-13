from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Awaitable, Callable, Literal

import asyncio
import json

from webpilot.agents.loop import AgentRunResult, SingleBrowserAgent
from webpilot.agents.planner import BrowserPlanner, PlanStep, TestPlan
from webpilot.browser.observation import BrowserObservation, ObservationEngine
from webpilot.graph.state import (
    ActionRecord,
    Day4RunState,
    PlanAttempt,
    RecoveryRecord,
    StepVerification,
    summarize_observation,
)
from webpilot.recovery.classifier import FailureClassifier
from webpilot.recovery.models import (
    FailureEvent,
    RecoveryAction,
    RecoveryDecision,
    RetryBudget,
)
from webpilot.recovery.policy import RecoveryPolicy
from webpilot.safety.models import ApprovalRequest
from webpilot.verifier.rules import RuleVerifier, VerificationResult


Day4Status = Literal[
    "passed",
    "plan_error",
    "execution_error",
    "verification_failed",
    "recovery_exhausted",
    "approval_required",
    "cancelled",
]


@dataclass(frozen=True)
class _StepFailure:
    failure: FailureEvent
    step: PlanStep
    index: int
    approval: ApprovalRequest | None = None
    cancelled: bool = False


@dataclass(frozen=True)
class Day4RunResult:
    """Immutable record for one planned browser run.

    Day 4 uses ``enable_recovery=False``. Day 5 enables bounded recovery:
    every handled failure is classified, recorded, and independently verified
    after the next completed plan step.
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
    """Planner -> per-step Actor -> independent Verifier, with optional Day 5 recovery."""

    def __init__(
        self,
        *,
        planner: BrowserPlanner,
        agent: SingleBrowserAgent,
        observation_engine: ObservationEngine,
        verifier: RuleVerifier,
        enable_verifier: bool = True,
        enable_recovery: bool = False,
        recovery_policy: RecoveryPolicy | None = None,
        failure_classifier: FailureClassifier | None = None,
        max_retries: int = 2,
        bootstrap_target: bool = False,
        short_wait_s: float = 0.25,
        wait: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if agent.observation_engine is not observation_engine:
            raise ValueError(
                "PlannedBrowserAgent requires the same ObservationEngine "
                "for execution and verification."
            )
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative.")
        if short_wait_s < 0:
            raise ValueError("short_wait_s must be non-negative.")
        self.planner = planner
        self.agent = agent
        self.observation_engine = observation_engine
        self.verifier = verifier
        self.enable_verifier = enable_verifier
        self.enable_recovery = enable_recovery
        self.recovery_policy = recovery_policy or RecoveryPolicy()
        self.failure_classifier = failure_classifier or FailureClassifier()
        self.max_retries = max_retries
        self.bootstrap_target = bootstrap_target
        self.short_wait_s = short_wait_s
        self.wait = wait or asyncio.sleep

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
        planning_observation = None
        if self.bootstrap_target:
            try:
                await self.agent.tools.execute(
                    "open_url",
                    {"url": target_url},
                )
                planning_observation = await self.observation_engine.observe(
                    self.agent.tools.runtime
                )
            except Exception as exc:
                return self._result(
                    status="plan_error",
                    state=None,
                    step_runs=[],
                    failed_step_id=None,
                    started_at=started_at,
                    error=(
                        "Unable to capture the initial browser snapshot: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )

        initial_plan = await self._plan_or_result(
            goal=goal,
            target_url=target_url,
            recovery_context=None,
            browser_observation=planning_observation,
            started_at=started_at,
        )
        if isinstance(initial_plan, Day4RunResult):
            return initial_plan

        state = Day4RunState(
            task=goal,
            target_url=target_url,
            plan=initial_plan,
            plan_attempt=1,
            plan_history=[
                PlanAttempt(
                    attempt=1,
                    trigger="initial",
                    plan=initial_plan,
                )
            ],
            observation=(
                summarize_observation(planning_observation)
                if planning_observation is not None
                else None
            ),
            status="running",
        )
        step_runs: list[AgentRunResult] = []
        budget = RetryBudget(max_retries=self.max_retries)
        resume_index = 0

        while True:
            outcome = await self._run_plan_attempt(
                state=state,
                step_runs=step_runs,
                budget=budget,
                start_index=resume_index,
            )
            if outcome is None:
                state.status = "completed"
                state.current_step_index = len(state.plan.steps)
                return self._result(
                    status="passed",
                    state=state,
                    step_runs=step_runs,
                    failed_step_id=None,
                    started_at=started_at,
                )

            if outcome.cancelled:
                state.status = "cancelled"
                return self._result(
                    status="cancelled",
                    state=state,
                    step_runs=step_runs,
                    failed_step_id=outcome.step.id,
                    started_at=started_at,
                    error=outcome.failure.message,
                )

            if outcome.approval is not None:
                state.status = "approval_required"
                state.approval = outcome.approval
                return self._result(
                    status="approval_required",
                    state=state,
                    step_runs=step_runs,
                    failed_step_id=outcome.step.id,
                    started_at=started_at,
                    error=outcome.failure.message,
                )

            failure = outcome.failure
            failed_step = outcome.step
            failed_index = outcome.index
            if not self.enable_recovery:
                state.status = "failed"
                return self._failure_result(
                    state=state,
                    step_runs=step_runs,
                    failure=failure,
                    failed_step=failed_step,
                    started_at=started_at,
                    status=(
                        "verification_failed"
                        if failure.failure_type.value == "ASSERTION_FAILED"
                        else "execution_error"
                    ),
                )

            decision = self.recovery_policy.decide(
                failure=failure,
                budget=budget,
            )
            if decision.consume_retry:
                budget.consume()

            recovery_outcome = await self._apply_recovery(
                state=state,
                step_runs=step_runs,
                failure=failure,
                decision=decision,
                budget=budget,
                started_at=started_at,
            )
            if isinstance(recovery_outcome, Day4RunResult):
                return recovery_outcome
            if recovery_outcome == "retry_step":
                resume_index = failed_index
                continue

            replan_result = await self._replan(
                state=state,
                step_runs=step_runs,
                failure=failure,
                started_at=started_at,
            )
            if isinstance(replan_result, Day4RunResult):
                return replan_result
            resume_index = 0

    async def _run_plan_attempt(
        self,
        *,
        state: Day4RunState,
        step_runs: list[AgentRunResult],
        budget: RetryBudget,
        start_index: int,
    ) -> _StepFailure | None:
        for index in range(start_index, len(state.plan.steps)):
            step = state.plan.steps[index]
            state.current_step_index = index
            requires_action = self.bootstrap_target and self._step_requires_action(step)
            # A planner milestone may already be true because the target page
            # has a useful default state or a previous step fulfilled it as a
            # side effect.  Verify first so a smaller model is not invited to
            # repeat a successful click solely to produce a DONE message.
            if self.enable_verifier and not requires_action:
                current_observation = await self.observation_engine.observe(
                    self.agent.tools.runtime
                )
                preverification = self.verifier.verify(
                    observation=current_observation,
                    criteria=step.success_criteria,
                )
                if preverification.status == "PASS":
                    state.observation = summarize_observation(current_observation)
                    state.verification = preverification
                    state.step_verifications.append(
                        StepVerification(
                            plan_step_id=step.id,
                            result=preverification,
                            plan_attempt=state.plan_attempt,
                        )
                    )
                    continue
            execution = await self.agent.run(
                goal=step.goal,
                target_url=state.target_url,
                completion_check=(
                    lambda observation: self.verifier.verify(
                        observation=observation,
                        criteria=step.success_criteria,
                    ).status == "PASS"
                    if self.enable_verifier
                    else None
                ),
                require_action=requires_action,
            )
            step_runs.append(execution)
            state.observation = summarize_observation(
                execution.final_observation
            )
            state.history.extend(
                self._to_action_record(
                    record,
                    step_id=step.id,
                    plan_attempt=state.plan_attempt,
                )
                for record in execution.action_history
            )

            if execution.status != "completed":
                failure = self.failure_classifier.from_exception(
                        exc=RuntimeError(
                            execution.error
                            or execution.message
                            or f"Actor status: {execution.status}"
                        ),
                        step_id=step.id,
                        retry_count=budget.retry_count,
                        tool_name=(
                            execution.action_history[-1].tool_name
                            if execution.action_history
                            else None
                        ),
                        element_ref=self._last_element_ref(execution),
                        current_url=execution.final_observation.url,
                    )
                if execution.status == "cancelled":
                    return _StepFailure(
                        failure=failure,
                        step=step,
                        index=index,
                        cancelled=True,
                    )
                return _StepFailure(
                    failure=failure,
                    step=step,
                    index=index,
                    approval=self._approval_from_execution(execution),
                )

            if not self.enable_verifier:
                continue

            verification = self.verifier.verify(
                observation=execution.final_observation,
                criteria=step.success_criteria,
            )
            state.verification = verification
            state.step_verifications.append(
                StepVerification(
                    plan_step_id=step.id,
                    result=verification,
                    plan_attempt=state.plan_attempt,
                )
            )
            if verification.status != "PASS":
                return _StepFailure(
                    failure=self.failure_classifier.from_verification(
                        verification=verification,
                        step_id=step.id,
                        retry_count=budget.retry_count,
                        current_url=execution.final_observation.url,
                    ),
                    step=step,
                    index=index,
                )

        return None

    @staticmethod
    def _step_requires_action(step: PlanStep) -> bool:
        """Do not let static page text pre-satisfy an operational milestone."""
        goal = step.goal.lower()
        return any(
            marker in goal
            for marker in (
                "open", "navigate", "switch", "search", "filter", "select",
                "enable", "disable", "sort", "add", "remove", "fill", "save",
                "log in", "login", "show", "trigger", "refresh", "retry", "move",
                "go to", "recover",
            )
        )

    async def _apply_recovery(
        self,
        *,
        state: Day4RunState,
        step_runs: list[AgentRunResult],
        failure: FailureEvent,
        decision: RecoveryDecision,
        budget: RetryBudget,
        started_at: float,
    ) -> str | Day4RunResult:
        if decision.action == RecoveryAction.STOP:
            return self._stop_after_recovery(
                state=state,
                step_runs=step_runs,
                failure=failure,
                decision=decision,
                budget=budget,
                started_at=started_at,
            )

        if decision.action == RecoveryAction.RE_OBSERVE:
            observation = await self.observation_engine.observe(
                self.agent.tools.runtime
            )
            state.observation = summarize_observation(observation)
            self._record_recovery(
                state=state,
                failure=failure,
                decision=decision,
                budget=budget,
                outcome="fresh_observation_recorded",
            )
            return "retry_step"

        if decision.action == RecoveryAction.SHORT_WAIT:
            await self.wait(self.short_wait_s)
            observation = await self.observation_engine.observe(
                self.agent.tools.runtime
            )
            state.observation = summarize_observation(observation)
            self._record_recovery(
                state=state,
                failure=failure,
                decision=decision,
                budget=budget,
                outcome="short_wait_then_fresh_observation",
            )
            return "retry_step"

        if decision.action == RecoveryAction.RETRY_ONCE:
            self._record_recovery(
                state=state,
                failure=failure,
                decision=decision,
                budget=budget,
                outcome="bounded_retry_scheduled",
            )
            return "retry_step"

        if decision.action == RecoveryAction.REPLAN:
            self._record_recovery(
                state=state,
                failure=failure,
                decision=decision,
                budget=budget,
                outcome="replan_scheduled",
            )
            return "replan"

        raise AssertionError(f"Unhandled recovery action: {decision.action}")

    async def _replan(
        self,
        *,
        state: Day4RunState,
        step_runs: list[AgentRunResult],
        failure: FailureEvent,
        started_at: float,
    ) -> Day4RunResult | None:
        next_attempt = state.plan_attempt + 1
        recovery_context = self._format_recovery_context(failure)
        browser_observation = await self.observation_engine.observe(
            self.agent.tools.runtime
        )
        plan_or_result = await self._plan_or_result(
            goal=state.task,
            target_url=state.target_url,
            recovery_context=recovery_context,
            browser_observation=browser_observation,
            started_at=started_at,
            state=state,
            step_runs=step_runs,
        )
        if isinstance(plan_or_result, Day4RunResult):
            return plan_or_result
        state.plan = plan_or_result
        state.plan_attempt = next_attempt
        state.current_step_index = 0
        state.plan_history.append(
            PlanAttempt(
                attempt=next_attempt,
                trigger="replan",
                plan=plan_or_result,
                failure=failure,
            )
        )
        return None

    async def _plan_or_result(
        self,
        *,
        goal: str,
        target_url: str,
        recovery_context: str | None,
        browser_observation: BrowserObservation | None = None,
        started_at: float,
        state: Day4RunState | None = None,
        step_runs: list[AgentRunResult] | None = None,
    ) -> TestPlan | Day4RunResult:
        try:
            return await self.planner.plan(
                goal=goal,
                target_url=target_url,
                recovery_context=recovery_context,
                browser_observation=browser_observation,
            )
        except Exception as exc:
            if state is not None:
                state.status = "failed"
            return self._result(
                status="plan_error",
                state=state,
                step_runs=step_runs or [],
                failed_step_id=None,
                started_at=started_at,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _stop_after_recovery(
        self,
        *,
        state: Day4RunState,
        step_runs: list[AgentRunResult],
        failure: FailureEvent,
        decision: RecoveryDecision,
        budget: RetryBudget,
        started_at: float,
    ) -> Day4RunResult:
        self._record_recovery(
            state=state,
            failure=failure,
            decision=decision,
            budget=budget,
            outcome="stopped",
        )
        state.status = "failed"
        return self._result(
            status="recovery_exhausted",
            state=state,
            step_runs=step_runs,
            failed_step_id=failure.step_id,
            started_at=started_at,
            error=(
                f"Recovery stopped for {failure.step_id}: "
                f"{decision.reason} Original failure: {failure.message}"
            ),
        )

    def _failure_result(
        self,
        *,
        state: Day4RunState,
        step_runs: list[AgentRunResult],
        failure: FailureEvent,
        failed_step: PlanStep,
        started_at: float,
        status: Day4Status,
    ) -> Day4RunResult:
        error = failure.message
        if status == "verification_failed" and state.verification is not None:
            error = self._verification_error(failed_step, state.verification)
        return self._result(
            status=status,
            state=state,
            step_runs=step_runs,
            failed_step_id=failed_step.id,
            started_at=started_at,
            error=error,
        )

    @staticmethod
    def _record_recovery(
        *,
        state: Day4RunState,
        failure: FailureEvent,
        decision: RecoveryDecision,
        budget: RetryBudget,
        outcome: str,
    ) -> None:
        state.recovery_history.append(
            RecoveryRecord(
                plan_attempt=state.plan_attempt,
                plan_step_id=failure.step_id,
                failure=failure,
                decision=decision,
                retry_count_after=budget.retry_count,
                outcome=outcome,
            )
        )

    @staticmethod
    def _to_action_record(
        record: object,
        *,
        step_id: str,
        plan_attempt: int,
    ) -> ActionRecord:
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
            plan_attempt=plan_attempt,
            semantic_target=record.semantic_target,
            healing=record.healing,
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
    def _last_element_ref(execution: AgentRunResult) -> str | None:
        if not execution.action_history:
            return None
        ref = execution.action_history[-1].arguments.get("ref")
        return ref if isinstance(ref, str) else None

    @staticmethod
    def _approval_from_execution(
        execution: AgentRunResult,
    ) -> ApprovalRequest | None:
        if not execution.action_history:
            return None
        error = execution.action_history[-1].error or ""
        prefix = "ApprovalRequiredError: APPROVAL_REQUIRED:"
        if not error.startswith(prefix):
            return None
        try:
            return ApprovalRequest.model_validate(
                json.loads(error.removeprefix(prefix))
            )
        except (ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _format_recovery_context(failure: FailureEvent) -> str:
        return (
            f"Failure type: {failure.failure_type.value}\n"
            f"Failed step: {failure.step_id}\n"
            f"Current URL: {failure.current_url or '<unknown>'}\n"
            f"Evidence: {failure.message}"
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

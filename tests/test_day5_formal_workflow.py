from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from webpilot.agents.actor import BrowserActor
from webpilot.agents.loop import SingleBrowserAgent
from webpilot.agents.planned_loop import PlannedBrowserAgent
from webpilot.agents.planner import BrowserPlanner
from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.llm.adapter import LLMReply, LLMToolCall
from webpilot.recovery.models import FailureType, RecoveryAction
from webpilot.verifier.rules import RuleVerifier


FIXTURE_URL = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "day3_agent.html"
).as_uri()


def plan_payload(*, expected_text: str) -> dict[str, Any]:
    return {
        "steps": [
            {
                "id": "step_1",
                "goal": "Search for laptop and reach results.",
                "risk_level": "L0",
                "success_criteria": [
                    {
                        "rule": "visible_text_contains",
                        "expected": expected_text,
                    }
                ],
            }
        ]
    }


class RecoveringSearchLLM:
    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.actor_turn = 0

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        names = {tool["function"]["name"] for tool in tools}
        if names == {"submit_test_plan"}:
            return LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="submit_test_plan",
                    arguments=plan_payload(
                        expected_text="Results for: laptop"
                    ),
                ),
            )

        self.actor_turn += 1
        replies = [
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="click",
                    arguments={"ref": "e999"},
                ),
            ),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="fill",
                    arguments={"ref": "e1", "value": "laptop"},
                ),
            ),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="click",
                    arguments={"ref": "e2"},
                ),
            ),
            LLMReply(
                content="DONE: Results for: laptop is visible."),
        ]
        return replies[self.actor_turn - 1]


class ReplanningSearchLLM:
    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.plan_turn = 0
        self.actor_turn = 0
        self.recovery_contexts: list[str | None] = []

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        names = {tool["function"]["name"] for tool in tools}
        if names == {"submit_test_plan"}:
            self.plan_turn += 1
            user_content = messages[-1]["content"]
            self.recovery_contexts.append(
                user_content if "RECOVERY CONTEXT:" in user_content else None
            )
            expected = (
                "Missing result" if self.plan_turn == 1 else "Results for: laptop"
            )
            return LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="submit_test_plan",
                    arguments=plan_payload(expected_text=expected),
                ),
            )

        self.actor_turn += 1
        replies = [
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="fill",
                    arguments={"ref": "e1", "value": "laptop"},
                ),
            ),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="click",
                    arguments={"ref": "e2"},
                ),
            ),
            LLMReply(
                content="DONE: Results for: laptop is visible."),
            LLMReply(
                content="DONE: Results for: laptop is still visible."),
        ]
        return replies[self.actor_turn - 1]


class ExhaustingRefLLM:
    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        names = {tool["function"]["name"] for tool in tools}
        if names == {"submit_test_plan"}:
            return LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="submit_test_plan",
                    arguments=plan_payload(
                        expected_text="Results for: laptop"
                    ),
                ),
            )
        return LLMReply(
            content="",
            tool_call=LLMToolCall(
                name="click",
                arguments={"ref": "e999"},
            ),
        )


class TwoStepRecoveryLLM:
    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.actor_turn = 0

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        names = {tool["function"]["name"] for tool in tools}
        if names == {"submit_test_plan"}:
            return LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="submit_test_plan",
                    arguments={
                        "steps": [
                            {
                                "id": "step_1",
                                "goal": "Open the product search page.",
                                "risk_level": "L0",
                                "success_criteria": [
                                    {
                                        "rule": "visible_text_contains",
                                        "expected": "Product Search",
                                    }
                                ],
                            },
                            {
                                "id": "step_2",
                                "goal": "Search for laptop and reach results.",
                                "risk_level": "L0",
                                "success_criteria": [
                                    {
                                        "rule": "visible_text_contains",
                                        "expected": "Results for: laptop",
                                    }
                                ],
                            },
                        ]
                    },
                ),
            )

        self.actor_turn += 1
        replies = [
            LLMReply(content="DONE: Product Search is visible."),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="click",
                    arguments={"ref": "e999"},
                ),
            ),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="fill",
                    arguments={"ref": "e1", "value": "laptop"},
                ),
            ),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="click",
                    arguments={"ref": "e2"},
                ),
            ),
            LLMReply(
                content="DONE: Results for: laptop is visible."),
        ]
        return replies[self.actor_turn - 1]


class DelayedVisibilityLLM:
    def __init__(self) -> None:
        self.actor_turn = 0

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        names = {tool["function"]["name"] for tool in tools}
        if names == {"submit_test_plan"}:
            return LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="submit_test_plan",
                    arguments=plan_payload(
                        expected_text="Results for: laptop"
                    ),
                ),
            )

        self.actor_turn += 1
        replies = [
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="click",
                    arguments={"ref": "e2"},
                ),
            ),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="fill",
                    arguments={"ref": "e1", "value": "laptop"},
                ),
            ),
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="click",
                    arguments={"ref": "e2"},
                ),
            ),
            LLMReply(content="DONE: Results for: laptop is visible."),
        ]
        return replies[self.actor_turn - 1]


class ForbiddenActor:
    async def decide(
        self,
        *,
        goal: str,
        observation: Any,
        history: list[dict[str, Any]],
        target_url: str,
    ) -> Any:
        raise RuntimeError("Actor returned forbidden browser tool: delete_account")


class AlwaysForbiddenLLM:
    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        names = {tool["function"]["name"] for tool in tools}
        if names == {"submit_test_plan"}:
            return LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="submit_test_plan",
                    arguments=plan_payload(
                        expected_text="Results for: laptop"
                    ),
                ),
            )
        return LLMReply(
            content="",
            tool_call=LLMToolCall(
                name="not_an_allowed_tool",
                arguments={},
            ),
        )


def make_workflow(
    runtime: BrowserRuntime,
    llm: Any,
    *,
    max_retries: int = 2,
    wait: Any | None = None,
) -> PlannedBrowserAgent:
    engine = ObservationEngine()
    return PlannedBrowserAgent(
        planner=BrowserPlanner(llm),
        agent=SingleBrowserAgent(
            actor=BrowserActor(llm),
            observation_engine=engine,
            tools=BrowserToolExecutor(runtime, engine),
            max_steps=4,
        ),
        observation_engine=engine,
        verifier=RuleVerifier(),
        enable_recovery=True,
        max_retries=max_retries,
        short_wait_s=0,
        wait=wait,
    )


@pytest.mark.asyncio
async def test_formal_workflow_reobserves_and_recovers_stale_ref() -> None:
    runtime = BrowserRuntime()
    workflow = make_workflow(runtime, RecoveringSearchLLM(FIXTURE_URL))

    await runtime.start()
    try:
        await runtime.open_url(FIXTURE_URL)
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "passed"
    assert result.state is not None
    assert result.state.status == "completed"
    assert result.state.recovery_history[0].failure.failure_type == (
        FailureType.ELEMENT_NOT_FOUND
    )
    assert result.state.recovery_history[0].decision.action == (
        RecoveryAction.RE_OBSERVE
    )
    assert result.state.recovery_history[0].retry_count_after == 1
    assert result.state.recovery_history[0].outcome == "fresh_observation_recorded"
    assert len(result.step_runs) == 2
    assert result.state.step_verifications[-1].result.status == "PASS"


@pytest.mark.asyncio
async def test_formal_workflow_replans_after_verifier_failure() -> None:
    runtime = BrowserRuntime()
    llm = ReplanningSearchLLM(FIXTURE_URL)
    workflow = make_workflow(runtime, llm)

    await runtime.start()
    try:
        await runtime.open_url(FIXTURE_URL)
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "passed"
    assert result.state is not None
    assert result.state.plan_attempt == 2
    assert [item.trigger for item in result.state.plan_history] == [
        "initial",
        "replan",
    ]
    assert result.state.recovery_history[0].failure.failure_type == (
        FailureType.ASSERTION_FAILED
    )
    assert result.state.recovery_history[0].decision.action == (
        RecoveryAction.REPLAN
    )
    assert llm.recovery_contexts[1] is not None
    assert "ASSERTION_FAILED" in (llm.recovery_contexts[1] or "")
    assert result.state.step_verifications[0].result.status == "FAIL"
    assert result.state.step_verifications[1].result.status == "PASS"


@pytest.mark.asyncio
async def test_formal_workflow_stops_when_recovery_budget_is_exhausted() -> None:
    runtime = BrowserRuntime()
    workflow = make_workflow(
        runtime,
        ExhaustingRefLLM(),
        max_retries=2,
    )

    await runtime.start()
    try:
        await runtime.open_url(FIXTURE_URL)
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "recovery_exhausted"
    assert result.state is not None
    assert len(result.step_runs) == 3
    assert len(result.state.recovery_history) == 3
    assert [
        item.decision.action
        for item in result.state.recovery_history
    ] == [
        RecoveryAction.RE_OBSERVE,
        RecoveryAction.RE_OBSERVE,
        RecoveryAction.STOP,
    ]
    assert result.state.recovery_history[-1].retry_count_after == 2


@pytest.mark.asyncio
async def test_recovery_retries_only_failed_step_not_prior_passed_step() -> None:
    runtime = BrowserRuntime()
    workflow = make_workflow(runtime, TwoStepRecoveryLLM(FIXTURE_URL))

    await runtime.start()
    try:
        await runtime.open_url(FIXTURE_URL)
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "passed"
    assert result.state is not None
    assert [run.goal for run in result.step_runs] == [
        "Open the product search page.",
        "Search for laptop and reach results.",
        "Search for laptop and reach results.",
    ]
    assert [
        item.plan_step_id
        for item in result.state.step_verifications
    ] == ["step_1", "step_2"]


@pytest.mark.asyncio
async def test_formal_workflow_short_wait_is_bounded_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = BrowserRuntime()
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    workflow = make_workflow(
        runtime,
        DelayedVisibilityLLM(),
        wait=record_sleep,
    )
    original_execute = workflow.agent.tools.execute
    first_click = True

    async def transient_not_visible(
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        nonlocal first_click
        if tool_name == "click" and first_click:
            first_click = False
            raise RuntimeError("Element is not visible")
        return await original_execute(tool_name, arguments)

    monkeypatch.setattr(workflow.agent.tools, "execute", transient_not_visible)

    await runtime.start()
    try:
        await runtime.open_url(FIXTURE_URL)
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "passed"
    assert result.state is not None
    assert sleeps == [0]
    assert result.state.recovery_history[0].decision.action == (
        RecoveryAction.SHORT_WAIT
    )
    assert result.state.step_verifications[-1].result.status == "PASS"


@pytest.mark.asyncio
async def test_formal_workflow_forbidden_action_stops_without_retry() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    workflow = PlannedBrowserAgent(
        planner=BrowserPlanner(AlwaysForbiddenLLM()),
        agent=SingleBrowserAgent(
            actor=ForbiddenActor(),
            observation_engine=engine,
            tools=BrowserToolExecutor(runtime, engine),
            max_steps=4,
        ),
        observation_engine=engine,
        verifier=RuleVerifier(),
        enable_recovery=True,
        max_retries=2,
        short_wait_s=0,
    )

    await runtime.start()
    try:
        await runtime.open_url(FIXTURE_URL)
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "recovery_exhausted"
    assert result.state is not None
    assert result.state.recovery_history[0].failure.failure_type == (
        FailureType.ACTION_FORBIDDEN
    )
    assert result.state.recovery_history[0].decision.action == RecoveryAction.STOP
    assert result.state.recovery_history[0].retry_count_after == 0

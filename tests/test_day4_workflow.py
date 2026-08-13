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
from webpilot.verifier.rules import RuleVerifier


FIXTURE_URL = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "day3_agent.html"
).as_uri()


class PlannedSearchLLM:
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
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="open_url",
                    arguments={"url": self.target_url},
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


class FailingVerificationLLM(PlannedSearchLLM):
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
                                        "expected": "This text does not exist",
                                    }
                                ],
                            }
                        ]
                    },
                ),
            )
        self.actor_turn += 1
        replies = [
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="open_url",
                    arguments={"url": self.target_url},
                ),
            ),
            LLMReply(content="DONE: The requested state is visible."),
        ]
        return replies[self.actor_turn - 1]


class PreverifiedStepLLM(PlannedSearchLLM):
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
                                "goal": "Confirm the page is already visible.",
                                "risk_level": "L0",
                                "success_criteria": [
                                    {
                                        "rule": "visible_text_contains",
                                        "expected": "Product Search",
                                    }
                                ],
                            },
                        ]
                    },
                ),
            )
        return await super().chat(messages=messages, tools=tools)


def make_workflow(
    runtime: BrowserRuntime,
    llm: Any,
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
    )


@pytest.mark.asyncio
async def test_day4_workflow_runs_plan_execute_verify() -> None:
    runtime = BrowserRuntime()
    workflow = make_workflow(runtime, PlannedSearchLLM(FIXTURE_URL))

    await runtime.start()
    try:
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "passed"
    assert result.passed is True
    assert result.failed_step_id is None
    assert result.state is not None
    assert result.state.status == "completed"
    assert result.state.current_step_index == 2
    assert len(result.step_runs) == 2
    assert result.step_runs[0].status == "completed"
    assert result.step_runs[1].status == "completed"
    assert result.state.verification is not None
    assert result.state.verification.status == "PASS"
    assert [
        item.plan_step_id
        for item in result.state.step_verifications
    ] == ["step_1", "step_2"]
    assert all(
        item.result.status == "PASS"
        for item in result.state.step_verifications
    )


@pytest.mark.asyncio
async def test_day4_workflow_keeps_actor_done_separate_from_verification() -> None:
    runtime = BrowserRuntime()
    workflow = make_workflow(runtime, FailingVerificationLLM(FIXTURE_URL))

    await runtime.start()
    try:
        result = await workflow.run(
            goal="Open the product search page.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "verification_failed"
    assert result.failed_step_id == "step_1"
    assert result.step_runs[0].status == "completed"
    assert "This text does not exist" in (result.error or "")
    assert result.state is not None
    assert len(result.state.step_verifications) == 1
    assert result.state.step_verifications[0].result.status == "FAIL"


@pytest.mark.asyncio
async def test_day4_workflow_skips_a_step_already_proved_by_browser_state() -> None:
    runtime = BrowserRuntime()
    workflow = make_workflow(runtime, PreverifiedStepLLM(FIXTURE_URL))

    await runtime.start()
    try:
        result = await workflow.run(
            goal="Open the product search page and confirm it is visible.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    assert result.status == "passed"
    assert len(result.step_runs) == 1
    assert result.state is not None
    assert [item.plan_step_id for item in result.state.step_verifications] == [
        "step_1",
        "step_2",
    ]
    assert all(item.result.status == "PASS" for item in result.state.step_verifications)


def test_day4_workflow_rejects_mismatched_observation_engine() -> None:
    runtime = BrowserRuntime()
    first_engine = ObservationEngine()
    second_engine = ObservationEngine()
    llm = PlannedSearchLLM(FIXTURE_URL)
    agent = SingleBrowserAgent(
        actor=BrowserActor(llm),
        observation_engine=first_engine,
        tools=BrowserToolExecutor(runtime, first_engine),
    )

    with pytest.raises(ValueError, match="same ObservationEngine"):
        PlannedBrowserAgent(
            planner=BrowserPlanner(llm),
            agent=agent,
            observation_engine=second_engine,
            verifier=RuleVerifier(),
        )


def test_day4_state_rejects_impossible_progress() -> None:
    from pydantic import ValidationError

    from webpilot.agents.planner import TestPlan
    from webpilot.graph.state import Day4RunState

    plan = TestPlan.model_validate(
        {
            "steps": [
                {
                    "id": "step_1",
                    "goal": "Open the page.",
                    "risk_level": "L0",
                    "success_criteria": [
                        {
                            "rule": "visible_text_contains",
                            "expected": "Product Search",
                        }
                    ],
                }
            ]
        }
    )

    with pytest.raises(ValidationError, match="cannot exceed"):
        Day4RunState(
            task="Open the page.",
            target_url=FIXTURE_URL,
            plan=plan,
            current_step_index=2,
        )

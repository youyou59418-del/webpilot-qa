from pathlib import Path
from typing import Any

import pytest

from webpilot.agents.actor import BrowserActor
from webpilot.agents.loop import SingleBrowserAgent
from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.llm.adapter import LLMReply, LLMToolCall


@pytest.fixture
def fixture_url() -> str:
    return (
        Path("tests/fixtures/day3_agent.html")
        .resolve()
        .as_uri()
    )


class ScriptedSearchLLM:
    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.turn = 0

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        self.turn += 1
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
                content="DONE: The visible page text says Results for: laptop.",
            ),
        ]
        return replies[self.turn - 1]


class ReobserveForeverLLM:
    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        return LLMReply(
            content="",
            tool_call=LLMToolCall(
                name="get_page_state",
                arguments={},
            ),
        )


class InvalidRefLLM:
    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        return LLMReply(
            content="",
            tool_call=LLMToolCall(
                name="click",
                arguments={"ref": "e999"},
            ),
        )


def make_agent(
    runtime: BrowserRuntime,
    llm: Any,
    *,
    max_steps: int,
) -> SingleBrowserAgent:
    engine = ObservationEngine()
    return SingleBrowserAgent(
        actor=BrowserActor(llm),
        observation_engine=engine,
        tools=BrowserToolExecutor(runtime, engine),
        max_steps=max_steps,
    )


@pytest.mark.asyncio
async def test_single_agent_runs_observe_think_act_loop(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()
    agent = make_agent(
        runtime,
        ScriptedSearchLLM(fixture_url),
        max_steps=6,
    )

    await runtime.start()
    try:
        result = await agent.run(
            goal="Search for laptop and wait for the matching result.",
            target_url=fixture_url,
        )
    finally:
        await runtime.close()

    assert result.status == "completed"
    assert result.tool_calls == 3
    assert [record.tool_name for record in result.action_history] == [
        "open_url",
        "fill",
        "click",
    ]
    assert "Results for: laptop" in result.final_observation.visible_text


@pytest.mark.asyncio
async def test_single_agent_stops_at_max_steps(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()
    agent = make_agent(runtime, ReobserveForeverLLM(), max_steps=2)

    await runtime.start()
    try:
        result = await agent.run(
            goal="Inspect the page.",
            target_url=fixture_url,
        )
    finally:
        await runtime.close()

    assert result.status == "max_steps_reached"
    assert result.tool_calls == 2
    assert "max_steps" in (result.error or "")


@pytest.mark.asyncio
async def test_single_agent_records_invalid_ref_as_tool_error(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()
    agent = make_agent(runtime, InvalidRefLLM(), max_steps=3)

    await runtime.start()
    try:
        result = await agent.run(
            goal="Click a missing element.",
            target_url=fixture_url,
        )
    finally:
        await runtime.close()

    assert result.status == "tool_error"
    assert result.tool_calls == 1
    assert "Unknown element ref" in (result.error or "")


def test_single_agent_requires_positive_step_budget() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()

    with pytest.raises(ValueError, match="positive"):
        SingleBrowserAgent(
            actor=BrowserActor(ReobserveForeverLLM()),
            observation_engine=engine,
            tools=BrowserToolExecutor(runtime, engine),
            max_steps=0,
        )

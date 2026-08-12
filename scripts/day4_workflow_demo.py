from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

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
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "day3_agent.html"
).as_uri()


class ScriptedDay4LLM:
    """Controlled Day 4 contract double; it never calls an external API."""

    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.plan_calls = 0
        self.actor_calls = 0

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        tool_names = {tool["function"]["name"] for tool in tools}
        if tool_names == {"submit_test_plan"}:
            self.plan_calls += 1
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

        self.actor_calls += 1
        actor_replies = [
            LLMReply(
                content="",
                tool_call=LLMToolCall(
                    name="open_url",
                    arguments={"url": self.target_url},
                ),
            ),
            LLMReply(content="DONE: Product Search is visible."),
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
            # A subsequent call is intentionally invalid: a third plan step
            # would be a test-double defect, not a hidden extra action.
        ]
        return actor_replies[self.actor_calls - 1]


async def main() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    llm = ScriptedDay4LLM(FIXTURE_URL)
    workflow = PlannedBrowserAgent(
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

    await runtime.start()
    try:
        result = await workflow.run(
            goal="Search for laptop and verify the result.",
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

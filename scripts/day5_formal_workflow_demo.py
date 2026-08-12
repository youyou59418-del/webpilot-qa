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


class ControlledRecoveryLLM:
    """Offline double that causes one stale-ref failure before recovery."""

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
                                "goal": "Search for laptop and reach results.",
                                "risk_level": "L0",
                                "success_criteria": [
                                    {
                                        "rule": "visible_text_contains",
                                        "expected": "Results for: laptop",
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


async def main() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    llm = ControlledRecoveryLLM(FIXTURE_URL)
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

    payload = result.as_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not result.passed:
        raise SystemExit(1)
    if not result.state or len(result.state.recovery_history) != 1:
        raise SystemExit("Expected exactly one recorded recovery event.")


if __name__ == "__main__":
    asyncio.run(main())

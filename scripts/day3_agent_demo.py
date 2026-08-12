from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from webpilot.agents.actor import BrowserActor
from webpilot.agents.loop import SingleBrowserAgent
from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.llm.adapter import LLMReply, LLMToolCall


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_URL = (
    PROJECT_ROOT / "tests" / "fixtures" / "day3_agent.html"
).as_uri()


class FixtureDemoLLM:
    """Controlled model double for offline loop-contract verification only."""

    def __init__(self) -> None:
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
                    arguments={"url": FIXTURE_URL},
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
                content="DONE: The visible result says Results for: laptop.",
            ),
        ]
        return replies[self.turn - 1]


async def main() -> None:
    runtime = BrowserRuntime()
    observation_engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, observation_engine)
    agent = SingleBrowserAgent(
        actor=BrowserActor(FixtureDemoLLM()),
        observation_engine=observation_engine,
        tools=tools,
        max_steps=6,
    )

    await runtime.start()
    try:
        result = await agent.run(
            goal=(
                "Search for laptop and finish only when the page says "
                "Results for: laptop."
            ),
            target_url=FIXTURE_URL,
        )
    finally:
        await runtime.close()

    if result.status != "completed":
        raise RuntimeError(f"Unexpected agent status: {result.status}")
    if "Results for: laptop" not in result.final_observation.visible_text:
        raise RuntimeError("Agent did not create the expected page state.")

    print("Day 3 agent loop contract PASSED")
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

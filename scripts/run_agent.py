from __future__ import annotations

import argparse
import asyncio
import json

from webpilot.agents.actor import BrowserActor
from webpilot.agents.loop import SingleBrowserAgent
from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.llm.adapter import OpenAICompatibleLLM


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Day 3 single browser agent against one target URL."
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument("--start-url", required=True)
    parser.add_argument("--max-steps", type=int, default=6)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    llm = OpenAICompatibleLLM.from_env()
    runtime = BrowserRuntime()
    observation_engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, observation_engine)
    agent = SingleBrowserAgent(
        actor=BrowserActor(llm),
        observation_engine=observation_engine,
        tools=tools,
        max_steps=args.max_steps,
    )

    await runtime.start()
    try:
        result = await agent.run(
            goal=args.goal,
            target_url=args.start_url,
        )
    finally:
        await runtime.close()

    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

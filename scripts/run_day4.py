from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from webpilot.agents.actor import BrowserActor
from webpilot.agents.loop import SingleBrowserAgent
from webpilot.agents.planned_loop import PlannedBrowserAgent
from webpilot.agents.planner import BrowserPlanner
from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.llm.adapter import OpenAICompatibleLLM
from webpilot.verifier.rules import RuleVerifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "day4" / "run.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Day 4 Planner -> Actor -> Verifier workflow."
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument("--start-url", required=True)
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        llm = OpenAICompatibleLLM.from_env()
    except RuntimeError as exc:
        print(f"LLM configuration error: {exc}", file=sys.stderr)
        return 2

    runtime = BrowserRuntime()
    observation_engine = ObservationEngine()
    agent = SingleBrowserAgent(
        actor=BrowserActor(llm),
        observation_engine=observation_engine,
        tools=BrowserToolExecutor(runtime, observation_engine),
        max_steps=args.max_steps,
    )
    workflow = PlannedBrowserAgent(
        planner=BrowserPlanner(llm),
        agent=agent,
        observation_engine=observation_engine,
        verifier=RuleVerifier(),
    )

    await runtime.start()
    try:
        result = await workflow.run(
            goal=args.goal,
            target_url=args.start_url,
        )
    finally:
        await runtime.close()

    payload = result.as_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Saved Day 4 run artifact to: {args.output}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

from __future__ import annotations

import asyncio
from pathlib import Path

from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_URL = (
    PROJECT_ROOT / "tests" / "fixtures" / "day3_agent.html"
).as_uri()


async def main() -> None:
    runtime = BrowserRuntime()
    observation_engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, observation_engine)

    await runtime.start()
    try:
        await tools.execute("open_url", {"url": FIXTURE_URL})
        observation = await observation_engine.observe(runtime)
        refs_by_name = {
            element.name: element.ref
            for element in observation.elements
        }

        await tools.execute(
            "fill",
            {
                "ref": refs_by_name["Search Products"],
                "value": "laptop",
            },
        )

        observation = await observation_engine.observe(runtime)
        refs_by_name = {
            element.name: element.ref
            for element in observation.elements
        }
        await tools.execute("click", {"ref": refs_by_name["Search"]})

        state = await tools.execute("get_page_state", {})
        result_text = state["observation"]["visible_text"]
        if "Results for: laptop" not in result_text:
            raise RuntimeError(f"Unexpected page state: {result_text!r}")

        print("Day 3 browser tool layer PASSED")
        print("Result: Results for: laptop")
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())

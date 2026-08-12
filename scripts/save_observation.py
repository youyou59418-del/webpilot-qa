import asyncio
from pathlib import Path

from webpilot.browser.observation import (
    ObservationEngine,
)
from webpilot.browser.runtime import (
    BrowserRuntime,
)


async def main() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()

    fixture = (
        Path(
            "tests/fixtures/"
            "day2_observation.html"
        )
        .resolve()
        .as_uri()
    )

    try:
        await runtime.start()
        await runtime.open_url(
            fixture
        )

        observation = await engine.observe(
            runtime
        )

        output = Path(
            "artifacts/day2/"
            "observation.json"
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_text(
            observation.model_dump_json(
                indent=2
            ),
            encoding="utf-8",
        )

        print(
            "Saved:",
            output
        )

    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())

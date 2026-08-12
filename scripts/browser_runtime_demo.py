import asyncio
from pathlib import Path

from webpilot.browser.runtime import BrowserRuntime


async def main() -> None:
    runtime = BrowserRuntime()

    fixture_path = (
        Path("tests/fixtures/day1_form.html")
        .resolve()
    )

    fixture_url = fixture_path.as_uri()

    try:
        print("Starting BrowserRuntime...")

        await runtime.start()

        print("Opening:", fixture_url)

        await runtime.open_url(
            fixture_url
        )

        print(
            "Title:",
            await runtime.title(),
        )

        await runtime.fill(
            "#name-input",
            "WebPilot",
        )

        print(
            "Filled input."
        )

        await runtime.click(
            "#submit-button"
        )

        print(
            "Clicked submit button."
        )

        result = await runtime.get_text(
            "#result"
        )

        print(
            "Result:",
            result,
        )

        screenshot = await runtime.screenshot(
            "artifacts/day1/browser-runtime-demo.png"
        )

        print(
            "Screenshot:",
            screenshot,
        )

        if result != "Hello, WebPilot!":
            raise RuntimeError(
                f"Unexpected result: {result}"
            )

        print(
            "BrowserRuntime demo PASSED"
        )

    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())

from pathlib import Path

import pytest

from webpilot.browser.runtime import BrowserRuntime


@pytest.fixture
def fixture_url() -> str:
    path = (
        Path("tests/fixtures/day1_form.html")
        .resolve()
    )

    return path.as_uri()


@pytest.mark.asyncio
async def test_browser_runtime_start_and_open(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()

    try:
        await runtime.start()

        await runtime.open_url(
            fixture_url
        )

        assert (
            await runtime.title()
            == "WebPilot Day1 Test"
        )

        current_url = (
            await runtime.current_url()
        )

        assert current_url.startswith(
            "file://"
        )

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_browser_runtime_fill_click_and_read(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()

    try:
        await runtime.start()

        await runtime.open_url(
            fixture_url
        )

        await runtime.fill(
            "#name-input",
            "WebPilot",
        )

        await runtime.click(
            "#submit-button"
        )

        result = await runtime.get_text(
            "#result"
        )

        assert (
            result
            == "Hello, WebPilot!"
        )

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_browser_runtime_screenshot(
    fixture_url: str,
    tmp_path: Path,
) -> None:
    runtime = BrowserRuntime()

    try:
        await runtime.start()

        await runtime.open_url(
            fixture_url
        )

        screenshot_path = (
            tmp_path / "runtime.png"
        )

        result = await runtime.screenshot(
            screenshot_path
        )

        assert result.exists()

        assert (
            result.stat().st_size
            > 0
        )

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_runtime_rejects_access_before_start() -> None:
    runtime = BrowserRuntime()

    with pytest.raises(
        RuntimeError,
        match="has not been started",
    ):
        _ = runtime.page

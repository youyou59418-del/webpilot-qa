import zipfile

import pytest

from webpilot.browser.runtime import BrowserRuntime


@pytest.mark.asyncio
async def test_runtime_persists_screenshot_and_playwright_trace(tmp_path) -> None:
    runtime = BrowserRuntime()
    await runtime.start()
    try:
        await runtime.start_trace()
        await runtime.page.set_content("<h1>Artifact proof</h1>")
        screenshot = await runtime.screenshot(tmp_path / "final.png")
        trace = await runtime.stop_trace(tmp_path / "trace.zip")
    finally:
        await runtime.close()

    assert screenshot.read_bytes().startswith(b"\x89PNG")
    assert zipfile.is_zipfile(trace)

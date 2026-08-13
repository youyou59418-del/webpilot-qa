import asyncio
import socket

import pytest
import uvicorn

from shopbench.app import create_app
from webpilot.browser.runtime import BrowserRuntime


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_resettable_shopbench_page_exposes_real_interactions() -> None:
    port = _unused_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    server_task = asyncio.create_task(server.serve())
    runtime = BrowserRuntime()
    try:
        for _ in range(50):
            if server.started:
                break
            if server_task.done():
                raise RuntimeError("ShopBench server exited before startup.")
            await asyncio.sleep(0.02)
        assert server.started

        await runtime.start()
        await runtime.open_url(f"http://127.0.0.1:{port}/?reset=1")
        assert await runtime.page.locator("h1").inner_text() == "ShopBench v1"
        await runtime.page.get_by_label("Search products").fill("laptop")
        assert await runtime.page.locator("#results-summary").inner_text() == "Results: 1 products"
        await runtime.page.get_by_role("button", name="Add Laptop Pro to cart").click()
        assert await runtime.page.locator("#cart-count").inner_text() == "1"
        await runtime.page.get_by_role("button", name="Reset benchmark state").click()
        assert await runtime.page.locator("#cart-count").inner_text() == "0"
        assert await runtime.page.locator("#results-summary").inner_text() == "Results: 10 products"
    finally:
        await runtime.close()
        server.should_exit = True
        await server_task

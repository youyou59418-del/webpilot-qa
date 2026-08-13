from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from webpilot.config import configure_playwright_browsers_path


class BrowserRuntime:
    """
    WebPilot-QA 的底层浏览器运行时。

    当前 Day 1 只负责最基础、确定性的浏览器操作：
    - 启动 Chromium
    - 创建独立 BrowserContext
    - 打开网页
    - 点击
    - 输入
    - 读取文本
    - 截图
    - 关闭浏览器

    Day 2 再在其上增加 Observation Engine。
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        viewport_width: int = 1440,
        viewport_height: int = 900,
    ) -> None:
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError(
                "BrowserRuntime has not been started. "
                "Call await runtime.start() first."
            )
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError(
                "BrowserRuntime has not been started. "
                "Call await runtime.start() first."
            )
        return self._context

    async def start(self) -> None:
        if self._page is not None:
            return

        if any(
            resource is not None
            for resource in (
                self._playwright,
                self._browser,
                self._context,
            )
        ):
            await self.close()

        configure_playwright_browsers_path()

        try:
            self._playwright = await async_playwright().start()

            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
            )

            self._context = await self._browser.new_context(
                viewport={
                    "width": self.viewport_width,
                    "height": self.viewport_height,
                }
            )

            self._page = await self._context.new_page()
        except Exception:
            await self.close()
            raise

    async def open_url(
        self,
        url: str,
        *,
        timeout_ms: int = 30_000,
    ) -> None:
        await self.page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )

    async def title(self) -> str:
        return await self.page.title()

    async def current_url(self) -> str:
        return self.page.url

    async def click(
        self,
        locator: str | Locator,
        *,
        timeout_ms: int = 10_000,
    ) -> None:
        target = (
            self.page.locator(locator)
            if isinstance(locator, str)
            else locator
        )
        await target.click(
            timeout=timeout_ms
        )

    async def fill(
        self,
        locator: str | Locator,
        value: str,
        *,
        timeout_ms: int = 10_000,
    ) -> None:
        target = (
            self.page.locator(locator)
            if isinstance(locator, str)
            else locator
        )
        await target.fill(
            value,
            timeout=timeout_ms,
        )

    async def select_option(
        self,
        locator: str | Locator,
        value: str,
        *,
        timeout_ms: int = 10_000,
    ) -> None:
        target = (
            self.page.locator(locator)
            if isinstance(locator, str)
            else locator
        )
        await target.select_option(
            label=value,
            timeout=timeout_ms,
        )

    async def get_text(
        self,
        locator: str,
        *,
        timeout_ms: int = 10_000,
    ) -> str:
        return await self.page.locator(
            locator
        ).inner_text(
            timeout=timeout_ms
        )

    async def screenshot(
        self,
        path: str | Path,
        *,
        full_page: bool = True,
    ) -> Path:
        output_path = Path(path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        await self.page.screenshot(
            path=str(output_path),
            full_page=full_page,
        )

        return output_path

    async def start_trace(self) -> None:
        await self.context.tracing.start(
            screenshots=True,
            snapshots=True,
            sources=False,
        )

    async def stop_trace(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await self.context.tracing.stop(path=str(output_path))
        return output_path

    async def close(self) -> None:
        self._page = None

        if self._context is not None:
            await self._context.close()
            self._context = None

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

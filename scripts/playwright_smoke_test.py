from pathlib import Path

from playwright.sync_api import sync_playwright

from webpilot.config import configure_playwright_browsers_path


ARTIFACT_DIR = Path("artifacts/day1")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    configure_playwright_browsers_path()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 900,
            }
        )

        page.goto(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=30_000,
        )

        print("Title:", page.title())
        print("URL:", page.url)

        screenshot_path = (
            ARTIFACT_DIR / "example.png"
        )

        page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )

        print(
            "Screenshot:",
            screenshot_path,
        )

        browser.close()

    print("Playwright smoke test PASSED")


if __name__ == "__main__":
    main()

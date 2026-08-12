from pathlib import Path

from webpilot.config import (
    PLAYWRIGHT_BROWSERS_PATH,
    WEBPILOT_BROWSERS_PATH,
    configure_playwright_browsers_path,
)


def test_explicit_playwright_path_is_preserved() -> None:
    environment = {
        PLAYWRIGHT_BROWSERS_PATH: "/custom/playwright-cache",
    }

    result = configure_playwright_browsers_path(
        environ=environment,
        candidates=(),
    )

    assert result == Path("/custom/playwright-cache")
    assert environment == {
        PLAYWRIGHT_BROWSERS_PATH: "/custom/playwright-cache",
    }


def test_webpilot_path_becomes_playwright_path() -> None:
    environment = {
        WEBPILOT_BROWSERS_PATH: "/configured/playwright-cache",
    }

    result = configure_playwright_browsers_path(
        environ=environment,
        candidates=(),
    )

    assert result == Path("/configured/playwright-cache")
    assert environment[PLAYWRIGHT_BROWSERS_PATH] == (
        "/configured/playwright-cache"
    )


def test_existing_candidate_is_discovered(tmp_path: Path) -> None:
    browser_cache = tmp_path / "playwright"
    browser_cache.mkdir()
    environment: dict[str, str] = {}

    result = configure_playwright_browsers_path(
        environ=environment,
        candidates=(browser_cache,),
    )

    assert result == browser_cache
    assert environment[PLAYWRIGHT_BROWSERS_PATH] == str(browser_cache)

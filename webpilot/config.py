from __future__ import annotations

import os
from collections.abc import MutableMapping, Sequence
from pathlib import Path


PLAYWRIGHT_BROWSERS_PATH = "PLAYWRIGHT_BROWSERS_PATH"
WEBPILOT_BROWSERS_PATH = "WEBPILOT_PLAYWRIGHT_BROWSERS_PATH"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BROWSER_CACHE_PATHS = (
    PROJECT_ROOT / ".cache" / "playwright",
    Path("/root/autodl-tmp/cache/playwright"),
)


def configure_playwright_browsers_path(
    *,
    environ: MutableMapping[str, str] | None = None,
    candidates: Sequence[Path] | None = None,
) -> Path | None:
    """Configure a project-owned Playwright browser-cache path when available.

    An explicit Playwright setting always wins.  For a fresh AutoDL shell, the
    project automatically discovers the data-disk cache used by this project,
    avoiding the transient and capacity-limited default under ``/root/.cache``.
    """
    environment = os.environ if environ is None else environ

    explicit_path = environment.get(PLAYWRIGHT_BROWSERS_PATH)
    if explicit_path:
        return Path(explicit_path).expanduser()

    configured_path = environment.get(WEBPILOT_BROWSERS_PATH)
    if configured_path:
        path = Path(configured_path).expanduser()
        environment[PLAYWRIGHT_BROWSERS_PATH] = str(path)
        return path

    paths_to_try = (
        DEFAULT_BROWSER_CACHE_PATHS
        if candidates is None
        else candidates
    )

    for candidate in paths_to_try:
        path = Path(candidate).expanduser()
        if path.is_dir():
            environment[PLAYWRIGHT_BROWSERS_PATH] = str(path)
            return path

    return None

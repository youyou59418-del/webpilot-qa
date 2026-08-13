from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class RegressionGenerationError(ValueError):
    pass


_SENSITIVE = re.compile(r"password|passcode|otp|verification|cvv|card|bank|passport", re.I)


def generate_pytest(*, trajectory: dict[str, Any], test_name: str) -> str:
    """Convert a verified, non-sensitive trajectory into an isolated Playwright test."""
    if trajectory.get("status") != "passed":
        raise RegressionGenerationError("Only a verified passed trajectory can generate a regression test.")
    state = trajectory.get("state")
    if not isinstance(state, dict) or not isinstance(state.get("target_url"), str):
        raise RegressionGenerationError("Trajectory must contain state.target_url.")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", test_name):
        raise RegressionGenerationError("test_name must be a safe Python identifier.")
    history = state.get("history")
    if not isinstance(history, list) or not history:
        raise RegressionGenerationError("Trajectory contains no successful actions.")
    lines = [
        "from playwright.async_api import async_playwright, expect",
        "import pytest",
        "from webpilot.config import configure_playwright_browsers_path",
        "",
        "@pytest.mark.asyncio",
        f"async def test_{test_name}() -> None:",
        "    configure_playwright_browsers_path()",
        "    async with async_playwright() as playwright:",
        "        browser = await playwright.chromium.launch(headless=True)",
        "        context = await browser.new_context()",
        "        page = await context.new_page()",
        "        try:",
        f"            await page.goto({state['target_url']!r}, wait_until='domcontentloaded')",
    ]
    for action in history:
        if not isinstance(action, dict):
            raise RegressionGenerationError("Invalid action record.")
        lines.extend(_render_action(action))
    for verification in state.get("step_verifications", []):
        if isinstance(verification, dict):
            lines.extend(_render_verification(verification))
    lines.extend([
        "        finally:",
        "            await context.close()",
        "            await browser.close()",
        "",
    ])
    return "\n".join(lines)


def write_pytest(*, trajectory_path: Path, output_path: Path, test_name: str) -> Path:
    trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
    if not isinstance(trajectory, dict):
        raise RegressionGenerationError("Trajectory root must be an object.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_pytest(trajectory=trajectory, test_name=test_name), encoding="utf-8")
    return output_path


def _render_action(action: dict[str, Any]) -> list[str]:
    if not isinstance(action.get("result"), dict) or action["result"].get("ok") is not True:
        raise RegressionGenerationError("Only successful actions are eligible for regression generation.")
    tool = action.get("tool_name")
    arguments = action.get("arguments")
    target = action.get("semantic_target")
    if not isinstance(arguments, dict) or not isinstance(target, dict):
        raise RegressionGenerationError("Action lacks semantic target data.")
    if tool == "open_url":
        url = arguments.get("url")
        if not isinstance(url, str):
            raise RegressionGenerationError("open_url requires a concrete URL.")
        return [f"            await page.goto({url!r}, wait_until='domcontentloaded')"]
    locator = _locator(target)
    if tool == "click":
        return [f"            await {locator}.click()"]
    if tool == "fill":
        value = arguments.get("value")
        name = target.get("name") or target.get("placeholder") or ""
        if not isinstance(value, str) or value == "[REDACTED]" or _SENSITIVE.search(str(name)):
            raise RegressionGenerationError("Sensitive or redacted fill values cannot be generated.")
        return [f"            await {locator}.fill({value!r})"]
    raise RegressionGenerationError(f"Unsupported browser tool for regression generation: {tool!r}")


def _locator(target: dict[str, Any]) -> str:
    role = target.get("role")
    name = target.get("name")
    placeholder = target.get("placeholder")
    if isinstance(role, str) and role and isinstance(name, str) and name:
        return f"page.get_by_role({role!r}, name={name!r})"
    if isinstance(placeholder, str) and placeholder:
        return f"page.get_by_placeholder({placeholder!r})"
    raise RegressionGenerationError("Action target needs an accessible role/name or placeholder.")


def _render_verification(verification: dict[str, Any]) -> list[str]:
    result = verification.get("result")
    if not isinstance(result, dict) or result.get("status") != "PASS":
        raise RegressionGenerationError("Only passing verifier evidence can be generated.")
    lines: list[str] = []
    for evidence in result.get("evidence", []):
        if not isinstance(evidence, dict) or not evidence.get("passed"):
            continue
        rule = evidence.get("rule")
        expected = evidence.get("expected")
        if not isinstance(expected, str):
            continue
        if rule == "visible_text_contains":
            lines.append(f"            await expect(page.get_by_text({expected!r}, exact=False)).to_be_visible()")
        elif rule == "url_contains":
            lines.append(f"            assert {expected!r} in page.url")
    return lines

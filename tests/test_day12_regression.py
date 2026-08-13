import subprocess
import sys
from pathlib import Path

import pytest

from webpilot.regression.generator import RegressionGenerationError, generate_pytest, write_pytest


def trajectory(target_url: str) -> dict[str, object]:
    return {
        "status": "passed",
        "state": {
            "target_url": target_url,
            "history": [
                {
                    "tool_name": "fill",
                    "arguments": {"ref": "e1", "value": "laptop"},
                    "semantic_target": {"role": "textbox", "name": "Search Products", "placeholder": None},
                    "result": {"ok": True},
                },
                {
                    "tool_name": "click",
                    "arguments": {"ref": "e2"},
                    "semantic_target": {"role": "button", "name": "Search", "placeholder": None},
                    "result": {"ok": True},
                },
            ],
            "step_verifications": [
                {"result": {"status": "PASS", "evidence": [{"rule": "visible_text_contains", "expected": "Results for: laptop", "passed": True}]}},
            ],
        },
    }


def test_generator_rejects_unverified_and_sensitive_trajectories() -> None:
    with pytest.raises(RegressionGenerationError, match="verified passed"):
        generate_pytest(trajectory={"status": "failed"}, test_name="bad")
    unsafe = trajectory("file:///tmp/test.html")
    unsafe["state"]["history"][0]["semantic_target"]["name"] = "Password"  # type: ignore[index]
    with pytest.raises(RegressionGenerationError, match="Sensitive"):
        generate_pytest(trajectory=unsafe, test_name="unsafe")


def test_generated_playwright_regression_passes_three_fresh_runs(tmp_path) -> None:
    fixture_url = (Path("tests/fixtures/day3_agent.html").resolve()).as_uri()
    trajectory_path = tmp_path / "workflow.json"
    trajectory_path.write_text(__import__("json").dumps(trajectory(fixture_url)), encoding="utf-8")
    generated = write_pytest(
        trajectory_path=trajectory_path,
        output_path=tmp_path / "test_generated_search.py",
        test_name="generated_search",
    )
    assert "get_by_role('textbox', name='Search Products')" in generated.read_text()
    for _ in range(3):
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(generated)],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

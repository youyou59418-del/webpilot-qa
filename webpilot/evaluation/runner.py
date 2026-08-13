from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from pathlib import Path
from typing import Any, Literal

from shopbench.tasks import BenchTask
from webpilot.evaluation.models import EvaluationOutcome, EvaluationReport


class EvaluationRunner:
    """Runs ShopBench through the durable API and emits auditable reports."""

    def __init__(
        self,
        *,
        api_url: str,
        shopbench_url: str,
        poll_interval_s: float = 0.25,
        timeout_s: float = 180.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.shopbench_url = shopbench_url.rstrip("/")
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s

    def dry_run(
        self,
        *,
        tasks: list[BenchTask],
        variant: str,
        model_name: str,
    ) -> EvaluationReport:
        now = datetime.now(UTC)
        return EvaluationReport(
            variant=variant,
            model_name=model_name,
            execution_mode="dry_run",
            started_at=now,
            completed_at=now,
            outcomes=[
                EvaluationOutcome(
                    task_id=task.id,
                    difficulty=task.difficulty,
                    status="skipped",
                    duration_ms=0,
                    tool_calls=0,
                    retries=0,
                    note="Dry-run validates the benchmark contract; it is not a model metric.",
                )
                for task in tasks
            ],
            metadata={"task_count": len(tasks)},
        )

    def run_live(
        self,
        *,
        tasks: list[BenchTask],
        variant: str,
        model_name: str,
        max_steps: int = 12,
        max_retries: int = 2,
    ) -> EvaluationReport:
        started_at = datetime.now(UTC)
        outcomes = [
            self._run_one(
                task=task,
                variant=variant,
                max_steps=max_steps,
                max_retries=max_retries,
            )
            for task in tasks
        ]
        return EvaluationReport(
            variant=variant,
            model_name=model_name,
            execution_mode="live_model",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            outcomes=outcomes,
            metadata={"task_count": len(tasks), "api_url": self.api_url},
        )

    def _run_one(
        self,
        *,
        task: BenchTask,
        variant: str,
        max_steps: int,
        max_retries: int,
    ) -> EvaluationOutcome:
        payload = {
            "goal": self._benchmark_goal(task),
            "target_url": self.shopbench_url + task.start_path,
            "max_steps": max_steps,
            "max_retries": max_retries,
            "variant": variant,
        }
        started = time.perf_counter()
        try:
            created = self._request("POST", "/runs", payload)
            run_id = str(created["run_id"])
            record = self._wait_for_terminal(run_id)
        except (KeyError, RuntimeError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            return EvaluationOutcome(
                task_id=task.id,
                difficulty=task.difficulty,
                status="failed",
                duration_ms=round((time.perf_counter() - started) * 1000),
                tool_calls=0,
                retries=0,
                failure_category="runtime",
                note=f"{type(exc).__name__}: {exc}",
            )

        result = record.get("result") if isinstance(record.get("result"), dict) else {}
        workflow_status = result.get("status")
        state_mismatch: str | None = None
        if record.get("status") == "approval_required":
            status: Literal["passed", "failed", "blocked_by_safety", "skipped"] = "blocked_by_safety"
        elif record.get("status") == "completed" and workflow_status == "passed":
            state_mismatch = self._validate_shopbench_state(
                task,
                final_shopbench_state=(
                    result.get("shopbench_state")
                    if isinstance(result.get("shopbench_state"), dict)
                    else None
                ),
            )
            status = "passed" if state_mismatch is None else "failed"
        else:
            status = "failed"
        state = result.get("state") if isinstance(result.get("state"), dict) else {}
        history = state.get("history") if isinstance(state.get("history"), list) else []
        if not history:
            history = result.get("action_history") if isinstance(result.get("action_history"), list) else []
        recovery = state.get("recovery_history") if isinstance(state.get("recovery_history"), list) else []
        return EvaluationOutcome(
            task_id=task.id,
            difficulty=task.difficulty,
            status=status,
            duration_ms=round((time.perf_counter() - started) * 1000),
            tool_calls=len(history),
            retries=len(recovery),
            run_id=run_id,
            failure_category=(
                None
                if status == "passed"
                else ("benchmark_state_mismatch" if state_mismatch else str(workflow_status or record.get("status")))
            ),
            note=state_mismatch,
        )

    def _validate_shopbench_state(
        self,
        task: BenchTask,
        *,
        final_shopbench_state: dict[str, Any] | None,
    ) -> str | None:
        """Independently compare the page's controlled state to the task oracle.

        Model-produced success criteria decide workflow completion; ShopBench's
        public expected state decides the evaluation score.  The executor
        captures the page state from its isolated browser context before that
        context closes, so default option text cannot be mistaken for a
        completed filter/search action.
        """
        final_state = final_shopbench_state
        if final_state is None:
            return "Workflow did not record a ShopBench final state."
        mismatches = []
        for key, expected in task.expected_state.items():
            actual = final_state.get(key)
            if key == "cart_contains":
                matched = expected in actual if isinstance(actual, list) else False
            else:
                matched = actual == expected
            if not matched:
                mismatches.append(f"{key}: expected {expected!r}, observed {actual!r}")
        return "; ".join(mismatches) if mismatches else None

    @staticmethod
    def _benchmark_goal(task: BenchTask) -> str:
        """Give the planner the public oracle without mutating the task itself.

        ShopBench is a controlled evaluation station. Its expected state is
        part of the task specification, so exposing it in the run goal avoids
        asking a small planner to invent fragile verifier text from prose.
        Production callers keep sending a normal human goal.
        """
        expected_state = json.dumps(task.expected_state, ensure_ascii=False, sort_keys=True)
        return (
            f"{task.goal}\n\n"
            "BENCHMARK ACCEPTANCE STATE (public task oracle):\n"
            f"{expected_state}\n"
            "Use these exact values to create only observable, deterministic success criteria."
        )

    def _wait_for_terminal(self, run_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            record = self._request("GET", f"/runs/{run_id}")
            if record.get("status") in {"completed", "failed", "cancelled", "approval_required"}:
                return record
            time.sleep(self.poll_interval_s)
        raise RuntimeError(f"Timed out waiting for run {run_id}.")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.api_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict):
            raise RuntimeError("API response must be an object.")
        return decoded


def write_report(report: EvaluationReport, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    json_path = output_dir / "report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output_dir / "outcomes.csv"
    headers = ["task_id", "difficulty", "status", "duration_ms", "tool_calls", "retries", "run_id", "failure_category", "note"]
    rows = [",".join(headers)]
    for outcome in report.outcomes:
        values = [str(getattr(outcome, header) or "").replace('"', '""') for header in headers]
        rows.append(",".join(f'"{value}"' for value in values))
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    markdown_path = output_dir / "summary.md"
    rate = "not measured" if report.success_rate is None else f"{report.success_rate:.1%}"
    markdown_path.write_text(
        "\n".join([
            "# ShopBench evaluation report",
            "",
            f"- Variant: `{report.variant}`",
            f"- Model: `{report.model_name}`",
            f"- Execution mode: `{report.execution_mode}`",
            f"- Attempted: {report.attempted_count}/{len(report.outcomes)}",
            f"- Passed: {report.passed_count}",
            f"- Success rate: {rate}",
            "",
            "Do not compare dry-run results as model performance.",
        ]) + "\n",
        encoding="utf-8",
    )
    chart_path = output_dir / "summary.svg"
    total = len(report.outcomes)
    passed = report.passed_count
    blocked = sum(item.status == "blocked_by_safety" for item in report.outcomes)
    failed = sum(item.status == "failed" for item in report.outcomes)
    scale = 0 if total == 0 else 360 / total
    bars = [
        ("Passed", passed, "#16803c"),
        ("Safety blocked", blocked, "#b7791f"),
        ("Failed", failed, "#c53030"),
    ]
    rows = []
    for index, (label, value, color) in enumerate(bars):
        y = 54 + index * 44
        rows.append(
            f'<text x="16" y="{y + 16}" font-size="14">{label}: {value}</text>'
            f'<rect x="150" y="{y}" width="{value * scale:.1f}" height="24" fill="{color}" />'
        )
    chart_path.write_text(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"560\" height=\"210\" "
        "viewBox=\"0 0 560 210\">"
        "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>"
        f"<text x=\"16\" y=\"28\" font-size=\"18\" font-weight=\"bold\">ShopBench: {report.variant}</text>"
        f"<text x=\"16\" y=\"46\" font-size=\"12\">{report.execution_mode}; tasks={total}</text>"
        + "".join(rows)
        + "</svg>\n",
        encoding="utf-8",
    )
    return {"json": json_path, "csv": csv_path, "markdown": markdown_path, "chart": chart_path}

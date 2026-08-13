from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from webpilot.artifacts.store import ArtifactReference, ArtifactStore
from webpilot.runs.models import RunEvent, RunRecord


def build_console_view(
    *,
    record: RunRecord,
    events: list[RunEvent],
    artifact_store: ArtifactStore,
) -> dict[str, Any]:
    """Project a durable run into the read-only Day 9 console contract."""

    references = artifact_store.list_run(record.run_id)
    artifacts = [reference.__dict__ for reference in references]
    workflow = _workflow_payload(record=record, artifact_store=artifact_store)
    state = workflow.get("state") if isinstance(workflow, dict) else None
    if not isinstance(state, dict):
        state = {}
    history = _as_list(state.get("history"))
    recovery_history = _as_list(state.get("recovery_history"))
    step_verifications = _as_list(state.get("step_verifications"))
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else None
    screenshot = _find_artifact(references, suffix=".png")
    trace = _find_artifact(references, suffix=".zip")

    duration_ms = _duration_ms(record, workflow)
    return {
        "run": ArtifactStore.redact(record.model_dump(mode="json")),
        "events": [event.model_dump(mode="json") for event in events],
        "plan": plan,
        "action_trace": ArtifactStore.redact(history),
        "verifier_evidence": ArtifactStore.redact(step_verifications),
        "recovery_history": ArtifactStore.redact(recovery_history),
        "current_screenshot": screenshot.__dict__ if screenshot else None,
        "trace": trace.__dict__ if trace else None,
        "metrics": {
            "duration_ms": duration_ms,
            "tool_calls": len(history),
            "retries": len(recovery_history),
        },
        "artifacts": artifacts,
    }


def _workflow_payload(
    *,
    record: RunRecord,
    artifact_store: ArtifactStore,
) -> dict[str, Any]:
    if isinstance(record.result, dict) and "state" in record.result:
        return record.result
    try:
        path = artifact_store.existing_path(run_id=record.run_id, name="workflow.json")
    except FileNotFoundError:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _find_artifact(
    references: list[ArtifactReference],
    *,
    suffix: str,
) -> ArtifactReference | None:
    for reference in references:
        if reference.name.endswith(suffix):
            return reference
    return None


def _duration_ms(record: RunRecord, workflow: dict[str, Any]) -> int:
    candidate = workflow.get("duration_ms")
    if isinstance(candidate, int) and candidate >= 0:
        return candidate
    start = record.created_at.astimezone(UTC)
    end = record.updated_at.astimezone(UTC)
    return max(0, round((end - start).total_seconds() * 1000))


def _as_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

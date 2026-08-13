import json

import pytest

from webpilot.artifacts.store import ArtifactStore


def test_artifacts_redact_secrets_and_stay_inside_run_directory(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    store.write_json(
        run_id="run-1",
        name="request.json",
        payload={"password": "hidden", "nested": {"token": "hidden"}, "goal": "safe"},
    )

    payload = json.loads((tmp_path / "artifacts" / "run-1" / "request.json").read_text())
    assert payload["password"] == "[REDACTED]"
    assert payload["nested"]["token"] == "[REDACTED]"
    assert payload["goal"] == "safe"

    with pytest.raises(ValueError):
        store.write_text(run_id="../escape", name="bad.txt", text="x")
    with pytest.raises(ValueError):
        store.write_text(run_id="run-1", name="../bad.txt", text="x")

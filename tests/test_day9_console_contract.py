import httpx
import pytest

from webpilot.artifacts.store import ArtifactStore
from webpilot.runs.models import RunStatus, WorkerExecutionResult
from webpilot.service.api import create_app
from webpilot.service.store import SQLiteRunStore
from webpilot.service.worker import RunWorker


class ConsoleExecutor:
    async def execute(self, record, *, cancel_requested):
        return WorkerExecutionResult(
            status=RunStatus.COMPLETED,
            result={
                "status": "passed",
                "duration_ms": 73,
                "state": {
                    "plan": {"steps": [{"id": "step-1", "goal": "Search catalog"}]},
                    "history": [{"tool_name": "fill", "arguments": {"value": "private"}}],
                    "step_verifications": [{"plan_step_id": "step-1", "result": {"status": "PASS"}}],
                    "recovery_history": [{"plan_step_id": "step-1", "outcome": "recovered"}],
                },
            },
        )


@pytest.mark.asyncio
async def test_console_projection_is_server_authoritative_and_redacted(tmp_path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    worker = RunWorker(store=store, artifact_store=artifacts, executor=ConsoleExecutor())
    app = create_app(store=store, artifact_store=artifacts, worker=worker)
    await worker.start()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post("/runs", json={"goal": "search", "target_url": "http://shopbench.test"})
            run_id = created.json()["run_id"]
            await worker.wait_for_idle()
            artifacts.write_text(run_id=run_id, name="final.png", text="image-placeholder")
            artifacts.write_text(run_id=run_id, name="trace.zip", text="trace-placeholder")

            view = await client.get(f"/runs/{run_id}/console")
            assert view.status_code == 200
            payload = view.json()
            assert payload["run"]["status"] == "completed"
            assert payload["plan"]["steps"][0]["id"] == "step-1"
            assert payload["metrics"] == {"duration_ms": 73, "tool_calls": 1, "retries": 1}
            assert payload["action_trace"][0]["arguments"]["value"] == "[REDACTED]"
            assert payload["current_screenshot"]["name"] == "final.png"
            assert payload["trace"]["name"] == "trace.zip"
            artifact = await client.get(f"/runs/{run_id}/artifacts/final.png")
            assert artifact.text == "image-placeholder"
            assert (await client.get(f"/runs/{run_id}/artifacts/../request.json")).status_code == 404
    finally:
        await worker.stop()

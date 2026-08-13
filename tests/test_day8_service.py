import asyncio

import httpx
import pytest

from webpilot.artifacts.store import ArtifactStore
from webpilot.runs.models import RunRequest, RunStatus, WorkerExecutionResult
from webpilot.safety.models import ApprovalRequest, RiskLevel, SafetyTarget
from webpilot.service.api import create_app
from webpilot.service.store import SQLiteRunStore
from webpilot.service.worker import RunWorker


class CompletedExecutor:
    async def execute(self, record, *, cancel_requested):
        return WorkerExecutionResult(
            status=RunStatus.CANCELLED if cancel_requested() else RunStatus.COMPLETED,
            result={"run_id": record.run_id, "message": "done"},
        )


class ApprovalExecutor:
    async def execute(self, record, *, cancel_requested):
        if not record.approved_fingerprints:
            return WorkerExecutionResult(
                status=RunStatus.APPROVAL_REQUIRED,
                result={"stage": "awaiting_approval"},
                approval=ApprovalRequest(
                    request_id="approval-1",
                    fingerprint="stable-delete-fingerprint",
                    risk_level=RiskLevel.L3,
                    tool_name="click",
                    target=SafetyTarget(role="button", name="Delete account"),
                    reason="Destructive action",
                ),
            )
        return WorkerExecutionResult(status=RunStatus.COMPLETED, result={"approved": True})


class BlockingExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, record, *, cancel_requested):
        self.started.set()
        while not cancel_requested():
            await asyncio.sleep(0.01)
        return WorkerExecutionResult(status=RunStatus.CANCELLED, result={"cancelled": True})


async def make_service(tmp_path, executor):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    worker = RunWorker(store=store, artifact_store=artifacts, executor=executor)
    await worker.start()
    app = create_app(
        store=store,
        artifact_store=artifacts,
        executor=executor,
        worker=worker,
    )
    return worker, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def request_payload() -> dict[str, object]:
    return {"goal": "check a page", "target_url": "https://example.test", "max_steps": 3}


@pytest.mark.asyncio
async def test_completed_run_has_events_and_redacted_artifacts(tmp_path) -> None:
    worker, client = await make_service(tmp_path, CompletedExecutor())
    try:
        response = await client.post("/runs", json=request_payload())
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        await worker.wait_for_idle()

        status = await client.get(f"/runs/{run_id}")
        assert status.json()["status"] == "completed"
        events = await client.get(f"/runs/{run_id}/events")
        assert [item["kind"] for item in events.json()] == ["queued", "started", "completed"]
        artifacts = await client.get(f"/runs/{run_id}/artifacts")
        assert {item["name"] for item in artifacts.json()} >= {"request.json", "result.json", "events.json"}
        stream = await client.get(f"/runs/{run_id}/events/stream?once=true")
        assert "event: completed" in stream.text
    finally:
        await client.aclose()
        await worker.stop()


@pytest.mark.asyncio
async def test_approval_requeues_then_completes(tmp_path) -> None:
    worker, client = await make_service(tmp_path, ApprovalExecutor())
    try:
        created = await client.post("/runs", json=request_payload())
        run_id = created.json()["run_id"]
        await worker.wait_for_idle()
        paused = await client.get(f"/runs/{run_id}")
        assert paused.json()["status"] == "approval_required"
        assert paused.json()["approval"]["fingerprint"] == "stable-delete-fingerprint"

        approved = await client.post(f"/runs/{run_id}/approve")
        assert approved.status_code == 200
        await worker.wait_for_idle()
        final = await client.get(f"/runs/{run_id}")
        assert final.json()["status"] == "completed"
        events = await client.get(f"/runs/{run_id}/events")
        assert "approved" in [item["kind"] for item in events.json()]
    finally:
        await client.aclose()
        await worker.stop()


@pytest.mark.asyncio
async def test_running_run_can_be_cancelled(tmp_path) -> None:
    executor = BlockingExecutor()
    worker, client = await make_service(tmp_path, executor)
    try:
        created = await client.post("/runs", json=request_payload())
        run_id = created.json()["run_id"]
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        cancelled = await client.post(f"/runs/{run_id}/cancel")
        assert cancelled.json()["cancel_requested"] is True
        await worker.wait_for_idle()
        final = await client.get(f"/runs/{run_id}")
        assert final.json()["status"] == "cancelled"
    finally:
        await client.aclose()
        await worker.stop()

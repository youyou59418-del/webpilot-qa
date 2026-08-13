from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from webpilot.artifacts.store import ArtifactStore
from webpilot.runs.models import RunRequest, RunStatus, WorkerExecutionResult
from webpilot.service.api import create_app
from webpilot.service.postgres_store import PostgreSQLRunStore
from webpilot.service.queue import RedisRunQueue
from webpilot.service.worker import RunWorker

TEST_DATABASE_URL = os.environ.get("WEBPILOT_TEST_DATABASE_URL", "")
TEST_REDIS_URL = os.environ.get("WEBPILOT_TEST_REDIS_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or not TEST_REDIS_URL,
    reason="Isolated PostgreSQL/Redis integration environment is not configured.",
)


class CompletedExecutor:
    async def execute(self, record, *, cancel_requested):
        status = RunStatus.CANCELLED if cancel_requested() else RunStatus.COMPLETED
        return WorkerExecutionResult(
            status=status,
            result={"run_id": record.run_id, "executor": "completed"},
        )


@pytest.mark.asyncio
async def test_postgres_and_redis_back_the_durable_api(tmp_path: Path) -> None:
    """State/events live in the isolated database; Redis only wakes a worker."""
    store = PostgreSQLRunStore(TEST_DATABASE_URL)
    queue = RedisRunQueue(
        redis_url=TEST_REDIS_URL,
        key=f"webpilot:test-queue:{uuid4()}",
    )
    artifacts = ArtifactStore(tmp_path / "artifacts")
    executor = CompletedExecutor()
    worker = RunWorker(store=store, artifact_store=artifacts, executor=executor, queue=queue)
    await worker.start()
    app = create_app(store=store, artifact_store=artifacts, executor=executor, worker=worker)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        created = await client.post(
            "/runs",
            json={"goal": "durable control-plane test", "target_url": "http://example.test"},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        await worker.wait_for_idle()

        record = (await client.get(f"/runs/{run_id}")).json()
        events = (await client.get(f"/runs/{run_id}/events")).json()
        assert record["status"] == "completed"
        assert [event["kind"] for event in events] == ["queued", "started", "completed"]
        assert await queue._require_client().llen(queue.key) == 0
    finally:
        await client.aclose()
        await worker.stop()


def test_postgres_requeues_interrupted_running_run_in_isolated_database() -> None:
    store = PostgreSQLRunStore(TEST_DATABASE_URL)
    record = store.create_run(
        request=RunRequest(goal="restart recovery", target_url="http://example.test"),
        artifact_dir="/tmp/webpilot-postgres-recovery",
    )
    assert store.claim_run(record.run_id) is not None

    assert store.recover_interrupted_runs() == [record.run_id]
    recovered = store.get_run(record.run_id)
    assert recovered.status is RunStatus.QUEUED
    assert [event.kind for event in store.list_events(record.run_id)] == [
        "queued",
        "started",
        "requeued_after_restart",
    ]


@pytest.mark.asyncio
async def test_redis_worker_discards_stale_message_and_processes_next_run(tmp_path: Path) -> None:
    store = PostgreSQLRunStore(TEST_DATABASE_URL)
    queue = RedisRunQueue(
        redis_url=TEST_REDIS_URL,
        key=f"webpilot:stale-queue:{uuid4()}",
    )
    artifacts = ArtifactStore(tmp_path / "artifacts")
    worker = RunWorker(store=store, artifact_store=artifacts, executor=CompletedExecutor(), queue=queue)
    await worker.start()
    try:
        await queue.enqueue("missing-run-id")
        record = store.create_run(
            request=RunRequest(goal="after stale message", target_url="http://example.test"),
            artifact_dir=str(artifacts.root),
        )
        await worker.enqueue(record.run_id)
        await worker.wait_for_idle()
        assert store.get_run(record.run_id).status is RunStatus.COMPLETED
        assert worker._task is not None and not worker._task.done()
    finally:
        await worker.stop()

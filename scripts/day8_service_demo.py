"""Day 8 durable queue/worker demonstration without an external model."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from webpilot.artifacts.store import ArtifactStore
from webpilot.runs.models import RunRequest, RunStatus, WorkerExecutionResult
from webpilot.service.store import SQLiteRunStore
from webpilot.service.worker import RunWorker


class DemoExecutor:
    async def execute(self, record, *, cancel_requested):
        if cancel_requested():
            return WorkerExecutionResult(status=RunStatus.CANCELLED)
        return WorkerExecutionResult(
            status=RunStatus.COMPLETED,
            result={"message": "Day 8 worker completed the queued run."},
        )


async def run_demo(root: Path) -> None:
    store = SQLiteRunStore(root / "runs.sqlite")
    artifacts = ArtifactStore(root / "artifacts")
    worker = RunWorker(store=store, artifact_store=artifacts, executor=DemoExecutor())
    await worker.start()
    try:
        record = store.create_run(
            request=RunRequest(goal="demonstrate durable worker", target_url="https://example.test"),
            artifact_dir=str(artifacts.root),
        )
        await worker.enqueue(record.run_id)
        await worker.wait_for_idle()
        final = store.get_run(record.run_id)
        print(json.dumps(final.model_dump(mode="json"), ensure_ascii=False, indent=2))
        print("artifacts:", [item.path for item in artifacts.list_run(record.run_id)])
    finally:
        await worker.stop()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="webpilot-day8-") as directory:
        asyncio.run(run_demo(Path(directory)))


if __name__ == "__main__":
    main()

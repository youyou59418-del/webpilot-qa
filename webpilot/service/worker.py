from __future__ import annotations

import asyncio

from webpilot.artifacts.store import ArtifactStore
from webpilot.runs.models import RunRecord, RunStatus
from webpilot.service.executor import RunExecutor
from webpilot.service.store import SQLiteRunStore


class RunWorker:
    """Single-process async worker; browser work is never executed in HTTP handlers."""

    def __init__(
        self,
        *,
        store: SQLiteRunStore,
        artifact_store: ArtifactStore,
        executor: RunExecutor,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.executor = executor
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        for run_id in self.store.list_queued_run_ids():
            await self._queue.put(run_id)
        self._task = asyncio.create_task(self._consume(), name="webpilot-run-worker")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def enqueue(self, run_id: str) -> None:
        await self._queue.put(run_id)

    async def wait_for_idle(self) -> None:
        await self._queue.join()

    async def _consume(self) -> None:
        while not self._stopping:
            run_id = await self._queue.get()
            try:
                await self._execute_one(run_id)
            finally:
                self._queue.task_done()

    async def _execute_one(self, run_id: str) -> None:
        record = self.store.claim_run(run_id)
        if record is None or record.status != RunStatus.RUNNING:
            return
        self._write_request_artifact(record)

        try:
            outcome = await self.executor.execute(
                record,
                cancel_requested=lambda: self.store.is_cancel_requested(run_id),
            )
        except Exception as exc:
            outcome_status = RunStatus.FAILED
            outcome_payload: dict[str, object] = {
                "error": f"{type(exc).__name__}: {exc}"
            }
            approval = None
        else:
            outcome_status = outcome.status
            outcome_payload = outcome.result
            approval = outcome.approval

        if self.store.is_cancel_requested(run_id) or outcome_status == RunStatus.CANCELLED:
            final = self.store.finish(
                run_id=run_id,
                status=RunStatus.CANCELLED,
                result=outcome_payload,
            )
        elif outcome_status == RunStatus.APPROVAL_REQUIRED:
            if approval is None:
                final = self.store.finish(
                    run_id=run_id,
                    status=RunStatus.FAILED,
                    result={
                        "error": "Executor returned approval_required without approval payload."
                    },
                )
            else:
                final = self.store.require_approval(
                    run_id=run_id,
                    approval=approval,
                    result=outcome_payload,
                )
        elif outcome_status == RunStatus.COMPLETED:
            final = self.store.finish(
                run_id=run_id,
                status=RunStatus.COMPLETED,
                result=outcome_payload,
            )
        else:
            final = self.store.finish(
                run_id=run_id,
                status=RunStatus.FAILED,
                result=outcome_payload,
            )

        self.artifact_store.write_json(
            run_id=run_id,
            name="result.json",
            payload=final.result or {},
        )
        self.artifact_store.write_json(
            run_id=run_id,
            name="events.json",
            payload=[
                event.model_dump(mode="json")
                for event in self.store.list_events(run_id)
            ],
        )

    def _write_request_artifact(self, record: RunRecord) -> None:
        self.artifact_store.create_run(record.run_id)
        self.artifact_store.write_json(
            run_id=record.run_id,
            name="request.json",
            payload=record.request,
        )

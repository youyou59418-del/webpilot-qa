from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from webpilot.artifacts.store import ArtifactStore
from webpilot.runs.models import RunEvent, RunRecord, RunStatus
from webpilot.safety.models import ApprovalRequest
from webpilot.service.executor import RunExecutor
from webpilot.service.queue import InMemoryRunQueue, RunQueue
from webpilot.service.store import RunNotFoundError


logger = logging.getLogger(__name__)


class RunStore(Protocol):
    def list_queued_run_ids(self) -> list[str]: ...
    def claim_run(self, run_id: str) -> RunRecord | None: ...
    def is_cancel_requested(self, run_id: str) -> bool: ...
    def require_approval(self, *, run_id: str, approval: ApprovalRequest, result: dict[str, object]) -> RunRecord: ...
    def finish(self, *, run_id: str, status: RunStatus, result: dict[str, object]) -> RunRecord: ...
    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[RunEvent]: ...


class RunWorker:
    """Durable worker: state lives in the store, queue entries only wake workers."""

    def __init__(
        self,
        *,
        store: RunStore,
        artifact_store: ArtifactStore,
        executor: RunExecutor,
        queue: RunQueue | None = None,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.executor = executor
        self.queue = queue or InMemoryRunQueue()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        await self.queue.start()
        recover = getattr(self.store, "recover_interrupted_runs", None)
        recovered_ids = list(recover()) if callable(recover) else []
        for run_id in [*recovered_ids, *self.store.list_queued_run_ids()]:
            await self.queue.enqueue(run_id)
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
        await self.queue.close()

    async def enqueue(self, run_id: str) -> None:
        await self.queue.enqueue(run_id)

    async def wait_for_idle(self) -> None:
        await self.queue.wait_for_idle()

    async def _consume(self) -> None:
        while not self._stopping:
            run_id = await self.queue.dequeue()
            try:
                await self._execute_one(run_id)
            except RunNotFoundError:
                # Redis is only a wake-up transport. A stale notification can
                # legitimately outlive a deleted test/benchmark row; it must
                # not terminate the sole worker or block later run IDs.
                logger.warning("Discarded stale queue notification for run %s", run_id)
            except Exception:
                # A single executor/store failure is recorded by _execute_one
                # where possible; any remaining unexpected fault is isolated
                # to this message so the durable worker stays available.
                logger.exception("Worker failed while handling run %s", run_id)
            finally:
                await self.queue.task_done()

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
            outcome_payload: dict[str, object] = {"error": f"{type(exc).__name__}: {exc}"}
            approval = None
        else:
            outcome_status = outcome.status
            outcome_payload = outcome.result
            approval = outcome.approval

        if self.store.is_cancel_requested(run_id) or outcome_status == RunStatus.CANCELLED:
            final = self.store.finish(
                run_id=run_id, status=RunStatus.CANCELLED, result=outcome_payload
            )
        elif outcome_status == RunStatus.APPROVAL_REQUIRED:
            if approval is None:
                final = self.store.finish(
                    run_id=run_id,
                    status=RunStatus.FAILED,
                    result={"error": "Executor returned approval_required without approval payload."},
                )
            else:
                final = self.store.require_approval(
                    run_id=run_id, approval=approval, result=outcome_payload
                )
        elif outcome_status == RunStatus.COMPLETED:
            final = self.store.finish(
                run_id=run_id, status=RunStatus.COMPLETED, result=outcome_payload
            )
        else:
            final = self.store.finish(
                run_id=run_id, status=RunStatus.FAILED, result=outcome_payload
            )

        self.artifact_store.write_json(
            run_id=run_id, name="result.json", payload=final.result or {}
        )
        self.artifact_store.write_json(
            run_id=run_id,
            name="events.json",
            payload=[event.model_dump(mode="json") for event in self.store.list_events(run_id)],
        )

    def _write_request_artifact(self, record: RunRecord) -> None:
        self.artifact_store.create_run(record.run_id)
        self.artifact_store.write_json(
            run_id=record.run_id, name="request.json", payload=record.request
        )

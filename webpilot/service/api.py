from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from webpilot.artifacts.store import ArtifactStore
from webpilot.runs.models import RunRequest, RunStatus
from webpilot.service.console_view import build_console_view
from webpilot.service.executor import RunExecutor, WebPilotRunExecutor
from webpilot.service.postgres_store import PostgreSQLRunStore
from webpilot.service.queue import build_run_queue_from_env
from webpilot.service.store import RunNotFoundError, SQLiteRunStore
from webpilot.service.worker import RunWorker


class RunStore(Protocol):
    def create_run(self, *, request: RunRequest, artifact_dir: str): ...
    def get_run(self, run_id: str): ...
    def list_events(self, run_id: str, *, after_sequence: int = 0): ...
    def request_cancel(self, run_id: str): ...
    def approve(self, run_id: str): ...


def build_run_store(*, project_root: Path) -> RunStore:
    """Use PostgreSQL only when explicitly configured; keep SQLite deterministic for tests."""
    database_url = os.environ.get("WEBPILOT_DATABASE_URL", "").strip()
    if database_url:
        return PostgreSQLRunStore(database_url)
    return SQLiteRunStore(project_root / "artifacts" / "service" / "runs.sqlite")


def create_app(
    *,
    store: RunStore | None = None,
    artifact_store: ArtifactStore | None = None,
    executor: RunExecutor | None = None,
    worker: RunWorker | None = None,
) -> FastAPI:
    """Build the API; run state is always persisted before a worker is notified."""

    project_root = Path(__file__).resolve().parents[2]
    artifact_store = artifact_store or ArtifactStore(project_root / "artifacts" / "runs")
    store = store or build_run_store(project_root=project_root)
    worker = worker or RunWorker(
        store=store,
        artifact_store=artifact_store,
        executor=executor or WebPilotRunExecutor(artifact_store=artifact_store),
        queue=build_run_queue_from_env(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await worker.start()
        try:
            yield
        finally:
            await worker.stop()

    app = FastAPI(title="WebPilot-QA", version="1.0.0", lifespan=lifespan)
    cors_origins = [
        item.strip()
        for item in os.environ.get(
            "WEBPILOT_CORS_ORIGINS",
            "http://127.0.0.1:3000,http://localhost:3000",
        ).split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.run_store = store
    app.state.artifact_store = artifact_store
    app.state.run_worker = worker

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "webpilot-qa"}

    @app.post("/runs", status_code=status.HTTP_202_ACCEPTED)
    async def create_run(request: RunRequest) -> dict[str, object]:
        record = store.create_run(request=request, artifact_dir=str(artifact_store.root))
        await worker.enqueue(record.run_id)
        return _run_payload(record)

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, object]:
        return _run_payload(_get_run_or_404(store, run_id))

    @app.get("/runs/{run_id}/events")
    async def get_events(run_id: str, after: int = Query(default=0, ge=0)) -> list[dict[str, object]]:
        try:
            events = store.list_events(run_id, after_sequence=after)
        except RunNotFoundError:
            raise _not_found(run_id) from None
        return [event.model_dump(mode="json") for event in events]

    @app.get("/runs/{run_id}/events/stream")
    async def stream_events(
        run_id: str, after: int = Query(default=0, ge=0), once: bool = False
    ) -> StreamingResponse:
        _get_run_or_404(store, run_id)

        async def event_stream() -> AsyncIterator[str]:
            next_sequence = after
            while True:
                events = store.list_events(run_id, after_sequence=next_sequence)
                for event in events:
                    next_sequence = event.sequence
                    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                    yield f"event: {event.kind}\\ndata: {payload}\\n\\n"
                record = store.get_run(run_id)
                if once or record.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                    return
                await asyncio.sleep(0.15)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict[str, object]:
        try:
            record = store.request_cancel(run_id)
        except RunNotFoundError:
            raise _not_found(run_id) from None
        return _run_payload(record)

    @app.post("/runs/{run_id}/approve")
    async def approve_run(run_id: str) -> dict[str, object]:
        try:
            record = store.approve(run_id)
        except RunNotFoundError:
            raise _not_found(run_id) from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await worker.enqueue(record.run_id)
        return _run_payload(record)

    @app.get("/runs/{run_id}/console")
    async def get_console_view(run_id: str) -> dict[str, object]:
        record = _get_run_or_404(store, run_id)
        return build_console_view(
            record=record,
            events=store.list_events(run_id),
            artifact_store=artifact_store,
        )

    @app.get("/runs/{run_id}/artifacts")
    async def list_artifacts(run_id: str) -> list[dict[str, str]]:
        _get_run_or_404(store, run_id)
        return [reference.__dict__ for reference in artifact_store.list_run(run_id)]

    @app.get("/runs/{run_id}/artifacts/{name}")
    async def get_artifact(run_id: str, name: str) -> FileResponse:
        _get_run_or_404(store, run_id)
        try:
            path = artifact_store.existing_path(run_id=run_id, name=name)
        except (FileNotFoundError, ValueError):
            raise HTTPException(status_code=404, detail=f"Unknown artifact: {name}") from None
        return FileResponse(path)

    return app


def _get_run_or_404(store: RunStore, run_id: str):
    try:
        return store.get_run(run_id)
    except RunNotFoundError:
        raise _not_found(run_id) from None


def _not_found(run_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Unknown run: {run_id}")


def _run_payload(record) -> dict[str, object]:
    return ArtifactStore.redact(record.model_dump(mode="json"))

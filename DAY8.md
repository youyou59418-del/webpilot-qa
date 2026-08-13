# Day 8 - Durable Run Service

## Delivered

- FastAPI endpoints for creating, reading, approving, cancelling, and observing browser runs.
- SQLite-backed durable run and event state, suitable for the current single-process / single-worker stage.
- A worker queue outside HTTP handlers, restart recovery for queued tasks, cancellation checks, and approval re-queueing.
- Per-run redacted request/result/safety/workflow artifacts under `artifacts/runs/<run_id>/`.
- Server-Sent Events for incremental run-state updates.

## Start and verify

```bash
./.venv/bin/python scripts/day8_service_demo.py
./.venv/bin/python -m uvicorn webpilot.service.api:create_app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

Create a run with `POST /runs`, poll `GET /runs/<run_id>`, consume `GET /runs/<run_id>/events/stream`, and use `POST /runs/<run_id>/approve` only after an `approval_required` state. `POST /runs/<run_id>/cancel` is valid before or during execution.

## Current operational boundary

This release intentionally uses one local worker and SQLite. Do not run multiple worker processes against this database. A production scale-out would replace the in-memory queue and SQLite lock with a shared queue and transactional database, keeping the API/state contracts unchanged.

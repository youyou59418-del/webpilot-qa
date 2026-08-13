from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from webpilot.runs.models import (
    RunEvent,
    RunRecord,
    RunRequest,
    RunStatus,
)
from webpilot.runs.state import ensure_transition
from webpilot.safety.models import ApprovalRequest


class RunNotFoundError(KeyError):
    pass


class SQLiteRunStore:
    """Small durable run/event store; SQLite is the Day 8 single-worker mode."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def create_run(
        self,
        *,
        request: RunRequest,
        artifact_dir: str,
    ) -> RunRecord:
        run_id = str(uuid4())
        now = self._now()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, request_json, status, created_at, updated_at,
                    artifact_dir, cancel_requested, approval_json,
                    approved_fingerprints_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, '[]', NULL)
                """,
                (
                    run_id,
                    self._dump(request),
                    RunStatus.QUEUED.value,
                    now,
                    now,
                    str(Path(artifact_dir) / run_id),
                ),
            )
            self._append_event(
                connection,
                run_id=run_id,
                kind="queued",
                status=RunStatus.QUEUED,
                payload={},
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return self._to_record(row)

    def list_events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[RunEvent]:
        self.get_run(run_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT sequence, kind, status, created_at, payload_json
                FROM run_events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (run_id, after_sequence),
            ).fetchall()
        return [
            RunEvent(
                sequence=row["sequence"],
                kind=row["kind"],
                status=RunStatus(row["status"]),
                created_at=self._parse_time(row["created_at"]),
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    def list_queued_run_ids(self) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id FROM runs WHERE status = ? ORDER BY created_at",
                (RunStatus.QUEUED.value,),
            ).fetchall()
        return [row["run_id"] for row in rows]

    def claim_run(self, run_id: str) -> RunRecord | None:
        with self._transaction() as connection:
            row = self._require_row(connection, run_id)
            current = RunStatus(row["status"])
            if current != RunStatus.QUEUED:
                return None
            if bool(row["cancel_requested"]):
                self._transition(
                    connection,
                    row=row,
                    target=RunStatus.CANCELLED,
                    kind="cancelled_before_start",
                    payload={},
                )
            else:
                self._transition(
                    connection,
                    row=row,
                    target=RunStatus.RUNNING,
                    kind="started",
                    payload={},
                )
        return self.get_run(run_id)

    def request_cancel(self, run_id: str) -> RunRecord:
        with self._transaction() as connection:
            row = self._require_row(connection, run_id)
            status = RunStatus(row["status"])
            if status in {RunStatus.QUEUED, RunStatus.APPROVAL_REQUIRED}:
                self._transition(
                    connection,
                    row=row,
                    target=RunStatus.CANCELLED,
                    kind="cancelled",
                    payload={},
                )
            elif status == RunStatus.RUNNING:
                now = self._now()
                connection.execute(
                    """
                    UPDATE runs
                    SET cancel_requested = 1, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (now, run_id),
                )
                self._append_event(
                    connection,
                    run_id=run_id,
                    kind="cancel_requested",
                    status=RunStatus.RUNNING,
                    payload={},
                )
        return self.get_run(run_id)

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._connection() as connection:
            row = self._require_row(connection, run_id)
        return bool(row["cancel_requested"])

    def require_approval(
        self,
        *,
        run_id: str,
        approval: ApprovalRequest,
        result: dict[str, object],
    ) -> RunRecord:
        with self._transaction() as connection:
            row = self._require_row(connection, run_id)
            self._transition(
                connection,
                row=row,
                target=RunStatus.APPROVAL_REQUIRED,
                kind="approval_required",
                payload={"approval": approval.model_dump(mode="json")},
                approval=approval,
                result=result,
            )
        return self.get_run(run_id)

    def approve(self, run_id: str) -> RunRecord:
        with self._transaction() as connection:
            row = self._require_row(connection, run_id)
            if RunStatus(row["status"]) != RunStatus.APPROVAL_REQUIRED:
                raise ValueError("Only an approval_required run can be approved.")
            approval_raw = row["approval_json"]
            if not approval_raw:
                raise ValueError("Run has no approval request.")
            approval = ApprovalRequest.model_validate_json(approval_raw)
            fingerprints = json.loads(row["approved_fingerprints_json"])
            if approval.fingerprint not in fingerprints:
                fingerprints.append(approval.fingerprint)
            self._transition(
                connection,
                row=row,
                target=RunStatus.QUEUED,
                kind="approved",
                payload={"request_id": approval.request_id},
                approval=None,
                approved_fingerprints=fingerprints,
            )
        return self.get_run(run_id)

    def finish(
        self,
        *,
        run_id: str,
        status: RunStatus,
        result: dict[str, object],
    ) -> RunRecord:
        if status not in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            raise ValueError("finish only accepts a terminal run status.")
        with self._transaction() as connection:
            row = self._require_row(connection, run_id)
            self._transition(
                connection,
                row=row,
                target=status,
                kind=status.value,
                payload={},
                result=result,
            )
        return self.get_run(run_id)

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    artifact_dir TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL,
                    approval_json TEXT,
                    approved_fingerprints_json TEXT NOT NULL,
                    result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                """
            )

    def _transition(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        target: RunStatus,
        kind: str,
        payload: dict[str, object],
        approval: ApprovalRequest | None | object = ...,
        approved_fingerprints: list[str] | None = None,
        result: dict[str, object] | None | object = ...,
    ) -> None:
        current = RunStatus(row["status"])
        ensure_transition(current=current, target=target)
        now = self._now()
        approval_json = (
            row["approval_json"]
            if approval is ...
            else self._dump(approval) if approval is not None else None
        )
        result_json = (
            row["result_json"]
            if result is ...
            else self._dump(result) if result is not None else None
        )
        fingerprints_json = self._dump(
            approved_fingerprints
            if approved_fingerprints is not None
            else json.loads(row["approved_fingerprints_json"])
        )
        connection.execute(
            """
            UPDATE runs
            SET status = ?, updated_at = ?, approval_json = ?,
                approved_fingerprints_json = ?, result_json = ?
            WHERE run_id = ?
            """,
            (
                target.value,
                now,
                approval_json,
                fingerprints_json,
                result_json,
                row["run_id"],
            ),
        )
        self._append_event(
            connection,
            run_id=row["run_id"],
            kind=kind,
            status=target,
            payload=payload,
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        kind: str,
        status: RunStatus,
        payload: dict[str, object],
    ) -> None:
        next_sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()["sequence"]
        connection.execute(
            """
            INSERT INTO run_events (
                run_id, sequence, kind, status, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                next_sequence,
                kind,
                status.value,
                self._now(),
                self._dump(payload),
            ),
        )

    def _require_row(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return row

    def _to_record(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            request=RunRequest.model_validate_json(row["request_json"]),
            status=RunStatus(row["status"]),
            created_at=self._parse_time(row["created_at"]),
            updated_at=self._parse_time(row["updated_at"]),
            artifact_dir=row["artifact_dir"],
            cancel_requested=bool(row["cancel_requested"]),
            approval=(
                ApprovalRequest.model_validate_json(row["approval_json"])
                if row["approval_json"]
                else None
            ),
            approved_fingerprints=json.loads(row["approved_fingerprints_json"]),
            result=(
                json.loads(row["result_json"])
                if row["result_json"]
                else None
            ),
        )

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _transaction(self):
        return _Transaction(self._lock, self._connection)

    @staticmethod
    def _dump(value: object) -> str:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value)


class _Transaction:
    def __init__(self, lock: threading.RLock, factory) -> None:
        self._lock = lock
        self._factory = factory
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._lock.acquire()
        self._connection = self._factory()
        self._connection.execute("BEGIN IMMEDIATE")
        return self._connection

    def __exit__(self, exc_type, exc, traceback) -> None:
        assert self._connection is not None
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._connection.close()
            self._lock.release()

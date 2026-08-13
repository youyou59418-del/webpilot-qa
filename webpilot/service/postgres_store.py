from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator
from uuid import uuid4

from webpilot.runs.models import RunEvent, RunRecord, RunRequest, RunStatus
from webpilot.runs.state import ensure_transition
from webpilot.safety.models import ApprovalRequest
from webpilot.service.store import RunNotFoundError


class PostgreSQLRunStore:
    """PostgreSQL authority for run state and ordered event history.

    Each state change and its matching event are committed in one transaction.
    `SELECT ... FOR UPDATE` makes claim/approval/cancellation safe when more
    than one API or worker process is present.
    """

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg  # noqa: F401
        except ImportError as exc:  # pragma: no cover - configuration error
            raise RuntimeError("PostgreSQL mode requires the 'psycopg' package.") from exc
        self.database_url = database_url
        self._initialize()

    def create_run(self, *, request: RunRequest, artifact_dir: str) -> RunRecord:
        run_id = str(uuid4())
        now = self._now()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, request_json, status, created_at, updated_at,
                    artifact_dir, cancel_requested, approval_json,
                    approved_fingerprints_json, result_json
                ) VALUES (%s, %s, %s, %s, %s, %s, FALSE, NULL, '[]', NULL)
                """,
                (
                    run_id,
                    self._dump(request),
                    RunStatus.QUEUED.value,
                    now,
                    now,
                    f"{artifact_dir.rstrip('/')}/{run_id}",
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
                "SELECT * FROM runs WHERE run_id = %s", (run_id,)
            ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return self._to_record(row)

    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[RunEvent]:
        self.get_run(run_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT sequence, kind, status, created_at, payload_json
                FROM run_events
                WHERE run_id = %s AND sequence > %s
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
                "SELECT run_id FROM runs WHERE status = %s ORDER BY created_at",
                (RunStatus.QUEUED.value,),
            ).fetchall()
        return [str(row["run_id"]) for row in rows]

    def claim_run(self, run_id: str) -> RunRecord | None:
        with self._transaction() as connection:
            row = self._require_row(connection, run_id, for_update=True)
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
            row = self._require_row(connection, run_id, for_update=True)
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
                connection.execute(
                    "UPDATE runs SET cancel_requested = TRUE, updated_at = %s WHERE run_id = %s",
                    (self._now(), run_id),
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
        self, *, run_id: str, approval: ApprovalRequest, result: dict[str, object]
    ) -> RunRecord:
        with self._transaction() as connection:
            row = self._require_row(connection, run_id, for_update=True)
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
            row = self._require_row(connection, run_id, for_update=True)
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
        self, *, run_id: str, status: RunStatus, result: dict[str, object]
    ) -> RunRecord:
        if status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ValueError("finish only accepts a terminal run status.")
        with self._transaction() as connection:
            row = self._require_row(connection, run_id, for_update=True)
            self._transition(
                connection,
                row=row,
                target=status,
                kind=status.value,
                payload={},
                result=result,
            )
        return self.get_run(run_id)

    def recover_interrupted_runs(self) -> list[str]:
        """Requeue runs left in `running` after an unclean worker restart."""
        recovered: list[str] = []
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM runs WHERE status = %s ORDER BY created_at FOR UPDATE",
                (RunStatus.RUNNING.value,),
            ).fetchall()
            for row in rows:
                run_id = str(row["run_id"])
                if bool(row["cancel_requested"]):
                    self._transition(
                        connection,
                        row=row,
                        target=RunStatus.CANCELLED,
                        kind="cancelled_after_restart",
                        payload={},
                    )
                    continue
                connection.execute(
                    "UPDATE runs SET status = %s, updated_at = %s WHERE run_id = %s",
                    (RunStatus.QUEUED.value, self._now(), run_id),
                )
                self._append_event(
                    connection,
                    run_id=run_id,
                    kind="requeued_after_restart",
                    status=RunStatus.QUEUED,
                    payload={},
                )
                recovered.append(run_id)
        return recovered

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    artifact_dir TEXT NOT NULL,
                    cancel_requested BOOLEAN NOT NULL,
                    approval_json TEXT,
                    approved_fingerprints_json TEXT NOT NULL,
                    result_json TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS runs_status_created_at_idx ON runs(status, created_at)"
            )

    def _transition(
        self,
        connection: Any,
        *,
        row: dict[str, Any],
        target: RunStatus,
        kind: str,
        payload: dict[str, object],
        approval: ApprovalRequest | None | object = ...,
        approved_fingerprints: list[str] | None = None,
        result: dict[str, object] | None | object = ...,
    ) -> None:
        current = RunStatus(row["status"])
        ensure_transition(current=current, target=target)
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
            SET status = %s, updated_at = %s, approval_json = %s,
                approved_fingerprints_json = %s, result_json = %s
            WHERE run_id = %s
            """,
            (target.value, self._now(), approval_json, fingerprints_json, result_json, row["run_id"]),
        )
        self._append_event(
            connection,
            run_id=str(row["run_id"]),
            kind=kind,
            status=target,
            payload=payload,
        )

    def _append_event(
        self, connection: Any, *, run_id: str, kind: str, status: RunStatus, payload: dict[str, object]
    ) -> None:
        next_sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = %s",
            (run_id,),
        ).fetchone()["sequence"]
        connection.execute(
            """
            INSERT INTO run_events (run_id, sequence, kind, status, created_at, payload_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (run_id, next_sequence, kind, status.value, self._now(), self._dump(payload)),
        )

    def _require_row(self, connection: Any, run_id: str, *, for_update: bool = False) -> dict[str, Any]:
        statement = "SELECT * FROM runs WHERE run_id = %s"
        if for_update:
            statement += " FOR UPDATE"
        row = connection.execute(statement, (run_id,)).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return row

    def _to_record(self, row: dict[str, Any]) -> RunRecord:
        return RunRecord(
            run_id=str(row["run_id"]),
            request=RunRequest.model_validate_json(row["request_json"]),
            status=RunStatus(row["status"]),
            created_at=self._parse_time(row["created_at"]),
            updated_at=self._parse_time(row["updated_at"]),
            artifact_dir=str(row["artifact_dir"]),
            cancel_requested=bool(row["cancel_requested"]),
            approval=(ApprovalRequest.model_validate_json(row["approval_json"]) if row["approval_json"] else None),
            approved_fingerprints=json.loads(row["approved_fingerprints_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
        )

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        with self._connection() as connection:
            with connection.transaction():
                yield connection

    @staticmethod
    def _dump(value: object) -> str:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _parse_time(value: datetime | str) -> datetime:
        return datetime.fromisoformat(value) if isinstance(value, str) else value

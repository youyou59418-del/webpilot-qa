from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from webpilot.safety.models import ApprovalRequest


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    target_url: str = Field(min_length=1)
    max_steps: int = Field(default=6, ge=1, le=50)
    max_retries: int = Field(default=2, ge=0, le=10)


class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    kind: str
    status: RunStatus
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    request: RunRequest
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    artifact_dir: str
    cancel_requested: bool = False
    approval: ApprovalRequest | None = None
    approved_fingerprints: list[str] = Field(default_factory=list)
    result: dict[str, Any] | None = None


class WorkerExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RunStatus
    result: dict[str, Any] = Field(default_factory=dict)
    approval: ApprovalRequest | None = None


TERMINAL_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }
)

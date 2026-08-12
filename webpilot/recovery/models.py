from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FailureType(str, Enum):
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    ELEMENT_NOT_VISIBLE = "ELEMENT_NOT_VISIBLE"
    TIMEOUT = "TIMEOUT"
    PAGE_CHANGED = "PAGE_CHANGED"
    WRONG_PAGE = "WRONG_PAGE"
    ASSERTION_FAILED = "ASSERTION_FAILED"
    ACTION_FORBIDDEN = "ACTION_FORBIDDEN"
    UNKNOWN = "UNKNOWN"


class RecoveryAction(str, Enum):
    RE_OBSERVE = "RE_OBSERVE"
    SHORT_WAIT = "SHORT_WAIT"
    RETRY_ONCE = "RETRY_ONCE"
    REPLAN = "REPLAN"
    STOP = "STOP"


class FailureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_type: FailureType
    step_id: str
    message: str

    tool_name: str | None = None
    element_ref: str | None = None

    retry_count: int = Field(ge=0)

    current_url: str | None = None


class RecoveryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: RecoveryAction
    reason: str
    consume_retry: bool = True


class RetryBudget(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    max_retries: int = Field(
        default=2,
        ge=0,
    )

    retry_count: int = Field(
        default=0,
        ge=0,
    )

    @property
    def remaining(self) -> int:
        return max(
            self.max_retries - self.retry_count,
            0,
        )

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def consume(self) -> None:
        if not self.can_retry():
            raise RuntimeError(
                "Retry budget exhausted"
            )

        self.retry_count += 1

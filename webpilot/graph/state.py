from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from webpilot.agents.planner import (
    TestPlan,
)
from webpilot.recovery.models import (
    FailureEvent,
    RecoveryDecision,
)
from webpilot.safety.models import ApprovalRequest
from webpilot.verifier.rules import (
    VerificationResult,
)


RunStatus = Literal[
    "queued",
    "planned",
    "running",
    "approval_required",
    "completed",
    "failed",
    "cancelled",
]


class ObservationSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    url: str
    title: str
    visible_text_excerpt: str
    element_count: int


class ActionRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    plan_step_id: str
    action_index: int
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    plan_attempt: int = Field(
        default=1,
        ge=1,
    )


class StepVerification(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    plan_step_id: str
    result: VerificationResult
    plan_attempt: int = Field(
        default=1,
        ge=1,
    )


class PlanAttempt(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    attempt: int = Field(
        ge=1,
    )
    trigger: Literal["initial", "replan"]
    plan: TestPlan
    failure: FailureEvent | None = None


class RecoveryRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    plan_attempt: int = Field(
        ge=1,
    )
    plan_step_id: str
    failure: FailureEvent
    decision: RecoveryDecision
    retry_count_after: int = Field(
        ge=0,
    )
    outcome: str


class Day4RunState(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    task: str
    target_url: str
    plan: TestPlan

    plan_attempt: int = Field(
        default=1,
        ge=1,
    )

    plan_history: list[PlanAttempt] = Field(
        default_factory=list,
    )

    current_step_index: int = Field(
        default=0,
        ge=0,
    )

    observation: (
        ObservationSummary
        | None
    ) = None

    history: list[ActionRecord] = Field(
        default_factory=list
    )

    verification: (
        VerificationResult
        | None
    ) = None

    step_verifications: list[StepVerification] = Field(
        default_factory=list,
    )

    recovery_history: list[RecoveryRecord] = Field(
        default_factory=list,
    )

    approval: ApprovalRequest | None = None

    status: RunStatus = "planned"

    @model_validator(mode="after")
    def validate_progress(self) -> "Day4RunState":
        if self.current_step_index > len(self.plan.steps):
            raise ValueError(
                "current_step_index cannot exceed the number of plan steps"
            )
        return self


def summarize_observation(
    observation: Any,
    *,
    max_chars: int = 1000,
) -> ObservationSummary:
    visible_text = (
        observation.visible_text
        or ""
    )

    return ObservationSummary(
        url=observation.url,
        title=observation.title,
        visible_text_excerpt=(
            visible_text[:max_chars]
        ),
        element_count=len(
            observation.elements
        ),
    )

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


OutcomeStatus = Literal["passed", "failed", "blocked_by_safety", "skipped"]


class EvaluationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    difficulty: Literal["easy", "medium", "hard"]
    status: OutcomeStatus
    duration_ms: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    retries: int = Field(ge=0)
    run_id: str | None = None
    failure_category: str | None = None
    note: str | None = None


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benchmark: str = "shopbench-v1"
    variant: str
    model_name: str
    execution_mode: Literal["live_model", "dry_run"]
    started_at: datetime
    completed_at: datetime
    outcomes: list[EvaluationOutcome]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def passed_count(self) -> int:
        return sum(item.status == "passed" for item in self.outcomes)

    @property
    def attempted_count(self) -> int:
        return sum(item.status != "skipped" for item in self.outcomes)

    @property
    def success_rate(self) -> float | None:
        if not self.attempted_count:
            return None
        return self.passed_count / self.attempted_count

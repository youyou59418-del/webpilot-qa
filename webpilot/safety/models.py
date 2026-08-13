from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class SafetyDisposition(str, Enum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"


class SafetyTarget(BaseModel):
    """Semantic target information safe to retain in a run artifact."""

    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    name: str | None = None
    url: str | None = None


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    fingerprint: str
    risk_level: RiskLevel
    tool_name: str
    target: SafetyTarget
    reason: str


class SafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: SafetyDisposition
    risk_level: RiskLevel
    tool_name: str
    target: SafetyTarget
    reason: str
    approval: ApprovalRequest | None = None


class SafetyAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    decision: SafetyDecision

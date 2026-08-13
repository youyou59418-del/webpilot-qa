from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol
from uuid import uuid4

from webpilot.safety.models import (
    ApprovalRequest,
    RiskLevel,
    SafetyAuditRecord,
    SafetyDecision,
    SafetyDisposition,
    SafetyTarget,
)
from webpilot.safety.policy import RiskPolicy


class ElementLookup(Protocol):
    def element_for(self, ref: str) -> Any:
        ...


class ApprovalRequiredError(PermissionError):
    """Raised before a high-risk browser action reaches Playwright."""

    prefix = "APPROVAL_REQUIRED:"

    def __init__(self, approval: ApprovalRequest) -> None:
        self.approval = approval
        super().__init__(
            self.prefix + approval.model_dump_json()
        )


class SafetyGate:
    """Default-deny gate for side-effecting browser operations.

    Approval is tied to a stable semantic fingerprint, not the temporary eN
    reference. Re-observation therefore cannot accidentally invalidate a
    user-approved action, while a different page target still needs approval.
    """

    def __init__(
        self,
        *,
        approved_fingerprints: set[str] | None = None,
        policy: RiskPolicy | None = None,
    ) -> None:
        self.approved_fingerprints = set(approved_fingerprints or set())
        self.policy = policy or RiskPolicy()
        self.audit_records: list[SafetyAuditRecord] = []

    def authorize(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        observation_engine: ElementLookup,
    ) -> None:
        target = self._target_for(
            tool_name=tool_name,
            arguments=arguments,
            observation_engine=observation_engine,
        )
        risk_level, reason = self.policy.classify(
            tool_name=tool_name,
            arguments=arguments,
            target=target,
        )
        fingerprint = self._fingerprint(
            tool_name=tool_name,
            target=target,
        )

        if risk_level in {RiskLevel.L0, RiskLevel.L1} or (
            fingerprint in self.approved_fingerprints
        ):
            self._record(
                SafetyDecision(
                    disposition=SafetyDisposition.ALLOW,
                    risk_level=risk_level,
                    tool_name=tool_name,
                    target=target,
                    reason=(
                        "Previously approved semantic action."
                        if fingerprint in self.approved_fingerprints
                        and risk_level in {RiskLevel.L2, RiskLevel.L3}
                        else reason
                    ),
                )
            )
            return

        approval = ApprovalRequest(
            request_id=str(uuid4()),
            fingerprint=fingerprint,
            risk_level=risk_level,
            tool_name=tool_name,
            target=target,
            reason=reason,
        )
        decision = SafetyDecision(
            disposition=SafetyDisposition.APPROVAL_REQUIRED,
            risk_level=risk_level,
            tool_name=tool_name,
            target=target,
            reason=reason,
            approval=approval,
        )
        self._record(decision)
        raise ApprovalRequiredError(approval)

    def _target_for(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        observation_engine: ElementLookup,
    ) -> SafetyTarget:
        if tool_name == "open_url":
            url = arguments.get("url")
            return SafetyTarget(url=url if isinstance(url, str) else None)
        ref = arguments.get("ref")
        if not isinstance(ref, str):
            return SafetyTarget()
        element = observation_engine.element_for(ref)
        return SafetyTarget(
            role=getattr(element, "role", None),
            name=getattr(element, "name", None)
            or getattr(element, "text", None)
            or getattr(element, "placeholder", None),
        )

    @staticmethod
    def _fingerprint(*, tool_name: str, target: SafetyTarget) -> str:
        material = json.dumps(
            {
                "tool_name": tool_name,
                "target": target.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _record(self, decision: SafetyDecision) -> None:
        self.audit_records.append(
            SafetyAuditRecord(
                sequence=len(self.audit_records) + 1,
                decision=decision,
            )
        )

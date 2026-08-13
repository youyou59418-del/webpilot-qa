from __future__ import annotations

from typing import Any

from webpilot.safety.models import RiskLevel, SafetyTarget


_HIGH_RISK_TERMS = {
    "delete",
    "remove",
    "destroy",
    "pay",
    "purchase",
    "buy",
    "order",
    "book",
    "send",
    "submit",
    "confirm",
    "subscribe",
    "unsubscribe",
    "transfer",
    "publish",
}

_SENSITIVE_FIELD_TERMS = {
    "password",
    "passcode",
    "otp",
    "one-time",
    "verification code",
    "cvv",
    "cvc",
    "card number",
    "credit card",
    "bank account",
    "ssn",
    "passport",
}


class RiskPolicy:
    """Classify browser actions from structured, semantic information only."""

    def classify(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        target: SafetyTarget,
    ) -> tuple[RiskLevel, str]:
        if tool_name in {"get_page_state", "open_url"}:
            return RiskLevel.L0, "Read-only page inspection or navigation."

        target_text = " ".join(
            part
            for part in (target.name, target.role)
            if part
        ).lower()

        if tool_name == "fill":
            if any(term in target_text for term in _SENSITIVE_FIELD_TERMS):
                return (
                    RiskLevel.L3,
                    "The target appears to collect sensitive credentials or identity data.",
                )
            return RiskLevel.L1, "Ordinary form entry."

        if tool_name == "click":
            if any(term in target_text for term in _HIGH_RISK_TERMS):
                return (
                    RiskLevel.L3,
                    "The target name indicates an external or destructive side effect.",
                )
            return RiskLevel.L1, "Ordinary semantic click."

        return RiskLevel.L3, "Unknown browser action requires explicit approval."

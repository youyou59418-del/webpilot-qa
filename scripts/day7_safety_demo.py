"""Day 7 approval-gate demonstration without opening a real browser."""

from __future__ import annotations

import json

from webpilot.browser.observation import InteractiveElement
from webpilot.safety.gate import ApprovalRequiredError, SafetyGate


class StaticElements:
    def element_for(self, ref: str) -> InteractiveElement:
        assert ref == "e1"
        return InteractiveElement(ref="e1", tag="button", role="button", name="Delete account")


def main() -> None:
    gate = SafetyGate()
    try:
        gate.authorize(
            tool_name="click",
            arguments={"ref": "e1"},
            observation_engine=StaticElements(),
        )
    except ApprovalRequiredError as exc:
        print("approval_required")
        print(json.dumps(exc.approval.model_dump(mode="json"), ensure_ascii=False, indent=2))
        gate.approved_fingerprints.add(exc.approval.fingerprint)

    gate.authorize(
        tool_name="click",
        arguments={"ref": "e1"},
        observation_engine=StaticElements(),
    )
    print("approved_action_allowed")
    print(json.dumps([item.model_dump(mode="json") for item in gate.audit_records], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

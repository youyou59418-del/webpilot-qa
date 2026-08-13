import pytest

from webpilot.browser.observation import InteractiveElement
from webpilot.safety.gate import ApprovalRequiredError, SafetyGate
from webpilot.safety.models import RiskLevel


class StaticElements:
    def __init__(self, element: InteractiveElement) -> None:
        self.element = element

    def element_for(self, ref: str) -> InteractiveElement:
        assert ref == self.element.ref
        return self.element


def test_ordinary_click_is_allowed_and_audited() -> None:
    gate = SafetyGate()
    elements = StaticElements(
        InteractiveElement(ref="e1", tag="button", role="button", name="Search")
    )

    gate.authorize(tool_name="click", arguments={"ref": "e1"}, observation_engine=elements)

    record = gate.audit_records[-1].decision
    assert record.risk_level == RiskLevel.L1
    assert record.disposition == "allow"


def test_destructive_click_requires_exact_approval() -> None:
    gate = SafetyGate()
    elements = StaticElements(
        InteractiveElement(ref="e9", tag="button", role="button", name="Delete account")
    )

    with pytest.raises(ApprovalRequiredError) as captured:
        gate.authorize(tool_name="click", arguments={"ref": "e9"}, observation_engine=elements)

    approval = captured.value.approval
    assert approval.risk_level == RiskLevel.L3
    gate.approved_fingerprints.add(approval.fingerprint)
    gate.authorize(tool_name="click", arguments={"ref": "e9"}, observation_engine=elements)
    assert gate.audit_records[-1].decision.disposition == "allow"


def test_sensitive_field_requires_approval() -> None:
    gate = SafetyGate()
    elements = StaticElements(
        InteractiveElement(ref="e3", tag="input", role="textbox", name="Password")
    )

    with pytest.raises(ApprovalRequiredError) as captured:
        gate.authorize(
            tool_name="fill",
            arguments={"ref": "e3", "value": "not-retained"},
            observation_engine=elements,
        )

    assert captured.value.approval.risk_level == RiskLevel.L3

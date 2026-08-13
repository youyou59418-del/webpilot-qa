from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
)

from webpilot.agents.planner import (
    SuccessCriterion,
)


VerificationStatus = Literal[
    "PASS",
    "FAIL",
]


class VerificationEvidence(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    rule: str
    expected: str
    actual: str
    passed: bool
    details: str = ""


class VerificationResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: VerificationStatus

    evidence: list[
        VerificationEvidence
    ]

    failure_reason: str | None = None


class RuleVerifier:
    def verify(
        self,
        *,
        observation: Any,
        criteria: list[
            SuccessCriterion
        ],
    ) -> VerificationResult:
        evidence: list[
            VerificationEvidence
        ] = []

        if not criteria:
            return VerificationResult(
                status="FAIL",
                evidence=[],
                failure_reason="No success criteria were provided.",
            )

        for criterion in criteria:
            if criterion.rule == "url_contains":
                item = self._verify_url_contains(
                    observation=observation,
                    criterion=criterion,
                )

            elif (
                criterion.rule
                == "visible_text_contains"
            ):
                item = (
                    self._verify_visible_text_contains(
                        observation=observation,
                        criterion=criterion,
                    )
                )

            elif (
                criterion.rule
                == "element_text_equals"
            ):
                item = (
                    self._verify_element_text_equals(
                        observation=observation,
                        criterion=criterion,
                    )
                )

            elif criterion.rule == "element_value_equals":
                item = self._verify_element_value_equals(
                    observation=observation,
                    criterion=criterion,
                )

            elif criterion.rule == "element_checked_equals":
                item = self._verify_element_checked_equals(
                    observation=observation,
                    criterion=criterion,
                )

            else:
                raise RuntimeError(
                    "Unsupported verification rule: "
                    f"{criterion.rule}"
                )

            evidence.append(
                item
            )

        passed = all(
            item.passed
            for item in evidence
        )

        if passed:
            return VerificationResult(
                status="PASS",
                evidence=evidence,
                failure_reason=None,
            )

        failed_rules = [
            f"{item.rule}({item.expected!r})"
            for item in evidence
            if not item.passed
        ]

        return VerificationResult(
            status="FAIL",
            evidence=evidence,
            failure_reason=(
                "Failed verification rule(s): "
                + ", ".join(failed_rules)
            ),
        )

    @staticmethod
    def _verify_url_contains(
        *,
        observation: Any,
        criterion: SuccessCriterion,
    ) -> VerificationEvidence:
        actual = observation.url or ""

        passed = (
            criterion.expected
            in actual
        )

        return VerificationEvidence(
            rule=criterion.rule,
            expected=criterion.expected,
            actual=actual,
            passed=passed,
            details=(
                "Checked BrowserObservation.url"
            ),
        )

    @staticmethod
    def _verify_visible_text_contains(
        *,
        observation: Any,
        criterion: SuccessCriterion,
    ) -> VerificationEvidence:
        actual = (
            observation.visible_text
            or ""
        )

        passed = (
            criterion.expected
            in actual
        )

        return VerificationEvidence(
            rule=criterion.rule,
            expected=criterion.expected,
            actual=actual,
            passed=passed,
            details=(
                "Checked visible page text"
            ),
        )

    @staticmethod
    def _verify_element_text_equals(
        *,
        observation: Any,
        criterion: SuccessCriterion,
    ) -> VerificationEvidence:
        candidates = []

        for element in observation.elements:
            if (
                criterion.element_role
                and element.role
                != criterion.element_role
            ):
                continue

            if (
                criterion.element_name
                and element.name
                != criterion.element_name
            ):
                continue

            candidates.append(
                element
            )

        target = (
            f"role={criterion.element_role!r}, "
            f"name={criterion.element_name!r}"
        )

        if not candidates:
            return VerificationEvidence(
                rule=criterion.rule,
                expected=criterion.expected,
                actual="<element-not-found>",
                passed=False,
                details=(
                    "No current observation element "
                    f"matched the semantic target ({target})"
                ),
            )

        actual_texts = [
            (
                element.text
                or ""
            ).strip()
            for element in candidates
        ]

        passed = any(
            text == criterion.expected
            for text in actual_texts
        )

        return VerificationEvidence(
            rule=criterion.rule,
            expected=criterion.expected,
            actual=repr(actual_texts),
            passed=passed,
            details=(
                "Matched element using exact semantic target "
                f"({target})"
            ),
        )

    @staticmethod
    def _matching_elements(
        *,
        observation: Any,
        criterion: SuccessCriterion,
    ) -> list[Any]:
        return [
            element
            for element in observation.elements
            if (
                (not criterion.element_role or element.role == criterion.element_role)
                and (not criterion.element_name or element.name == criterion.element_name)
            )
        ]

    def _verify_element_value_equals(
        self,
        *,
        observation: Any,
        criterion: SuccessCriterion,
    ) -> VerificationEvidence:
        candidates = self._matching_elements(
            observation=observation,
            criterion=criterion,
        )
        actual_values = [element.value or "" for element in candidates]
        return VerificationEvidence(
            rule=criterion.rule,
            expected=criterion.expected,
            actual=repr(actual_values) if candidates else "<element-not-found>",
            passed=criterion.expected in actual_values,
            details="Matched the current control value using its semantic target.",
        )

    def _verify_element_checked_equals(
        self,
        *,
        observation: Any,
        criterion: SuccessCriterion,
    ) -> VerificationEvidence:
        candidates = self._matching_elements(
            observation=observation,
            criterion=criterion,
        )
        expected = criterion.expected == "true"
        actual_values = [element.checked for element in candidates]
        return VerificationEvidence(
            rule=criterion.rule,
            expected=criterion.expected,
            actual=repr(actual_values) if candidates else "<element-not-found>",
            passed=expected in actual_values,
            details="Matched the current checked state using its semantic target.",
        )

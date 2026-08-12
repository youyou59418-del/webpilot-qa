from types import SimpleNamespace

from webpilot.recovery.classifier import FailureClassifier
from webpilot.recovery.models import FailureType


def test_element_not_found() -> None:
    event = FailureClassifier().from_exception(
        exc=RuntimeError(
            "Unknown element ref: e999"
        ),
        step_id="step_1",
        retry_count=0,
        tool_name="click",
        element_ref="e999",
    )

    assert (
        event.failure_type
        == FailureType.ELEMENT_NOT_FOUND
    )


def test_element_not_visible() -> None:
    event = FailureClassifier().from_exception(
        exc=RuntimeError(
            "Element is not visible"
        ),
        step_id="step_1",
        retry_count=0,
    )

    assert (
        event.failure_type
        == FailureType.ELEMENT_NOT_VISIBLE
    )


def test_timeout() -> None:
    event = FailureClassifier().from_exception(
        exc=RuntimeError(
            "Operation timed out"
        ),
        step_id="step_1",
        retry_count=0,
    )

    assert (
        event.failure_type
        == FailureType.TIMEOUT
    )


def test_page_changed() -> None:
    event = FailureClassifier().from_exception(
        exc=RuntimeError(
            "Execution context was destroyed because of navigation"
        ),
        step_id="step_1",
        retry_count=0,
    )

    assert (
        event.failure_type
        == FailureType.PAGE_CHANGED
    )


def test_action_forbidden() -> None:
    event = FailureClassifier().from_exception(
        exc=RuntimeError(
            "Browser tool is not allowed"
        ),
        step_id="step_1",
        retry_count=0,
    )

    assert (
        event.failure_type
        == FailureType.ACTION_FORBIDDEN
    )


def test_verification_failure() -> None:
    verification = SimpleNamespace(
        failure_reason=(
            "Expected text was not found"
        )
    )

    event = FailureClassifier().from_verification(
        verification=verification,
        step_id="step_1",
        retry_count=0,
    )

    assert (
        event.failure_type
        == FailureType.ASSERTION_FAILED
    )


def test_wrong_page() -> None:
    event = FailureClassifier().wrong_page(
        step_id="step_1",
        retry_count=0,
        expected_url="products",
        current_url="login",
    )

    assert (
        event.failure_type
        == FailureType.WRONG_PAGE
    )


def test_url_verification_failure_is_classified_as_wrong_page() -> None:
    verification = SimpleNamespace(
        failure_reason="Expected URL fragment was not found",
        evidence=[
            SimpleNamespace(
                rule="url_contains",
                passed=False,
            )
        ],
    )

    event = FailureClassifier().from_verification(
        verification=verification,
        step_id="step_1",
        retry_count=0,
        current_url="https://example.test/login",
    )

    assert event.failure_type == FailureType.WRONG_PAGE

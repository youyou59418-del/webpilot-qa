import pytest

from webpilot.recovery.models import (
    FailureEvent,
    FailureType,
    RecoveryAction,
    RetryBudget,
)
from webpilot.recovery.policy import RecoveryPolicy


@pytest.mark.parametrize(
    ("failure_type", "expected_action"),
    [
        (
            FailureType.ELEMENT_NOT_FOUND,
            RecoveryAction.RE_OBSERVE,
        ),
        (
            FailureType.ELEMENT_NOT_VISIBLE,
            RecoveryAction.SHORT_WAIT,
        ),
        (
            FailureType.TIMEOUT,
            RecoveryAction.RETRY_ONCE,
        ),
        (
            FailureType.PAGE_CHANGED,
            RecoveryAction.RE_OBSERVE,
        ),
        (
            FailureType.WRONG_PAGE,
            RecoveryAction.REPLAN,
        ),
        (
            FailureType.ASSERTION_FAILED,
            RecoveryAction.REPLAN,
        ),
        (
            FailureType.ACTION_FORBIDDEN,
            RecoveryAction.STOP,
        ),
        (
            FailureType.UNKNOWN,
            RecoveryAction.STOP,
        ),
    ],
)
def test_recovery_mapping(
    failure_type,
    expected_action,
) -> None:
    policy = RecoveryPolicy()

    budget = RetryBudget(
        max_retries=2
    )

    failure = FailureEvent(
        failure_type=failure_type,
        step_id="step_1",
        message="test",
        retry_count=0,
    )

    decision = policy.decide(
        failure=failure,
        budget=budget,
    )

    assert (
        decision.action
        == expected_action
    )


def test_budget_exhaustion_forces_stop() -> None:
    policy = RecoveryPolicy()

    budget = RetryBudget(
        max_retries=1,
        retry_count=1,
    )

    failure = FailureEvent(
        failure_type=FailureType.TIMEOUT,
        step_id="step_1",
        message="timeout",
        retry_count=1,
    )

    decision = policy.decide(
        failure=failure,
        budget=budget,
    )

    assert (
        decision.action
        == RecoveryAction.STOP
    )

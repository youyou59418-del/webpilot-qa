from __future__ import annotations

from webpilot.recovery.models import (
    FailureEvent,
    FailureType,
    RecoveryAction,
    RecoveryDecision,
    RetryBudget,
)


class RecoveryPolicy:
    def decide(
        self,
        *,
        failure: FailureEvent,
        budget: RetryBudget,
    ) -> RecoveryDecision:

        if failure.failure_type == FailureType.ACTION_FORBIDDEN:
            return RecoveryDecision(
                action=RecoveryAction.STOP,
                reason=(
                    "Forbidden action must stop immediately."
                ),
                consume_retry=False,
            )

        if failure.failure_type == FailureType.UNKNOWN:
            return RecoveryDecision(
                action=RecoveryAction.STOP,
                reason=(
                    "Unknown failure will not be blindly retried."
                ),
                consume_retry=False,
            )

        if not budget.can_retry():
            return RecoveryDecision(
                action=RecoveryAction.STOP,
                reason=(
                    "Recovery retry budget exhausted."
                ),
                consume_retry=False,
            )

        if failure.failure_type == FailureType.ELEMENT_NOT_FOUND:
            return RecoveryDecision(
                action=RecoveryAction.RE_OBSERVE,
                reason=(
                    "Element ref is stale or missing. "
                    "Re-observe and use the new observation."
                ),
            )

        if failure.failure_type == FailureType.ELEMENT_NOT_VISIBLE:
            return RecoveryDecision(
                action=RecoveryAction.SHORT_WAIT,
                reason=(
                    "Element may become visible after "
                    "a short bounded wait."
                ),
            )

        if failure.failure_type == FailureType.TIMEOUT:
            return RecoveryDecision(
                action=RecoveryAction.RETRY_ONCE,
                reason=(
                    "Timeout receives a bounded retry."
                ),
            )

        if failure.failure_type == FailureType.PAGE_CHANGED:
            return RecoveryDecision(
                action=RecoveryAction.RE_OBSERVE,
                reason=(
                    "Page changed and current observation "
                    "may be stale."
                ),
            )

        if failure.failure_type == FailureType.WRONG_PAGE:
            return RecoveryDecision(
                action=RecoveryAction.REPLAN,
                reason=(
                    "Current page no longer matches plan."
                ),
            )

        if failure.failure_type == FailureType.ASSERTION_FAILED:
            return RecoveryDecision(
                action=RecoveryAction.REPLAN,
                reason=(
                    "Verifier evidence indicates that "
                    "the plan did not reach the expected state."
                ),
            )

        return RecoveryDecision(
            action=RecoveryAction.STOP,
            reason="No recovery policy matched.",
            consume_retry=False,
        )

import pytest

from webpilot.recovery.models import RetryBudget


def test_retry_budget_tracks_remaining() -> None:
    budget = RetryBudget(max_retries=2)

    assert budget.retry_count == 0
    assert budget.remaining == 2
    assert budget.can_retry() is True

    budget.consume()

    assert budget.retry_count == 1
    assert budget.remaining == 1

    budget.consume()

    assert budget.retry_count == 2
    assert budget.remaining == 0
    assert budget.can_retry() is False


def test_retry_budget_rejects_extra_retry() -> None:
    budget = RetryBudget(max_retries=1)

    budget.consume()

    with pytest.raises(
        RuntimeError,
        match="exhausted",
    ):
        budget.consume()

from __future__ import annotations

from webpilot.runs.models import RunStatus


_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.APPROVAL_REQUIRED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.APPROVAL_REQUIRED: frozenset(
        {RunStatus.QUEUED, RunStatus.CANCELLED}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


def ensure_transition(*, current: RunStatus, target: RunStatus) -> None:
    if target not in _TRANSITIONS[current]:
        raise ValueError(
            f"Invalid run state transition: {current.value} -> {target.value}"
        )


def can_transition(*, current: RunStatus, target: RunStatus) -> bool:
    return target in _TRANSITIONS[current]

"""
Lazy package exports.

This file intentionally avoids eager cross-module imports
to prevent circular imports between agents, graph and verifier.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {'ActionRecord': ('webpilot.graph.state', 'ActionRecord'),
 'Day4RunState': ('webpilot.graph.state', 'Day4RunState'),
 'ObservationSummary': ('webpilot.graph.state', 'ObservationSummary'),
 'PlanAttempt': ('webpilot.graph.state', 'PlanAttempt'),
 'RecoveryRecord': ('webpilot.graph.state', 'RecoveryRecord'),
 'StepVerification': ('webpilot.graph.state', 'StepVerification'),
 'summarize_observation': ('webpilot.graph.state', 'summarize_observation')}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    target = _EXPORTS.get(name)

    if target is None:
        raise AttributeError(
            f"module {__name__!r} "
            f"has no attribute {name!r}"
        )

    module_name, attribute_name = target

    module = import_module(
        module_name
    )

    value = getattr(
        module,
        attribute_name,
    )

    globals()[name] = value

    return value


def __dir__():
    return sorted(
        set(globals())
        | set(__all__)
    )

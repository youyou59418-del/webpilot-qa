"""
Lazy package exports.

This file intentionally avoids eager cross-module imports
to prevent circular imports between agents, graph and verifier.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {'RuleVerifier': ('webpilot.verifier.rules', 'RuleVerifier'),
 'VerificationEvidence': ('webpilot.verifier.rules', 'VerificationEvidence'),
 'VerificationResult': ('webpilot.verifier.rules', 'VerificationResult')}

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

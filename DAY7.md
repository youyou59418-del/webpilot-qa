# Day 7 - Risk Gate and Human Approval

## Delivered

- A semantic risk policy at the browser-tool boundary.
- L0/L1 actions run automatically; L3 side-effecting clicks and sensitive field entry stop before Playwright executes them.
- Approval is bound to a stable semantic fingerprint (tool plus target), rather than an unstable page element reference.
- Every decision is captured in a redacted safety artifact.
- The Day 5 formal workflow now returns `approval_required` or `cancelled` instead of treating these as generic failures.

## Acceptance checks

```bash
./.venv/bin/python scripts/day7_safety_demo.py
./.venv/bin/python -m pytest -q tests/test_day7_safety.py tests/test_day7_browser_gate.py
```

The demo must first print `approval_required`, then `approved_action_allowed`. The browser test verifies that a destructive click changes no page state until its matching fingerprint is approved.

## Operating rule

Approval is only for the exact semantic action displayed by the API. If the page target, action type, or policy changes, its fingerprint changes and a new approval is required. Never bypass the gate by adding arbitrary tool names or selector/JavaScript execution.

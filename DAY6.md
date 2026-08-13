# WebPilot-QA Day 6

## Goal

Add a rule-based Self-Healing Locator for recovering
interactive browser targets after DOM drift.

## Core Rule

Element refs such as e1/e2/e3 remain observation-local.

Day 6 does NOT make refs persistent.

Instead:

old semantic signature
-> fresh BrowserObservation
-> candidate ranking
-> healed current ref
-> browser action
-> fresh observation
-> Verifier

## Element Signature

The Self-Healing Locator records:

- tag
- role
- accessible name
- label
- placeholder
- visible text
- data-testid
- structural context

The original element ref is retained only for audit/debugging.

## Candidate Scoring

Priority:

1. role
2. accessible name / label
3. placeholder / visible text
4. data-testid
5. structural context

Day 6 uses deterministic rules and string similarity.

No embedding model is used.

## Controlled DOM Drift

The Day 6 fixture tests:

- Login -> Sign in
- element id rebuild
- container nesting changes
- element order changes
- data-testid removal
- ambiguous duplicate candidates

## Safety

A candidate must pass both:

- minimum score threshold
- minimum margin over second candidate

Ambiguous candidates are rejected instead of being clicked.

## Success Definition

Finding a similar-looking element is NOT considered recovery.

A Locator Recovery is successful only when:

1. a new candidate is selected
2. the browser action is executed
3. a fresh BrowserObservation is created
4. Verifier confirms the expected browser state

## Demo

```bash
python scripts/day6_self_healing_demo.py
```

Expected final output:

```text
Day 6 Self-Healing Demo PASSED
```

## Benchmark

```bash
python scripts/run_day6_self_healing_benchmark.py
```

Metrics:

- Locator Recovery Rate
- Task Success Rate after healing
- False Match Rate
- Safe Rejection Count

## Tests

```bash
pytest -q \
tests/test_self_healing_locator.py \
tests/test_day6_self_healing_integration.py
```

## Full Regression

```bash
pytest -q
```

## Day 6 Boundary

Not implemented:

- embedding-based locator matching
- vision fallback
- Risk-Aware Action Gate
- Human Approval
- FastAPI
- Worker
- Web Console
- vLLM

These capabilities belong to later development stages.

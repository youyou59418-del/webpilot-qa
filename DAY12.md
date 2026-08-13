# Day 12 - Regression Script Generator

Only a `workflow.json` whose status is `passed` can be converted to a regression test. The generator rejects failed actions, missing semantic targets, password/card-like fields and redacted values. It creates a fresh isolated BrowserContext and semantic Playwright locators, never transient `e1` references or CSS selectors.

```bash
./.venv/bin/python scripts/generate_regression_test.py artifacts/runs/<run_id>/workflow.json   --out artifacts/regression/test_generated.py --test-name shopbench_regression
for repeat in 1 2 3; do
  ./.venv/bin/python -m pytest -q artifacts/regression/test_generated.py
done
```

Verified live example:

- Source trajectory: `artifacts/runs/0fb88fd9-8cdc-4fa1-8dc6-3654c270dbdd/workflow.json` (E05, non-sensitive, passed).
- Generated test: `artifacts/regression/day12_e05/test_e05_open_help.py`.
- Acceptance: three fresh-context passes recorded in `run_1.log`, `run_2.log` and `run_3.log`.

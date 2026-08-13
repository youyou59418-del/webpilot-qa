# Day 12 - Regression Script Generator

Only a `workflow.json` whose status is `passed` can be converted to a regression test. The generator rejects failed actions, missing semantic targets, password/card-like form fields, and redacted values. It creates an isolated BrowserContext and semantic Playwright locators, never temporary `e1` references or CSS selectors.

```bash
./.venv/bin/python scripts/generate_regression_test.py artifacts/runs/<run_id>/workflow.json \
  --out artifacts/regression/test_generated.py --test-name shopbench_search
for repeat in 1 2 3; do ./.venv/bin/python -m pytest -q artifacts/regression/test_generated.py; done
```

The generated script is only accepted after three fresh-context passes and its report records the trajectory source, generated file, and repeat count.

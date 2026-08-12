# Day 4: Planner, per-step execution, and independent verification

Day 4 adds a strict workflow:

```text
Planner -> ordered TestPlan -> Actor executes one plan step -> Verifier reads live browser state
```

The Planner only returns a structured plan. The Actor can still use only the
Day 3 allowlisted browser tools. The Verifier is the final authority for each
completed step: an Actor `DONE` message alone never marks a step successful.

## Scope and non-goals

- Supported deterministic rules: `url_contains`, `visible_text_contains`, and
  `element_text_equals`.
- `element_text_equals` requires both a semantic ARIA role and a semantic name.
- Plan step ids must be exactly ordered as `step_1`, `step_2`, ... .
- Day 4 has no retry, replanning-after-failure, locator healing, or LLM Judge.
  Those are Day 5 and later responsibilities.

## Offline acceptance

No API key is required for the controlled workflow demonstration:

```bash
cd /root/autodl-tmp/webpilot-qa
.venv/bin/python -m pytest -q tests/test_planner.py tests/test_verifier.py tests/test_day4_workflow.py
.venv/bin/python scripts/day4_workflow_demo.py
.venv/bin/python -m pytest -q
```

The demonstration uses a scripted model double and proves that the workflow
stores the plan, action history, independent verification evidence, and final
state. It is not a real-model quality measurement.

## Real model run

Use the same OpenAI-compatible configuration as Day 3. Keep credentials only
in the current shell or an approved secret manager; do not commit them or put
them in artifacts.

```bash
export LLM_BASE_URL='https://provider.example/v1'
export LLM_API_KEY='your-secret-key'
export LLM_MODEL='your-model-id'
export LLM_TIMEOUT_S='60'

.venv/bin/python scripts/run_day4.py \\
  --goal 'Search for laptop and stop only when the page says Results for: laptop.' \\
  --start-url "file://$(pwd)/tests/fixtures/day3_agent.html" \\
  --max-steps 6 \\
  --output artifacts/day4/real_run.json
```

Exit code `0` means each plan step received `PASS` from the independent
Verifier. Exit code `1` means the plan, actor execution, or verification
failed and the JSON artifact explains which one. Exit code `2` means the LLM
configuration is missing or invalid.

# Day 5: Failure-Aware Recovery

Day 5 extends the Day 4 formal workflow with bounded recovery:

```text
Planner -> Actor -> Verifier -> FailureClassifier -> RecoveryPolicy
                                      |                    |
                                      +---- evidence -------+
```

The recovery policy never permits an unbounded retry. Each failure becomes a
typed `FailureEvent`, a policy decision, and a record in the final run JSON.

## Supported recovery behavior

| Failure | Action | Bound |
| --- | --- | --- |
| stale/missing element ref | `RE_OBSERVE` | consumes one retry; the Actor receives fresh refs |
| invisible element | `SHORT_WAIT` then re-observe | consumes one retry |
| timeout | `RETRY_ONCE` | consumes one retry |
| page changed | `RE_OBSERVE` | consumes one retry |
| URL verification shows wrong page / failed verification | `REPLAN` | consumes one retry and provides failure evidence to Planner |
| forbidden or unknown action | `STOP` | never retried |

Day 5 intentionally does not introduce selector healing. Day 6 will match
semantic targets after DOM drift; Day 5 only re-observes and lets the Actor or
Planner choose a valid current reference.

## Offline acceptance

```bash
cd /root/autodl-tmp/webpilot-qa
.venv/bin/python -m pytest -q tests/test_recovery_models.py tests/test_recovery_classifier.py tests/test_recovery_policy.py tests/test_day5_formal_workflow.py
.venv/bin/python scripts/day5_formal_workflow_demo.py
.venv/bin/python scripts/run_day5_recovery_benchmark.py
.venv/bin/python -m pytest -q
```

The controlled benchmark only measures one injected stale-reference case. Its
success rate is not a real-model or real-site success rate.

## Real-model entry point

Configure `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, and optionally
`LLM_TIMEOUT_S` only in the current shell or a secret manager. Do not commit
credentials or artifacts.

```bash
.venv/bin/python scripts/run_day5.py \
  --goal 'Search for laptop and stop only when the page says Results for: laptop.' \
  --start-url "file://$(pwd)/tests/fixtures/day3_agent.html" \
  --max-steps 6 \
  --max-retries 2 \
  --output artifacts/day5/real_run.json
```

The result is successful only when every final plan step receives independent
Verifier `PASS`. Inspect `state.recovery_history`, `state.plan_history`, and
`state.step_verifications` to distinguish an initial failure from a verified
recovery.

# Verified run status

## Code and deployment

- Full Python test suite: **107 passed** after the final strict-evaluation and planner changes.
- Local model service: Qwen2.5-7B-Instruct is running through the OpenAI-compatible vLLM endpoint; both ordinary chat and constrained tool-call checks have passed.
- WebPilot API and local ShopBench station are online at the project-local endpoints.

## Day 11 strict evaluation — current baseline

The authoritative report is `artifacts/evaluation/day11/qwen-full-100-strict/report.json`.

- Model: `Qwen2.5-7B-Instruct-vllm`
- Tasks: all 100 fixed ShopBench v1 tasks, fresh browser context per task
- Budget: 6 actions and 2 retries per task
- Passed: **8 / 100 (8.0%)**
- Safety blocked: **10 / 100** — these are not counted as passes.
- Failed: **82 / 100**
- By difficulty: Easy 8/30 passed; Medium 0/40; Hard 0/30.

The score is strict: a workflow must first pass its independent browser verifier and then match ShopBench's public `expected_state` field-by-field. This removes false positives caused by default option text appearing in page text. The earlier `qwen-full-100-snapshot` 30% report uses the old text-only scoring and is retained only as a superseded diagnostic artifact; it is not a project metric.

The current model/runtime integration is complete, but the 8% strict performance baseline is not suitable for a production-success claim. The main remaining quality work is improving planning/action fidelity or evaluating a stronger approved model using this same strict harness.

## Controlled ablation

`artifacts/evaluation/day11/qwen-ablation-strict/summary/ablation.md` uses the same five non-sensitive task IDs (E05, E07, E08, E09, E29), Qwen model, six-action budget and two retries for every variant:

| Variant | Passed |
| --- | ---: |
| full | 4/5 |
| no_recovery | 3/5 |
| no_self_healing | 4/5 |
| no_verifier | 0/5 |
| single_agent | 0/5 |

This small gate shows that verification is essential to reliable completion on this task slice, recovery adds one successful task, and this slice did not exercise a self-healing advantage. It is a controlled component comparison, not a substitute for the 100-task strict score.

## Day 12 live regression

A passed, non-sensitive E05 trajectory (`0fb88fd9-8cdc-4fa1-8dc6-3654c270dbdd`) generated `artifacts/regression/day12_e05/test_e05_open_help.py`. It uses semantic Playwright locators and passed three independent fresh-context executions (`run_1.log` through `run_3.log`).

No failed or safety-blocked trajectory is eligible for regression generation.

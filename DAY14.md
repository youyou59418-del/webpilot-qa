# Day 14 - Final project handoff

The final handoff is the repository README, architecture, demo sequence, interview evidence rules, Day 11 reports, and Day 12 generated regression tests. Before publishing a resume metric or demo claim, verify it points to a `live_model` evaluation artifact and a reproducible command.

Final acceptance commands:

```bash
./.venv/bin/python -m pytest -q
./.tools/node/bin/npm --prefix console run build
./.venv/bin/python scripts/run_day11_evaluation.py --mode dry-run
```

Then archive the Day 13 environment fact sheet and the completed live ShopBench report alongside the repository commit used for the demo.

Use `docs/RUN_STATUS.md` when presenting the project: it separates verified service integration, test-suite acceptance and real model-performance evidence. Do not turn an API-health check, a dry-run, or a safety-blocked task into a success-rate claim.

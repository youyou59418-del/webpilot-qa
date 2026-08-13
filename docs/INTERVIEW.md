# Interview evidence and boundaries

## Explain the design

- Structured observations replace raw selectors so a model sees the current semantic interaction surface.
- The verifier checks browser state, rather than accepting a model's claim that a task is complete.
- Recovery has a bounded budget; self-healing refuses ambiguous matches.
- Safety approval is tied to the semantic action, not a temporary page reference.
- ShopBench is controlled and resettable, separating reproducible evaluation from real-site demonstrations.

## Evidence rule

Only cite measurements from `artifacts/evaluation/**/report.json` whose execution mode is `live_model`. Dry-run reports, unit tests, and architecture claims are not success-rate evidence. Report blocked high-risk tasks separately from model failures.

## Limitations

- SQLite and one local worker are intentionally the current single-instance mode.
- Browser contexts isolate sessions, not the operating system.
- Local vLLM compatibility does not imply external-API-quality tool use.
- The regression generator excludes sensitive inputs and only accepts verified successful trajectories.

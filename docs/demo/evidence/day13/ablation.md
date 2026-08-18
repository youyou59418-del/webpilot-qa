# Day 11 ablation comparison

| Variant | Attempted | Passed | Safety blocked | Failed | Success rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| full | 5 | 3 | 0 | 2 | 60.0% |
| no_recovery | 5 | 2 | 0 | 3 | 40.0% |
| no_self_healing | 5 | 3 | 0 | 2 | 60.0% |
| no_verifier | 5 | 3 | 0 | 2 | 60.0% |
| single_agent | 5 | 0 | 0 | 5 | 0.0% |

Only compare rows with the same task IDs, model, budgets and retry policy.

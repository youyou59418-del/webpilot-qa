# Verified run status

The repository has a clean code-level acceptance result: the full test suite passes. The local Qwen service is independently checked through its OpenAI-compatible model listing, a constrained chat response, and a required function call.

The Day 11 artifact directory contains two different kinds of evidence:

- `dry-run` files validate report and task contracts only; they are never model scores.
- `live_model` files are real execution evidence. The current three-task, equal-budget ablation gate records zero successful completions for Qwen2.5-7B-Instruct. One login task was correctly stopped by the safety gate; the other two expose planning/recovery limits. This is a deployment finding, not a deployment success claim.

Day 12's generator and three fresh-context executions are covered by the automated suite. A production regression artifact must still originate from a passed, non-sensitive live trajectory; no failed or safety-blocked trajectory may be converted.

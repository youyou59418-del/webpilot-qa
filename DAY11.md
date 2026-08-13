# Day 11 - Strict Evaluation and Ablation

The evaluation runner creates a durable API run for every fixed ShopBench task and writes JSON, CSV, Markdown and SVG evidence. A live-model score is accepted only when both conditions hold:

1. WebPilot's independent browser verifier reports workflow completion.
2. The executor captures the ShopBench public controlled state before closing its browser context, and every key in the task's `expected_state` matches that captured state.

This second condition prevents default option text from being incorrectly scored as a completed action.

```bash
# Contract smoke check: never a model metric.
./.venv/bin/python scripts/run_day11_evaluation.py --mode dry-run   --output-dir artifacts/evaluation/day11/dry-run

# Strict full evaluation: one fresh browser context per task.
./.venv/bin/python scripts/run_day11_evaluation.py --mode live --variant full   --model-name Qwen2.5-7B-Instruct-vllm --max-steps 6 --max-retries 2   --output-dir artifacts/evaluation/day11/qwen-full-100-strict

# Controlled ablation: identical task IDs, model and budgets for every row.
for variant in full single_agent no_verifier no_recovery no_self_healing; do
  ./.venv/bin/python scripts/run_day11_evaluation.py --mode live --variant "$variant"     --model-name Qwen2.5-7B-Instruct-vllm     --task-id E05 --task-id E07 --task-id E08 --task-id E09 --task-id E29     --max-steps 6 --max-retries 2     --output-dir "artifacts/evaluation/day11/qwen-ablation-strict/$variant"
done
./.venv/bin/python scripts/summarize_day11_ablations.py   --input-root artifacts/evaluation/day11/qwen-ablation-strict   --output-dir artifacts/evaluation/day11/qwen-ablation-strict/summary
```

The verified Qwen 7B strict baseline is 8/100. This is a genuine baseline, not a completion claim; use the same strict runner for later prompt, model or agent changes.

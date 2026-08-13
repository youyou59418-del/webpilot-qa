# Day 11 - Evaluation and Ablation

The evaluation runner consumes the fixed ShopBench task contract through the Day 8 API and writes JSON, CSV, and Markdown artifacts. It records task ID, difficulty, run ID, terminal result, duration, tool calls, retries, and failure category.

```bash
# Contract smoke check: does not claim a model success rate.
./.venv/bin/python scripts/run_day11_evaluation.py --mode dry-run --output-dir artifacts/evaluation/day11/dry-run

# Live model evaluation after ShopBench, API/Worker and a configured LLM are running.
./.venv/bin/python scripts/run_day11_evaluation.py --mode live --model-name Qwen2.5-7B-Instruct --limit 5 --output-dir artifacts/evaluation/day11/qwen-gate

# A controlled ablation gate: same task IDs, model, four-action budget and no retries.
for variant in single_agent no_verifier no_recovery no_self_healing full; do
  ./.venv/bin/python scripts/run_day11_evaluation.py --mode live --variant "$variant" \
    --model-name Qwen2.5-7B-Instruct --task-id E01 --task-id E02 --task-id E05 \
    --max-steps 4 --max-retries 0 --output-dir "artifacts/evaluation/day11/ablation/$variant"
done
./.venv/bin/python scripts/summarize_day11_ablations.py \
  --input-root artifacts/evaluation/day11/ablation \
  --output-dir artifacts/evaluation/day11/ablation/summary
```

Run each ablation with the same task IDs, model, context budget and retries. Only compare `live_model` reports; a `dry_run` validates contracts but is deliberately excluded from performance claims.

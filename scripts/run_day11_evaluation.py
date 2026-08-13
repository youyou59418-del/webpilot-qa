from __future__ import annotations

import argparse
from pathlib import Path

from shopbench.tasks import by_difficulty, get_task
from webpilot.evaluation.runner import EvaluationRunner, write_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dry-run", "live"], default="dry-run")
    parser.add_argument("--variant", default="full")
    parser.add_argument("--model-name", default="unconfigured")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--shopbench-url", default="http://127.0.0.1:8080")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    parser.add_argument(
        "--task-id",
        action="append",
        help="Run one or more explicit ShopBench IDs, preserving the supplied order.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evaluation/day11"))
    args = parser.parse_args()
    if args.task_id:
        tasks = []
        for task_id in args.task_id:
            task = get_task(task_id)
            if task is None:
                parser.error(f"Unknown ShopBench task ID: {task_id}")
            tasks.append(task)
    else:
        tasks = by_difficulty(args.difficulty)
    if args.limit is not None:
        tasks = tasks[:args.limit]
    runner = EvaluationRunner(api_url=args.api_url, shopbench_url=args.shopbench_url)
    report = (
        runner.dry_run(tasks=tasks, variant=args.variant, model_name=args.model_name)
        if args.mode == "dry-run"
        else runner.run_live(
            tasks=tasks,
            variant=args.variant,
            model_name=args.model_name,
            max_steps=args.max_steps,
            max_retries=args.max_retries,
        )
    )
    for name, path in write_report(report, args.output_dir).items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()

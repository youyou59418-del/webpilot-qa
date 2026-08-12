import json
from pathlib import Path


def test_day3_local_baseline_has_twenty_unique_tasks() -> None:
    path = Path("benchmarks/tasks/day3_local_tasks.json")
    tasks = json.loads(path.read_text(encoding="utf-8"))

    assert len(tasks) == 20
    assert len({task["id"] for task in tasks}) == 20
    assert all(task["goal"].strip() for task in tasks)
    assert all(task["expected_text"].strip() for task in tasks)

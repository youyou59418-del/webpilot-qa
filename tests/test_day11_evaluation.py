import json

from shopbench.tasks import all_tasks, get_task
from webpilot.evaluation.runner import EvaluationRunner, write_report


def test_dry_run_report_is_explicitly_non_metric_and_writes_artifacts(tmp_path) -> None:
    report = EvaluationRunner(
        api_url="http://api.test",
        shopbench_url="http://shop.test",
    ).dry_run(tasks=all_tasks()[:3], variant="full", model_name="unconfigured")

    assert report.execution_mode == "dry_run"
    assert report.attempted_count == 0
    assert report.success_rate is None
    paths = write_report(report, tmp_path)
    assert json.loads(paths["json"].read_text())["outcomes"][0]["status"] == "skipped"
    assert "not measured" in paths["markdown"].read_text()
    assert paths["csv"].read_text().count("\n") == 4
    assert "<svg" in paths["chart"].read_text()


def test_live_goal_includes_the_public_shopbench_oracle() -> None:
    task = get_task("E05")
    assert task is not None

    goal = EvaluationRunner._benchmark_goal(task)

    assert goal.startswith(task.goal)
    assert "BENCHMARK ACCEPTANCE STATE" in goal
    assert '"dialog_open": "ShopBench help"' in goal


def test_shopbench_state_oracle_rejects_default_option_text_false_positive() -> None:
    task = get_task("E21")
    assert task is not None
    runner = EvaluationRunner(api_url="http://api.test", shopbench_url="http://shop.test")

    mismatch = runner._validate_shopbench_state(
        task,
        final_shopbench_state={
            "category": "All",
            "search": "",
            "cart_count": 0,
        },
    )

    assert mismatch is not None
    assert "category" in mismatch


def test_shopbench_state_oracle_accepts_expected_cart_membership() -> None:
    task = get_task("E29")
    assert task is not None
    runner = EvaluationRunner(api_url="http://api.test", shopbench_url="http://shop.test")

    mismatch = runner._validate_shopbench_state(
        task,
        final_shopbench_state={
            "cart_count": 1,
            "cart_contains": ["Laptop Pro"],
        },
    )

    assert mismatch is None

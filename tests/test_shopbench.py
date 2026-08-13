import httpx
import pytest

from shopbench.app import create_app
from shopbench.tasks import all_tasks, by_difficulty


def test_shopbench_has_fixed_coverage_and_balanced_difficulties() -> None:
    tasks = all_tasks()
    assert len(tasks) == 100
    assert len({task.id for task in tasks}) == 100
    assert {task.difficulty for task in tasks} == {"easy", "medium", "hard"}
    assert len(by_difficulty("easy")) == 30
    assert len(by_difficulty("medium")) == 40
    assert len(by_difficulty("hard")) == 30
    assert all(task.start_path == "/?reset=1" for task in tasks)
    modules = {module for task in tasks for module in task.modules}
    assert modules >= {
        "login", "search", "filter", "cart", "forms", "tables",
        "pagination", "dialog", "tabs", "dynamic_dom", "toast",
        "loading", "error",
    }


@pytest.mark.asyncio
async def test_shopbench_api_is_repeatable_and_serves_controlled_page() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://shopbench.test",
    ) as client:
        health = await client.get("/health")
        assert health.json() == {"status": "ok", "service": "shopbench", "task_count": 100}
        first = await client.get("/api/tasks")
        second = await client.get("/api/tasks")
        assert first.json() == second.json()
        assert len(first.json()) == 100
        assert len((await client.get("/api/tasks?difficulty=hard")).json()) == 30
        assert (await client.get("/api/tasks/E01")).json()["id"] == "E01"
        assert (await client.get("/api/tasks/missing")).status_code == 404
        page = await client.get("/?reset=1")
        assert "ShopBench v1" in page.text
        assert "Reset benchmark state" in page.text

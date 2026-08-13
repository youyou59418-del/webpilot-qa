from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shopbench.tasks import Difficulty, all_tasks, by_difficulty, get_task


STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="ShopBench v1", version="1.0.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "shopbench",
            "task_count": len(all_tasks()),
        }

    @app.get("/api/tasks")
    async def list_tasks(
        difficulty: Difficulty | None = Query(default=None),
    ) -> list[dict[str, object]]:
        return [task.model_dump(mode="json") for task in by_difficulty(difficulty)]

    @app.get("/api/tasks/{task_id}")
    async def task_detail(task_id: str) -> dict[str, object]:
        task = get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Unknown ShopBench task: {task_id}")
        return task.model_dump(mode="json")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app

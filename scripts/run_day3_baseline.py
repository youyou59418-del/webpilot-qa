from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from webpilot.agents.actor import BrowserActor
from webpilot.agents.loop import AgentRunResult, SingleBrowserAgent
from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.llm.adapter import OpenAICompatibleLLM


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS_PATH = PROJECT_ROOT / "benchmarks" / "tasks" / "day3_local_tasks.json"
DEFAULT_FIXTURE_URL = (
    PROJECT_ROOT / "tests" / "fixtures" / "day3_agent.html"
).as_uri()
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "day3" / "baseline.json"


@dataclass(frozen=True)
class BaselineTask:
    task_id: str
    goal: str
    expected_text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the 20-task Day 3 local single-agent baseline."
    )
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS_PATH)
    parser.add_argument("--start-url", default=DEFAULT_FIXTURE_URL)
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def load_tasks(path: Path) -> list[BaselineTask]:
    try:
        raw_tasks = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Task file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Task file is not valid JSON: {path}") from exc

    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise RuntimeError("Task file must contain a non-empty JSON list.")

    tasks: list[BaselineTask] = []
    seen_ids: set[str] = set()
    for item in raw_tasks:
        if not isinstance(item, dict):
            raise RuntimeError("Every task must be a JSON object.")
        task = BaselineTask(
            task_id=_required_task_string(item, "id"),
            goal=_required_task_string(item, "goal"),
            expected_text=_required_task_string(item, "expected_text"),
        )
        if task.task_id in seen_ids:
            raise RuntimeError(f"Duplicate task id: {task.task_id}")
        seen_ids.add(task.task_id)
        tasks.append(task)
    return tasks


def _required_task_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Task field {key!r} must be a non-empty string.")
    return value.strip()


async def run_task(
    *,
    llm: OpenAICompatibleLLM,
    task: BaselineTask,
    start_url: str,
    max_steps: int,
) -> dict[str, Any]:
    runtime = BrowserRuntime()
    observation_engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, observation_engine)
    agent = SingleBrowserAgent(
        actor=BrowserActor(llm),
        observation_engine=observation_engine,
        tools=tools,
        max_steps=max_steps,
    )

    started_at = perf_counter()
    await runtime.start()
    try:
        result = await agent.run(
            goal=task.goal,
            target_url=start_url,
        )
    finally:
        await runtime.close()

    return result_to_record(task, result, perf_counter() - started_at)


def result_to_record(
    task: BaselineTask,
    result: AgentRunResult,
    elapsed_s: float,
) -> dict[str, Any]:
    expected_state_present = (
        task.expected_text in result.final_observation.visible_text
    )
    accepted = result.status == "completed" and expected_state_present
    return {
        "task_id": task.task_id,
        "status": result.status,
        "accepted": accepted,
        "expected_text": task.expected_text,
        "final_visible_text": result.final_observation.visible_text,
        "steps": result.steps,
        "tool_calls": result.tool_calls,
        "duration_ms": round(elapsed_s * 1000),
        "agent_message": result.message,
        "error": result.error,
    }


async def main() -> int:
    args = parse_args()
    tasks = load_tasks(args.tasks)
    llm = OpenAICompatibleLLM.from_env()
    records = [
        await run_task(
            llm=llm,
            task=task,
            start_url=args.start_url,
            max_steps=args.max_steps,
        )
        for task in tasks
    ]

    accepted = [record for record in records if record["accepted"]]
    summary = {
        "task_count": len(records),
        "task_success_rate": len(accepted) / len(records),
        "average_steps": mean(record["steps"] for record in records),
        "average_tool_calls": mean(record["tool_calls"] for record in records),
        "average_duration_ms": mean(record["duration_ms"] for record in records),
    }
    payload = {"summary": summary, "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved detailed Day 3 baseline to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

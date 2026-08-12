from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from time import perf_counter

from webpilot.agents.planner import (
    SuccessCriterion,
)
from webpilot.browser.observation import (
    ObservationEngine,
)
from webpilot.browser.runtime import (
    BrowserRuntime,
)
from webpilot.browser.tools import (
    BrowserToolExecutor,
)
from webpilot.recovery.classifier import (
    FailureClassifier,
)
from webpilot.recovery.models import (
    RecoveryAction,
    RetryBudget,
)
from webpilot.recovery.policy import (
    RecoveryPolicy,
)
from webpilot.verifier.rules import (
    RuleVerifier,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "day3_agent.html"
)

OUTPUT = (
    PROJECT_ROOT
    / "artifacts"
    / "day5"
    / "recovery_benchmark.json"
)


async def current_url(
    runtime,
):
    value = runtime.current_url()

    if inspect.isawaitable(
        value
    ):
        return await value

    return value


async def run_trial(
    trial_id: int,
):
    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

    started = perf_counter()

    tool_calls = 0
    retries = 0

    try:
        await runtime.open_url(
            FIXTURE.as_uri()
        )

        engine = ObservationEngine()

        tools = BrowserToolExecutor(
            runtime,
            engine,
        )

        classifier = (
            FailureClassifier()
        )

        policy = RecoveryPolicy()

        budget = RetryBudget(
            max_retries=2
        )

        observation = await engine.observe(
            runtime
        )

        textbox_ref = next(
            element.ref
            for element
            in observation.elements
            if (
                element.role
                == "textbox"
                and (
                    element.name
                    == "Search Products"
                    or
                    element.placeholder
                    == "Enter product name"
                )
            )
        )

        value = (
            f"laptop-{trial_id}"
        )

        await tools.execute(
            "fill",
            {
                "ref": textbox_ref,
                "value": value,
            },
        )

        tool_calls += 1

        try:
            await tools.execute(
                "click",
                {
                    "ref": "e999",
                },
            )

            tool_calls += 1

        except Exception as exc:
            # Failed tool call is still a tool call.
            tool_calls += 1

            failure = (
                classifier
                .from_exception(
                    exc=exc,
                    step_id="step_1",
                    retry_count=(
                        budget.retry_count
                    ),
                    tool_name="click",
                    element_ref="e999",
                    current_url=(
                        await current_url(
                            runtime
                        )
                    ),
                )
            )

        decision = policy.decide(
            failure=failure,
            budget=budget,
        )

        if (
            decision.action
            != RecoveryAction.RE_OBSERVE
        ):
            return {
                "trial_id": trial_id,
                "success": False,
                "reason": (
                    "unexpected recovery action"
                ),
                "tool_calls": tool_calls,
                "retries": retries,
            }

        if decision.consume_retry:
            budget.consume()
            retries += 1

        observation = await engine.observe(
            runtime
        )

        button_ref = next(
            element.ref
            for element
            in observation.elements
            if (
                element.role == "button"
                and element.name == "Search"
            )
        )

        await tools.execute(
            "click",
            {
                "ref": button_ref,
            },
        )

        tool_calls += 1

        observation = await engine.observe(
            runtime
        )

        verification = (
            RuleVerifier()
            .verify(
                observation=observation,
                criteria=[
                    SuccessCriterion(
                        rule=(
                            "visible_text_contains"
                        ),
                        expected=(
                            f"Results for: {value}"
                        ),
                    )
                ],
            )
        )

        duration = (
            perf_counter()
            - started
        )

        return {
            "trial_id": trial_id,
            "success": (
                verification.status
                == "PASS"
            ),
            "failure_type": (
                failure.failure_type.value
            ),
            "recovery_action": (
                decision.action.value
            ),
            "retry_count": (
                budget.retry_count
            ),
            "tool_calls": tool_calls,
            "duration_s": round(
                duration,
                4,
            ),
        }

    finally:
        await runtime.close()


async def main():
    trial_count = 20

    records = []

    for trial_id in range(
        1,
        trial_count + 1,
    ):
        print(
            f"Running recovery trial "
            f"{trial_id}/{trial_count}"
        )

        record = await run_trial(
            trial_id
        )

        records.append(
            record
        )

    recovered = sum(
        1
        for record in records
        if record.get(
            "success"
        )
    )

    rate = (
        recovered / trial_count
        if trial_count
        else 0.0
    )

    average_tool_calls = (
        sum(
            record.get(
                "tool_calls",
                0,
            )
            for record in records
        )
        / trial_count
    )

    average_retries = (
        sum(
            record.get(
                "retry_count",
                0,
            )
            for record in records
        )
        / trial_count
    )

    payload = {
        "benchmark_type": (
            "controlled_fixture_recovery"
        ),
        "failure_injected": (
            "ELEMENT_NOT_FOUND"
        ),
        "trial_count": trial_count,
        "recovery_success_count": (
            recovered
        ),
        "recovery_success_rate": (
            rate
        ),
        "average_tool_calls": (
            average_tool_calls
        ),
        "average_retries": (
            average_retries
        ),
        "records": records,
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "\n========================================"
    )

    print(
        "Day 5 Recovery Benchmark"
    )

    print(
        "========================================"
    )

    print(
        "Trials:",
        trial_count,
    )

    print(
        "Recovered:",
        recovered,
    )

    print(
        "Recovery Success Rate:",
        f"{rate:.2%}",
    )

    print(
        "Average Tool Calls:",
        round(
            average_tool_calls,
            3,
        ),
    )

    print(
        "Average Retries:",
        round(
            average_retries,
            3,
        ),
    )

    print(
        "Saved:",
        OUTPUT,
    )


if __name__ == "__main__":
    asyncio.run(main())

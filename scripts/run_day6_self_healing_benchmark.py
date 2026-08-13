from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter

from webpilot.agents.planner import (
    SuccessCriterion,
)
from webpilot.browser.locator import (
    SelfHealingAmbiguousError,
    SelfHealingLocator,
    SelfHealingNotFoundError,
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
    / "day6_self_healing.html"
)

OUTPUT = (
    PROJECT_ROOT
    / "artifacts"
    / "day6"
    / "self_healing_benchmark.json"
)


MODES = [
    "rename",
    "id",
    "structure",
    "combined",
    "ambiguous",
]


async def run_trial(
    *,
    trial_id: int,
    mode: str,
):
    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

    started = perf_counter()

    try:
        await runtime.open_url(
            FIXTURE.as_uri()
            + f"?mode={mode}"
        )

        engine = ObservationEngine()

        tools = BrowserToolExecutor(
            runtime,
            engine,
        )

        healer = SelfHealingLocator(
            min_score=0.55,
            min_margin=0.08,
        )

        observation = await engine.observe(
            runtime
        )

        login = next(
            element
            for element
            in observation.elements
            if (
                element.role == "button"
                and element.name == "Login"
            )
        )

        signature = await healer.capture(
            engine=engine,
            element=login,
        )

        mutate = next(
            element
            for element
            in observation.elements
            if (
                element.role == "button"
                and element.name
                == "Mutate DOM"
            )
        )

        await tools.execute(
            "click",
            {
                "ref": mutate.ref,
            },
        )

        observation = await engine.observe(
            runtime
        )

        try:
            healing = await healer.heal(
                engine=engine,
                observation=observation,
                target=signature,
            )

        except SelfHealingAmbiguousError as exc:
            return {
                "trial_id": trial_id,
                "mode": mode,
                "locator_recovered": False,
                "task_success": False,
                "false_match": False,
                "safe_rejection": True,
                "failure_reason": (
                    "AMBIGUOUS"
                ),
                "details": str(exc),
                "duration_s": round(
                    perf_counter()
                    - started,
                    4,
                ),
            }

        except SelfHealingNotFoundError as exc:
            return {
                "trial_id": trial_id,
                "mode": mode,
                "locator_recovered": False,
                "task_success": False,
                "false_match": False,
                "safe_rejection": True,
                "failure_reason": (
                    "NOT_FOUND"
                ),
                "details": str(exc),
                "duration_s": round(
                    perf_counter()
                    - started,
                    4,
                ),
            }

        # -----------------------------------------
        # Execute healed candidate
        # -----------------------------------------

        await tools.execute(
            "click",
            {
                "ref": healing.healed_ref,
            },
        )

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
                        expected="Authenticated",
                    )
                ],
            )
        )

        success = (
            verification.status
            == "PASS"
        )

        return {
            "trial_id": trial_id,
            "mode": mode,
            "locator_recovered": True,
            "task_success": success,
            "false_match": (
                not success
            ),
            "safe_rejection": False,
            "healed_ref": (
                healing.healed_ref
            ),
            "score": (
                healing.score
            ),
            "margin": (
                healing.margin
            ),
            "reasons": (
                healing.reasons
            ),
            "duration_s": round(
                perf_counter()
                - started,
                4,
            ),
        }

    finally:
        await runtime.close()


async def main():
    records = []

    trial_id = 0

    for mode in MODES:
        for repetition in range(4):
            trial_id += 1

            print(
                f"Trial "
                f"{trial_id}/20 "
                f"mode={mode}"
            )

            record = await run_trial(
                trial_id=trial_id,
                mode=mode,
            )

            records.append(
                record
            )

    trial_count = len(
        records
    )

    recovered_count = sum(
        1
        for item in records
        if item[
            "locator_recovered"
        ]
    )

    task_success_count = sum(
        1
        for item in records
        if item[
            "task_success"
        ]
    )

    false_match_count = sum(
        1
        for item in records
        if item[
            "false_match"
        ]
    )

    safe_rejection_count = sum(
        1
        for item in records
        if item[
            "safe_rejection"
        ]
    )

    recovery_rate = (
        recovered_count
        / trial_count
        if trial_count
        else 0.0
    )

    task_success_rate = (
        task_success_count
        / trial_count
        if trial_count
        else 0.0
    )

    false_match_rate = (
        false_match_count
        / recovered_count
        if recovered_count
        else 0.0
    )

    payload = {
        "benchmark_type": (
            "controlled_self_healing"
        ),
        "trial_count": (
            trial_count
        ),
        "locator_recovery_count": (
            recovered_count
        ),
        "locator_recovery_rate": (
            recovery_rate
        ),
        "task_success_count": (
            task_success_count
        ),
        "task_success_rate": (
            task_success_rate
        ),
        "false_match_count": (
            false_match_count
        ),
        "false_match_rate": (
            false_match_rate
        ),
        "safe_rejection_count": (
            safe_rejection_count
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
        "Day 6 Self-Healing Benchmark"
    )

    print(
        "========================================"
    )

    print(
        "Trials:",
        trial_count,
    )

    print(
        "Locator Recovered:",
        recovered_count,
    )

    print(
        "Locator Recovery Rate:",
        f"{recovery_rate:.2%}",
    )

    print(
        "Task Success:",
        task_success_count,
    )

    print(
        "Task Success Rate:",
        f"{task_success_rate:.2%}",
    )

    print(
        "False Matches:",
        false_match_count,
    )

    print(
        "False Match Rate:",
        f"{false_match_rate:.2%}",
    )

    print(
        "Safe Rejections:",
        safe_rejection_count,
    )

    print(
        "Saved:",
        OUTPUT,
    )


if __name__ == "__main__":
    asyncio.run(main())

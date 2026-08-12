from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

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


async def get_current_url(
    runtime: BrowserRuntime,
) -> str:
    value = runtime.current_url()

    if inspect.isawaitable(
        value
    ):
        return await value

    return value


async def main():
    print(
        "========================================"
    )
    print(
        "WebPilot-QA Day 5"
    )
    print(
        "Failure-Aware Recovery Demo"
    )
    print(
        "========================================"
    )

    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

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

        # =========================================
        # Initial observation
        # =========================================

        observation = await engine.observe(
            runtime
        )

        textbox_ref = None

        for element in observation.elements:
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
            ):
                textbox_ref = (
                    element.ref
                )

                break

        if textbox_ref is None:
            raise RuntimeError(
                "Search textbox not found"
            )

        print(
            "\nInitial textbox ref:",
            textbox_ref,
        )

        await tools.execute(
            "fill",
            {
                "ref": textbox_ref,
                "value": "laptop",
            },
        )

        print(
            "\nFilled textbox with laptop"
        )

        # =========================================
        # Inject failure
        # =========================================

        print(
            "\nInjecting invalid ref e999..."
        )

        try:
            await tools.execute(
                "click",
                {
                    "ref": "e999",
                },
            )

        except Exception as exc:
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
                        await get_current_url(
                            runtime
                        )
                    ),
                )
            )

        else:
            raise RuntimeError(
                "Injected failure did not fail"
            )

        print(
            "\nFailure Event:"
        )

        print(
            json.dumps(
                failure.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

        # =========================================
        # Recovery policy
        # =========================================

        decision = policy.decide(
            failure=failure,
            budget=budget,
        )

        print(
            "\nRecovery Decision:"
        )

        print(
            json.dumps(
                decision.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

        if (
            decision.action
            != RecoveryAction.RE_OBSERVE
        ):
            raise RuntimeError(
                "Expected RE_OBSERVE"
            )

        if decision.consume_retry:
            budget.consume()

        print(
            "\nRetry Budget:"
        )

        print(
            "retry_count:",
            budget.retry_count,
        )

        print(
            "remaining:",
            budget.remaining,
        )

        # =========================================
        # Fresh Observation
        # =========================================

        observation = await engine.observe(
            runtime
        )

        search_ref = None

        for element in observation.elements:
            if (
                element.role
                == "button"
                and element.name
                == "Search"
            ):
                search_ref = (
                    element.ref
                )

                break

        if search_ref is None:
            raise RuntimeError(
                "Search button not found"
            )

        print(
            "\nFresh Search button ref:",
            search_ref,
        )

        await tools.execute(
            "click",
            {
                "ref": search_ref,
            },
        )

        # =========================================
        # Final verification
        # =========================================

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
                            "Results for: laptop"
                        ),
                    )
                ],
            )
        )

        print(
            "\nFinal Verification:"
        )

        print(
            json.dumps(
                verification.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

        if (
            verification.status
            != "PASS"
        ):
            raise RuntimeError(
                "Recovery verification failed"
            )

        print(
            "\n========================================"
        )

        print(
            "Day 5 Recovery Demo PASSED"
        )

        print(
            "========================================"
        )

    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())

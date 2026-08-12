from __future__ import annotations

import inspect
from pathlib import Path

import pytest

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
    FailureType,
    RecoveryAction,
    RetryBudget,
)
from webpilot.recovery.policy import (
    RecoveryPolicy,
)
from webpilot.verifier.rules import (
    RuleVerifier,
)


FIXTURE = (
    Path(__file__).resolve().parent
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


@pytest.mark.asyncio
async def test_element_not_found_reobserve_recovery():
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

        # -----------------------------------------
        # Initial Observation
        # -----------------------------------------

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

        assert (
            textbox_ref
            is not None
        )

        # -----------------------------------------
        # Normal action
        # -----------------------------------------

        await tools.execute(
            "fill",
            {
                "ref": textbox_ref,
                "value": "laptop",
            },
        )

        # -----------------------------------------
        # Inject invalid/stale ref
        # -----------------------------------------

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
            raise AssertionError(
                "Invalid ref unexpectedly succeeded"
            )

        # -----------------------------------------
        # Classification
        # -----------------------------------------

        assert (
            failure.failure_type
            == FailureType.ELEMENT_NOT_FOUND
        )

        # -----------------------------------------
        # Policy
        # -----------------------------------------

        decision = policy.decide(
            failure=failure,
            budget=budget,
        )

        assert (
            decision.action
            == RecoveryAction.RE_OBSERVE
        )

        if decision.consume_retry:
            budget.consume()

        # -----------------------------------------
        # Recovery:
        # MUST create fresh Observation
        # -----------------------------------------

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

        assert (
            search_ref
            is not None
        )

        # -----------------------------------------
        # Recovered action
        # -----------------------------------------

        await tools.execute(
            "click",
            {
                "ref": search_ref,
            },
        )

        # -----------------------------------------
        # Recovery MUST be followed by
        # fresh Observation + Verifier.
        # -----------------------------------------

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

        assert (
            verification.status
            == "PASS"
        )

        assert (
            budget.retry_count
            == 1
        )

    finally:
        await runtime.close()

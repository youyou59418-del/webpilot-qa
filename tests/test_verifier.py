from __future__ import annotations

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
from webpilot.verifier.rules import (
    RuleVerifier,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "day3_agent.html"
)


@pytest.mark.asyncio
async def test_url_contains_pass_and_fail() -> None:
    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

    try:
        await runtime.open_url(
            FIXTURE.as_uri()
        )

        engine = ObservationEngine()

        observation = await engine.observe(
            runtime
        )

        verifier = RuleVerifier()

        passed = verifier.verify(
            observation=observation,
            criteria=[
                SuccessCriterion(
                    rule="url_contains",
                    expected="day3_agent.html",
                )
            ],
        )

        assert passed.status == "PASS"

        failed = verifier.verify(
            observation=observation,
            criteria=[
                SuccessCriterion(
                    rule="url_contains",
                    expected="missing-page",
                )
            ],
        )

        assert failed.status == "FAIL"

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_visible_text_pass_and_fail() -> None:
    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

    try:
        await runtime.open_url(
            FIXTURE.as_uri()
        )

        engine = ObservationEngine()

        observation = await engine.observe(
            runtime
        )

        verifier = RuleVerifier()

        passed = verifier.verify(
            observation=observation,
            criteria=[
                SuccessCriterion(
                    rule="visible_text_contains",
                    expected="Product Search",
                )
            ],
        )

        assert passed.status == "PASS"

        premature_done = verifier.verify(
            observation=observation,
            criteria=[
                SuccessCriterion(
                    rule="visible_text_contains",
                    expected="Results for: laptop",
                )
            ],
        )

        assert (
            premature_done.status
            == "FAIL"
        )

        assert (
            premature_done
            .evidence[0]
            .passed
            is False
        )

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_element_text_equals_pass_and_fail() -> None:
    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

    try:
        await runtime.open_url(
            FIXTURE.as_uri()
        )

        engine = ObservationEngine()

        observation = await engine.observe(
            runtime
        )

        verifier = RuleVerifier()

        passed = verifier.verify(
            observation=observation,
            criteria=[
                SuccessCriterion(
                    rule="element_text_equals",
                    expected="Search",
                    element_role="button",
                    element_name="Search",
                )
            ],
        )

        assert passed.status == "PASS"

        failed = verifier.verify(
            observation=observation,
            criteria=[
                SuccessCriterion(
                    rule="element_text_equals",
                    expected="Submit",
                    element_role="button",
                    element_name="Search",
                )
            ],
        )

        assert failed.status == "FAIL"

    finally:
        await runtime.close()


def test_verifier_rejects_empty_criteria() -> None:
    from types import SimpleNamespace

    result = RuleVerifier().verify(
        observation=SimpleNamespace(
            url="https://example.test",
            visible_text="",
            elements=[],
        ),
        criteria=[],
    )

    assert result.status == "FAIL"
    assert result.failure_reason == "No success criteria were provided."

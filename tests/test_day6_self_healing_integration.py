from __future__ import annotations

from pathlib import Path

import pytest

from webpilot.agents.planner import (
    SuccessCriterion,
)
from webpilot.browser.locator import (
    SelfHealingAmbiguousError,
    SelfHealingLocator,
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


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "day6_self_healing.html"
)


async def find_element(
    observation,
    *,
    role: str,
    name: str,
):
    for element in (
        observation.elements
    ):
        if (
            element.role == role
            and element.name == name
        ):
            return element

    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "rename",
        "id",
        "structure",
        "combined",
    ],
)
async def test_self_healing_recovers_dom_drift(
    mode,
):
    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

    try:
        url = (
            FIXTURE.as_uri()
            + f"?mode={mode}"
        )

        await runtime.open_url(
            url
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

        # -----------------------------------------
        # Observe original DOM
        # -----------------------------------------

        observation = await engine.observe(
            runtime
        )

        login_element = await find_element(
            observation,
            role="button",
            name="Login",
        )

        assert login_element is not None

        # Save semantic signature BEFORE drift.
        old_signature = await healer.capture(
            engine=engine,
            element=login_element,
        )

        original_ref = (
            old_signature.ref
        )

        assert original_ref is not None

        # -----------------------------------------
        # Trigger DOM mutation
        # -----------------------------------------

        mutate_element = await find_element(
            observation,
            role="button",
            name="Mutate DOM",
        )

        assert mutate_element is not None

        await tools.execute(
            "click",
            {
                "ref": mutate_element.ref,
            },
        )

        # -----------------------------------------
        # MUST create a fresh observation.
        # Old refs are NOT trusted.
        # -----------------------------------------

        observation = await engine.observe(
            runtime
        )

        # -----------------------------------------
        # Self-Healing
        # -----------------------------------------

        healing = await healer.heal(
            engine=engine,
            observation=observation,
            target=old_signature,
        )

        assert healing.healed_ref

        assert (
            healing.score
            >= 0.55
        )

        # -----------------------------------------
        # Execute healed current ref
        # -----------------------------------------

        await tools.execute(
            "click",
            {
                "ref": healing.healed_ref,
            },
        )

        # -----------------------------------------
        # Healing only counts if Verifier PASS.
        # -----------------------------------------

        observation = await engine.observe(
            runtime
        )

        verification = RuleVerifier().verify(
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

        assert (
            verification.status
            == "PASS"
        )

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_ambiguous_healing_is_rejected():
    runtime = BrowserRuntime(
        headless=True
    )

    await runtime.start()

    try:
        url = (
            FIXTURE.as_uri()
            + "?mode=ambiguous"
        )

        await runtime.open_url(
            url
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

        login_element = await find_element(
            observation,
            role="button",
            name="Login",
        )

        assert login_element is not None

        signature = await healer.capture(
            engine=engine,
            element=login_element,
        )

        mutate_element = await find_element(
            observation,
            role="button",
            name="Mutate DOM",
        )

        assert mutate_element is not None

        await tools.execute(
            "click",
            {
                "ref": mutate_element.ref,
            },
        )

        observation = await engine.observe(
            runtime
        )

        with pytest.raises(
            SelfHealingAmbiguousError
        ):
            await healer.heal(
                engine=engine,
                observation=observation,
                target=signature,
            )

    finally:
        await runtime.close()

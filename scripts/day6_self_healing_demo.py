from __future__ import annotations

import asyncio
import json
from pathlib import Path

from webpilot.agents.planner import (
    SuccessCriterion,
)
from webpilot.browser.locator import (
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


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "day6_self_healing.html"
)


async def main():
    print(
        "========================================"
    )
    print(
        "WebPilot-QA Day 6"
    )
    print(
        "Self-Healing Locator Demo"
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
            + "?mode=combined"
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

        # =========================================
        # Original page
        # =========================================

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

        original_signature = (
            await healer.capture(
                engine=engine,
                element=login,
            )
        )

        print(
            "\nOriginal Element Signature:"
        )

        print(
            json.dumps(
                original_signature.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

        original_ref = (
            original_signature.ref
        )

        print(
            "\nOriginal ref:",
            original_ref,
        )

        # =========================================
        # Trigger combined DOM drift
        # =========================================

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

        print(
            "\nDOM drift injected:"
        )

        print(
            "- Login -> Sign in"
        )

        print(
            "- element id rebuilt"
        )

        print(
            "- DOM nesting changed"
        )

        print(
            "- element order changed"
        )

        print(
            "- data-testid removed"
        )

        # =========================================
        # Fresh Observation
        # =========================================

        observation = await engine.observe(
            runtime
        )

        print(
            "\nCurrent interactive elements:"
        )

        for element in (
            observation.elements
        ):
            print(
                f"[{element.ref}] "
                f"{element.role} "
                f"{element.name!r}"
            )

        # =========================================
        # Heal
        # =========================================

        healing = await healer.heal(
            engine=engine,
            observation=observation,
            target=original_signature,
        )

        print(
            "\nHealing Result:"
        )

        print(
            json.dumps(
                healing.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

        print(
            "\nOld ref was NOT reused:"
        )

        print(
            "old_ref=",
            original_ref,
        )

        print(
            "healed_ref=",
            healing.healed_ref,
        )

        # =========================================
        # Execute healed target
        # =========================================

        await tools.execute(
            "click",
            {
                "ref": healing.healed_ref,
            },
        )

        # =========================================
        # Mandatory Verify
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
                        expected="Authenticated",
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
                "Self-Healing candidate "
                "did not produce expected "
                "browser state."
            )

        print(
            "\n========================================"
        )

        print(
            "Day 6 Self-Healing Demo PASSED"
        )

        print(
            "========================================"
        )

    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())

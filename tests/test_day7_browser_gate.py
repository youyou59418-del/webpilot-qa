import pytest

from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import BrowserToolExecutor
from webpilot.safety.gate import ApprovalRequiredError, SafetyGate


@pytest.mark.asyncio
async def test_destructive_click_never_reaches_browser_before_approval() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    gate = SafetyGate()
    tools = BrowserToolExecutor(runtime, engine, safety_gate=gate)

    await runtime.start()
    try:
        await runtime.page.set_content(
            "<button onclick=\"document.body.dataset.deleted='yes'\">Delete account</button>"
        )
        observation = await engine.observe(runtime)
        ref = observation.elements[0].ref

        with pytest.raises(ApprovalRequiredError) as captured:
            await tools.execute("click", {"ref": ref})
        assert await runtime.page.evaluate("document.body.dataset.deleted || null") is None

        gate.approved_fingerprints.add(captured.value.approval.fingerprint)
        await tools.execute("click", {"ref": ref})
        assert await runtime.page.evaluate("document.body.dataset.deleted") == "yes"
    finally:
        await runtime.close()

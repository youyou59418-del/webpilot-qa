from pathlib import Path

import pytest

from webpilot.browser.observation import ObservationEngine
from webpilot.browser.runtime import BrowserRuntime
from webpilot.browser.tools import (
    BROWSER_TOOL_SCHEMAS,
    BrowserToolExecutor,
    ToolInputError,
)


@pytest.fixture
def fixture_url() -> str:
    return (
        Path("tests/fixtures/day3_agent.html")
        .resolve()
        .as_uri()
    )


@pytest.mark.asyncio
async def test_tools_execute_ref_based_search(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, engine)

    await runtime.start()
    try:
        await tools.execute("open_url", {"url": fixture_url})
        observation = await engine.observe(runtime)
        refs = {element.name: element.ref for element in observation.elements}

        await tools.execute(
            "fill",
            {"ref": refs["Search Products"], "value": "laptop"},
        )
        observation = await engine.observe(runtime)
        refs = {element.name: element.ref for element in observation.elements}
        await tools.execute("click", {"ref": refs["Search"]})

        state = await tools.execute("get_page_state", {})
        assert "Results for: laptop" in state["observation"]["visible_text"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_tools_reject_raw_selector_and_extra_arguments(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, engine)

    await runtime.start()
    try:
        await tools.execute("open_url", {"url": fixture_url})
        observation = await engine.observe(runtime)
        textbox_ref = next(
            element.ref
            for element in observation.elements
            if element.role == "textbox"
        )

        with pytest.raises(ToolInputError, match="Unexpected argument"):
            await tools.execute(
                "fill",
                {
                    "ref": textbox_ref,
                    "value": "laptop",
                    "selector": "#search-input",
                },
            )

        with pytest.raises(KeyError, match="Unknown element ref"):
            await tools.execute("click", {"ref": "#search-button"})
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_tools_enforce_role_and_url_contract(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, engine)

    await runtime.start()
    try:
        await tools.execute("open_url", {"url": fixture_url})
        observation = await engine.observe(runtime)
        button_ref = next(
            element.ref
            for element in observation.elements
            if element.role == "button"
        )

        with pytest.raises(ToolInputError, match="not a textbox"):
            await tools.execute(
                "fill",
                {"ref": button_ref, "value": "laptop"},
            )

        with pytest.raises(ToolInputError, match="only allows"):
            await tools.execute(
                "open_url",
                {"url": "javascript:alert(1)"},
            )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_get_page_state_rejects_arguments() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()
    tools = BrowserToolExecutor(runtime, engine)

    await runtime.start()
    try:
        with pytest.raises(ToolInputError, match="Unexpected argument"):
            await tools.execute("get_page_state", {"unused": "value"})
    finally:
        await runtime.close()


def test_browser_tool_schemas_are_strict() -> None:
    for schema in BROWSER_TOOL_SCHEMAS:
        parameters = schema["function"]["parameters"]
        assert parameters["type"] == "object"
        assert parameters["additionalProperties"] is False

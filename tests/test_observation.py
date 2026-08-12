from pathlib import Path

import pytest

from webpilot.browser.observation import (
    ObservationEngine,
)
from webpilot.browser.runtime import (
    BrowserRuntime,
)


@pytest.fixture
def fixture_url() -> str:
    return (
        Path(
            "tests/fixtures/"
            "day2_observation.html"
        )
        .resolve()
        .as_uri()
    )


@pytest.mark.asyncio
async def test_observation_has_page_metadata(
    fixture_url: str,
) -> None:

    runtime = BrowserRuntime()
    engine = ObservationEngine()

    try:
        await runtime.start()
        await runtime.open_url(
            fixture_url
        )

        observation = await engine.observe(
            runtime
        )

        assert (
            observation.title
            == "WebPilot Observation Test"
        )

        assert observation.url.startswith(
            "file://"
        )

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_observation_extracts_elements(
    fixture_url: str,
) -> None:

    runtime = BrowserRuntime()
    engine = ObservationEngine()

    try:
        await runtime.start()
        await runtime.open_url(
            fixture_url
        )

        observation = await engine.observe(
            runtime
        )

        names = {
            element.name
            for element
            in observation.elements
        }

        assert "Search Products" in names
        assert "Search" in names
        assert "Category" in names
        assert "View Products" in names
        assert "In Stock Only" in names

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_hidden_elements_are_filtered(
    fixture_url: str,
) -> None:

    runtime = BrowserRuntime()
    engine = ObservationEngine()

    try:
        await runtime.start()
        await runtime.open_url(
            fixture_url
        )

        observation = await engine.observe(
            runtime
        )

        names = {
            element.name
            for element
            in observation.elements
        }

        assert "Hidden Button" not in names

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_element_refs_are_unique(
    fixture_url: str,
) -> None:

    runtime = BrowserRuntime()
    engine = ObservationEngine()

    try:
        await runtime.start()
        await runtime.open_url(
            fixture_url
        )

        observation = await engine.observe(
            runtime
        )

        refs = [
            element.ref
            for element
            in observation.elements
        ]

        assert len(refs) == len(set(refs))

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_observation_serializable(
    fixture_url: str,
) -> None:

    runtime = BrowserRuntime()
    engine = ObservationEngine()

    try:
        await runtime.start()
        await runtime.open_url(
            fixture_url
        )

        observation = await engine.observe(
            runtime
        )

        payload = observation.model_dump()

        assert "url" in payload
        assert "title" in payload
        assert "elements" in payload

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_observation_limits_visible_interactive_elements() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine(max_elements=100)

    try:
        await runtime.start()

        hidden_buttons = "".join(
            '<button style="display: none">hidden</button>'
            for _ in range(100)
        )
        await runtime.page.set_content(
            hidden_buttons
            + '<button id="visible-action">Visible action</button>'
        )

        observation = await engine.observe(runtime)

        assert [
            element.name
            for element in observation.elements
        ] == ["Visible action"]

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_observation_excludes_noninteractive_roles() -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()

    try:
        await runtime.start()
        await runtime.page.set_content(
            '<div role="main">Main region</div>'
            '<button>Go</button>'
        )

        observation = await engine.observe(runtime)

        assert [
            (element.role, element.name)
            for element in observation.elements
        ] == [("button", "Go")]

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_ref_locator_performs_real_page_action(
    fixture_url: str,
) -> None:
    runtime = BrowserRuntime()
    engine = ObservationEngine()

    try:
        await runtime.start()
        await runtime.open_url(fixture_url)
        observation = await engine.observe(runtime)

        refs_by_name = {
            element.name: element.ref
            for element in observation.elements
        }

        await engine.locator_for(
            refs_by_name["Search Products"]
        ).fill("iPhone")
        await engine.locator_for(
            refs_by_name["Search"]
        ).click()

        assert await runtime.get_text(
            "#products"
        ) == "Results for: iPhone"

    finally:
        await runtime.close()

import asyncio
from pathlib import Path

from rich import print
from rich.console import Console
from rich.table import Table

from webpilot.browser.observation import (
    ObservationEngine,
)
from webpilot.browser.runtime import (
    BrowserRuntime,
)


async def main() -> None:
    runtime = BrowserRuntime()

    engine = ObservationEngine()

    fixture = (
        Path(
            "tests/fixtures/"
            "day2_observation.html"
        )
        .resolve()
        .as_uri()
    )

    try:
        await runtime.start()

        await runtime.open_url(
            fixture
        )

        observation = await engine.observe(
            runtime
        )

        print(
            "\n[bold]URL:[/bold]",
            observation.url,
        )

        print(
            "[bold]Title:[/bold]",
            observation.title,
        )

        table = Table(
            title="Interactive Elements"
        )

        table.add_column("Ref")
        table.add_column("Role")
        table.add_column("Name")
        table.add_column("Tag")

        for element in observation.elements:
            table.add_row(
                element.ref,
                element.role or "-",
                element.name or "-",
                element.tag,
            )

        Console().print(table)

        print(
            "\n[bold]Visible Text:[/bold]"
        )

        print(
            observation.visible_text
        )

        print(
            "\nObservation demo PASSED"
        )

    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
from pathlib import Path

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
        # -------------------------
        # 1. 启动浏览器
        # -------------------------
        await runtime.start()

        await runtime.open_url(
            fixture
        )


        # -------------------------
        # 2. 获取结构化 Observation
        # -------------------------
        observation = (
            await engine.observe(
                runtime
            )
        )


        # -------------------------
        # 3. 输出实际识别结果
        # -------------------------
        print(
            "\n===== "
            "Browser Observation "
            "====="
        )

        for element in (
            observation.elements
        ):
            print(
                f"{element.ref}: "
                f"role="
                f"{element.role!r}, "
                f"name="
                f"{element.name!r}, "
                f"placeholder="
                f"{element.placeholder!r}"
            )


        # -------------------------
        # 4. 找搜索框和搜索按钮
        # -------------------------
        search_input_ref = None
        search_button_ref = None

        for element in (
            observation.elements
        ):

            # 输入框：
            # Role + Name/Placeholder
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
                search_input_ref = (
                    element.ref
                )


            # 搜索按钮：
            # Role + Accessible Name
            if (
                element.role
                == "button"
                and
                element.name
                == "Search"
            ):
                search_button_ref = (
                    element.ref
                )


        # -------------------------
        # 5. 明确检查查找结果
        # -------------------------
        if (
            search_input_ref
            is None
        ):
            raise RuntimeError(
                "Search input was "
                "not found in "
                "BrowserObservation."
            )

        if (
            search_button_ref
            is None
        ):
            raise RuntimeError(
                "Search button was "
                "not found in "
                "BrowserObservation."
            )


        print(
            "\nResolved refs:"
        )

        print(
            "Search input:",
            search_input_ref,
        )

        print(
            "Search button:",
            search_button_ref,
        )


        # -------------------------
        # 6. Ref -> Locator
        # -------------------------
        search_input = (
            engine.locator_for(
                search_input_ref
            )
        )

        search_button = (
            engine.locator_for(
                search_button_ref
            )
        )


        # -------------------------
        # 7. 使用 Ref 对真实网页操作
        # -------------------------
        await search_input.fill(
            "iPhone"
        )

        await search_button.click()


        # -------------------------
        # 8. 检查真实页面结果
        # -------------------------
        result = (
            await runtime.get_text(
                "#products"
            )
        )

        print(
            "\nResult:",
            result,
        )


        if (
            result
            != "Results for: iPhone"
        ):
            raise RuntimeError(
                "Unexpected page "
                f"result: {result!r}"
            )


        # -------------------------
        # 9. 截图保存证据
        # -------------------------
        screenshot_path = (
            await runtime.screenshot(
                "artifacts/day2/"
                "ref-action-demo.png"
            )
        )

        print(
            "Screenshot:",
            screenshot_path,
        )


        print(
            "\n"
            "Element ref action "
            "PASSED"
        )


    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())

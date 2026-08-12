from __future__ import annotations

from playwright.async_api import Locator
from pydantic import BaseModel, Field

from webpilot.browser.runtime import BrowserRuntime


class InteractiveElement(BaseModel):
    ref: str

    tag: str
    role: str | None = None
    name: str | None = None

    text: str | None = None
    placeholder: str | None = None
    element_type: str | None = None

    enabled: bool = True
    visible: bool = True


class BrowserObservation(BaseModel):
    url: str
    title: str

    elements: list[InteractiveElement] = Field(
        default_factory=list
    )

    visible_text: str = ""

    aria_snapshot: str | None = None


class ObservationEngine:
    """
    将真实网页转换为适合 Browser Agent 使用的
    结构化 BrowserObservation。

    Day 2 核心职责：
    1. 提取可交互元素
    2. 过滤不可见元素
    3. 推导基础 ARIA Role
    4. 提取并规范化元素语义名称
    5. 为元素生成 e1/e2/e3... 引用
    6. 保存 ref -> Playwright Locator 映射
    """

    INTERACTIVE_SELECTOR = """
        a,
        button,
        input,
        textarea,
        select,
        [role="button"],
        [role="link"],
        [role="textbox"],
        [role="combobox"],
        [role="checkbox"],
        [role="radio"],
        [role="switch"],
        [role="tab"],
        [role="menuitem"],
        [role="option"],
        [role="slider"],
        [role="spinbutton"],
        [role="listbox"],
        [role="treeitem"],
        [contenteditable="true"],
        [tabindex]:not([tabindex="-1"])
    """

    def __init__(
        self,
        *,
        max_elements: int = 100,
        max_visible_text_chars: int = 4000,
    ) -> None:
        self.max_elements = max_elements
        self.max_visible_text_chars = (
            max_visible_text_chars
        )

        self._ref_locators: dict[
            str,
            Locator,
        ] = {}

    async def observe(
        self,
        runtime: BrowserRuntime,
    ) -> BrowserObservation:

        page = runtime.page

        # 每次重新观察页面，都重新生成 Ref。
        self._ref_locators = {}

        candidates = page.locator(
            self.INTERACTIVE_SELECTOR
        )

        count = await candidates.count()

        elements: list[
            InteractiveElement
        ] = []

        for index in range(count):
            if len(elements) >= self.max_elements:
                break

            locator = candidates.nth(index)

            # 过滤隐藏元素。
            try:
                visible = (
                    await locator.is_visible()
                )
            except Exception:
                continue

            if not visible:
                continue

            # 在浏览器侧提取元素语义信息。
            data = await locator.evaluate(
                """
                (el) => {

                    // -------------------------
                    // 统一文本格式
                    // -------------------------
                    const clean = (value) => {
                        if (
                            value === null ||
                            value === undefined
                        ) {
                            return null;
                        }

                        const normalized =
                            String(value)
                                .replace(
                                    /\\s+/g,
                                    " "
                                )
                                .trim();

                        return (
                            normalized.length > 0
                                ? normalized
                                : null
                        );
                    };


                    // -------------------------
                    // Tag
                    // -------------------------
                    const tag =
                        el.tagName
                            .toLowerCase();


                    // -------------------------
                    // Role
                    // -------------------------
                    let role = clean(
                        el.getAttribute(
                            "role"
                        )
                    );

                    const type = clean(
                        el.getAttribute(
                            "type"
                        )
                    );

                    if (!role) {

                        if (tag === "button") {
                            role = "button";
                        }

                        else if (tag === "a") {
                            role = "link";
                        }

                        else if (
                            tag === "textarea"
                        ) {
                            role = "textbox";
                        }

                        else if (
                            tag === "select"
                        ) {
                            role = "combobox";
                        }

                        else if (
                            tag === "input"
                        ) {

                            if (
                                type === "checkbox"
                            ) {
                                role =
                                    "checkbox";
                            }

                            else if (
                                type === "radio"
                            ) {
                                role =
                                    "radio";
                            }

                            else if (
                                type === "button" ||
                                type === "submit" ||
                                type === "reset"
                            ) {
                                role =
                                    "button";
                            }

                            else {
                                role =
                                    "textbox";
                            }
                        }
                    }


                    // -------------------------
                    // Label
                    // -------------------------
                    let label = null;

                    if (
                        el.labels &&
                        el.labels.length > 0
                    ) {
                        label = clean(
                            el.labels[0]
                                .innerText
                        );
                    }


                    // -------------------------
                    // 其他语义信息
                    // -------------------------
                    const text = clean(
                        el.innerText
                    );

                    const ariaLabel = clean(
                        el.getAttribute(
                            "aria-label"
                        )
                    );

                    const placeholder = clean(
                        el.getAttribute(
                            "placeholder"
                        )
                    );

                    const title = clean(
                        el.getAttribute(
                            "title"
                        )
                    );

                    const alt = clean(
                        el.getAttribute(
                            "alt"
                        )
                    );

                    const value = clean(
                        el.getAttribute(
                            "value"
                        )
                    );

                    const tabindex =
                        el.getAttribute(
                            "tabindex"
                        );

                    const nativeInteractive =
                        tag === "button" ||
                        tag === "input" ||
                        tag === "textarea" ||
                        tag === "select" ||
                        (
                            tag === "a" &&
                            el.hasAttribute("href")
                        ) ||
                        el.isContentEditable;

                    const interactiveRoles = [
                        "button",
                        "link",
                        "textbox",
                        "combobox",
                        "checkbox",
                        "radio",
                        "switch",
                        "tab",
                        "menuitem",
                        "option",
                        "slider",
                        "spinbutton",
                        "listbox",
                        "treeitem"
                    ];

                    const isFocusable =
                        tabindex !== null &&
                        Number(tabindex) >= 0;

                    const interactive =
                        nativeInteractive ||
                        interactiveRoles.includes(role) ||
                        isFocusable;


                    // -------------------------
                    // Name 优先级
                    // -------------------------
                    const name =
                        ariaLabel ||
                        label ||
                        text ||
                        placeholder ||
                        alt ||
                        title ||
                        value ||
                        null;


                    return {
                        tag: tag,
                        role: role,
                        name: name,
                        text: text,
                        placeholder:
                            placeholder,
                        type: type,
                        interactive: interactive,
                        disabled:
                            Boolean(
                                el.disabled
                            )
                    };
                }
                """
            )

            if not data["interactive"]:
                continue

            # 只给真正可见、可操作元素编号。
            ref = (
                f"e{len(elements) + 1}"
            )

            self._ref_locators[
                ref
            ] = locator

            elements.append(
                InteractiveElement(
                    ref=ref,
                    tag=data["tag"],
                    role=data["role"],
                    name=data["name"],
                    text=data["text"],
                    placeholder=(
                        data[
                            "placeholder"
                        ]
                    ),
                    element_type=(
                        data["type"]
                    ),
                    enabled=not data[
                        "disabled"
                    ],
                    visible=True,
                )
            )


        # -------------------------
        # 页面可见文本
        # -------------------------
        visible_text = ""

        try:
            visible_text = (
                await page
                .locator("body")
                .inner_text()
            )

            # 同样做一次文本规范化。
            visible_text = " ".join(
                visible_text.split()
            )

            visible_text = (
                visible_text[
                    :
                    self
                    .max_visible_text_chars
                ]
            )

        except Exception:
            visible_text = ""


        # -------------------------
        # ARIA Snapshot
        # -------------------------
        aria_snapshot = None

        try:
            aria_snapshot = (
                await page
                .aria_snapshot()
            )

        except Exception:
            # ARIA Snapshot 是辅助信息，
            # 即使当前浏览器版本不支持，
            # 也不影响主 Observation。
            aria_snapshot = None


        return BrowserObservation(
            url=page.url,
            title=await page.title(),
            elements=elements,
            visible_text=visible_text,
            aria_snapshot=aria_snapshot,
        )


    def locator_for(
        self,
        ref: str,
    ) -> Locator:
        """
        将 Agent 世界中的 e1/e2/e3
        转换回真实 Playwright Locator。
        """

        locator = (
            self._ref_locators
            .get(ref)
        )

        if locator is None:
            raise KeyError(
                f"Unknown element ref: "
                f"{ref}"
            )

        return locator

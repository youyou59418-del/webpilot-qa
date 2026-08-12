from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from webpilot.browser.observation import (
    BrowserObservation,
    InteractiveElement,
    ObservationEngine,
)
from webpilot.browser.runtime import BrowserRuntime


BROWSER_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open an absolute http, https, or file URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The absolute URL to open.",
                    }
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": (
                "Click a visible, enabled interactive element using a ref from "
                "the current observation, for example e1."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "Element ref from the current observation.",
                    }
                },
                "required": ["ref"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill",
            "description": (
                "Fill a visible, enabled textbox using a ref from the current "
                "observation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "Textbox ref from the current observation.",
                    },
                    "value": {
                        "type": "string",
                        "description": "Text to enter.",
                    },
                },
                "required": ["ref", "value"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_state",
            "description": "Read a fresh structured browser observation.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]

ALLOWED_BROWSER_TOOLS = frozenset(
    {
        "open_url",
        "click",
        "fill",
        "get_page_state",
    }
)

CLICKABLE_ROLES = frozenset(
    {
        "button",
        "link",
        "checkbox",
        "radio",
        "switch",
        "tab",
        "menuitem",
        "option",
        "treeitem",
    }
)


class ToolInputError(ValueError):
    """Raised when an LLM request is outside the Day 3 browser-tool contract."""


def observation_to_dict(
    observation: BrowserObservation,
) -> dict[str, Any]:
    return observation.model_dump()


class BrowserToolExecutor:
    """The allowlisted boundary between an LLM action and Playwright.

    The model can only name a fixed tool and pass primitive JSON arguments. It
    never receives a CSS selector, XPath, JavaScript, or shell capability.
    Element refs are resolved against the most recent ObservationEngine state.
    """

    def __init__(
        self,
        runtime: BrowserRuntime,
        observation_engine: ObservationEngine,
    ) -> None:
        self.runtime = runtime
        self.observation_engine = observation_engine

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name not in ALLOWED_BROWSER_TOOLS:
            raise ToolInputError(
                f"Browser tool is not allowed: {tool_name}"
            )
        if not isinstance(arguments, dict):
            raise ToolInputError("Browser tool arguments must be an object.")

        if tool_name == "open_url":
            return await self._open_url(arguments)
        if tool_name == "click":
            return await self._click(arguments)
        if tool_name == "fill":
            return await self._fill(arguments)
        if tool_name == "get_page_state":
            return await self._get_page_state(arguments)

        raise AssertionError(f"Unhandled allowed tool: {tool_name}")

    async def _open_url(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_exact_keys(arguments, required={"url"})
        url = self._required_string(arguments, "url")
        self._validate_url(url)

        await self.runtime.open_url(url)
        return {
            "ok": True,
            "tool": "open_url",
            "url": await self.runtime.current_url(),
        }

    async def _click(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_exact_keys(arguments, required={"ref"})
        ref = self._required_string(arguments, "ref")
        element = self._actionable_element(ref)

        if element.role not in CLICKABLE_ROLES:
            raise ToolInputError(
                f"Element ref {ref} is not clickable: role={element.role!r}"
            )

        await self.runtime.click(
            self.observation_engine.locator_for(ref)
        )
        return {
            "ok": True,
            "tool": "click",
            "ref": ref,
        }

    async def _fill(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_exact_keys(
            arguments,
            required={"ref", "value"},
        )
        ref = self._required_string(arguments, "ref")
        value = self._required_string(arguments, "value")
        element = self._actionable_element(ref)

        if element.role != "textbox":
            raise ToolInputError(
                f"Element ref {ref} is not a textbox: role={element.role!r}"
            )

        await self.runtime.fill(
            self.observation_engine.locator_for(ref),
            value,
        )
        return {
            "ok": True,
            "tool": "fill",
            "ref": ref,
        }

    async def _get_page_state(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_exact_keys(arguments, required=set())
        observation = await self.observation_engine.observe(self.runtime)
        return {
            "ok": True,
            "tool": "get_page_state",
            "observation": observation_to_dict(observation),
        }

    def _actionable_element(self, ref: str) -> InteractiveElement:
        element = self.observation_engine.element_for(ref)
        if not element.visible:
            raise ToolInputError(f"Element ref {ref} is not visible.")
        if not element.enabled:
            raise ToolInputError(f"Element ref {ref} is disabled.")
        return element

    @staticmethod
    def _require_exact_keys(
        arguments: dict[str, Any],
        *,
        required: set[str],
    ) -> None:
        keys = set(arguments)
        missing = required - keys
        unexpected = keys - required
        if missing:
            raise ToolInputError(
                "Missing required argument(s): " + ", ".join(sorted(missing))
            )
        if unexpected:
            raise ToolInputError(
                "Unexpected argument(s): " + ", ".join(sorted(unexpected))
            )

    @staticmethod
    def _required_string(
        arguments: dict[str, Any],
        key: str,
    ) -> str:
        value = arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ToolInputError(
                f"Missing or invalid string argument: {key}"
            )
        return value.strip()

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https", "file"}:
            raise ToolInputError(
                "open_url only allows http, https, or file URLs."
            )
        if parsed.scheme in {"http", "https"} and not parsed.netloc:
            raise ToolInputError("HTTP URLs must include a host.")
        if parsed.scheme == "file" and not parsed.path:
            raise ToolInputError("file URLs must include an absolute path.")

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from webpilot.browser.observation import BrowserObservation
from webpilot.browser.tools import (
    ALLOWED_BROWSER_TOOLS,
    BROWSER_TOOL_SCHEMAS,
)
from webpilot.llm.adapter import ChatModel


@dataclass(frozen=True)
class ActorDecision:
    kind: Literal["tool", "done"]
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    message: str = ""


def format_observation(observation: BrowserObservation) -> str:
    lines = [
        f"URL: {observation.url}",
        f"Title: {observation.title}",
        "",
        "Interactive Elements:",
    ]
    if not observation.elements:
        lines.append("(none)")
    else:
        for element in observation.elements:
            name = (
                element.name
                or element.text
                or element.placeholder
                or ""
            )
            details: list[str] = []
            if element.placeholder:
                details.append(f'placeholder="{element.placeholder}"')
            if element.value is not None:
                details.append(f'value="{element.value}"')
            if element.checked is not None:
                details.append(f"checked={str(element.checked).lower()}")
            if not element.enabled:
                details.append("disabled")
            suffix = f" [{', '.join(details)}]" if details else ""
            lines.append(
                f'[{element.ref}] {element.role or element.tag} "{name}"{suffix}'
            )
    lines.extend(
        [
            "",
            "Visible Text:",
            observation.visible_text or "(empty)",
        ]
    )
    return "\n".join(lines)


class BrowserActor:
    """One-action-at-a-time decision layer for the Day 3 baseline."""

    def __init__(self, llm: ChatModel) -> None:
        self.llm = llm

    async def decide(
        self,
        *,
        goal: str,
        observation: BrowserObservation,
        history: list[dict[str, Any]],
        target_url: str,
        require_action: bool = False,
    ) -> ActorDecision:
        system_prompt = """
You are the Actor of WebPilot-QA, a browser testing agent.

Choose exactly one next action. Use only the supplied browser tools. For
click/fill/select_option, use only refs from the CURRENT observation. Never emit CSS
selectors, XPath, JavaScript, shell commands, or invented refs. Refs expire
after every action because the page is observed again.

When the supplied target URL has not been opened, call open_url with that exact
URL. Prefer the smallest action that makes progress. If the goal is fully
achieved based on the current page state, call no tool and reply exactly:

DONE: <short evidence-based reason>

Do not claim DONE without page-state evidence.
        """.strip()

        if require_action:
            system_prompt += (
                "\n\nThis plan step requires a real browser state change. "
                "You must make at least one browser tool call before DONE; "
                "static labels or option names already visible on the page "
                "are not evidence that an action was completed."
            )

        user_prompt = f"""
GOAL:
{goal}

TARGET URL:
{target_url}

CURRENT OBSERVATION:
{format_observation(observation)}

RECENT ACTION HISTORY:
{json.dumps(history[-5:], ensure_ascii=False, indent=2)}

Choose the next single action.
        """.strip()

        reply = await self.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=BROWSER_TOOL_SCHEMAS,
        )

        if reply.tool_call is not None:
            tool_name = reply.tool_call.name
            if tool_name not in ALLOWED_BROWSER_TOOLS:
                raise RuntimeError(
                    f"Actor returned forbidden browser tool: {tool_name}"
                )
            return ActorDecision(
                kind="tool",
                tool_name=tool_name,
                arguments=reply.tool_call.arguments,
                message=reply.content,
            )

        content = reply.content.strip()
        if content.startswith("DONE:"):
            return ActorDecision(kind="done", message=content)
        raise RuntimeError(
            "Actor returned neither a structured browser tool call nor a valid "
            f"DONE response. Raw content: {content!r}"
        )

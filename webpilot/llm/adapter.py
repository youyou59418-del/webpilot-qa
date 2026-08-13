from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class LLMToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMReply:
    content: str
    tool_call: LLMToolCall | None = None


class ChatModel(Protocol):
    """The narrow model contract consumed by the Day 3 Actor."""

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply: ...


class OpenAICompatibleLLM:
    """Minimal OpenAI-compatible Chat Completions adapter.

    Provider configuration lives only here. The BrowserActor depends on the
    ChatModel protocol, so the agent loop can be exercised with a controlled
    fake in tests without coupling production code to a vendor SDK.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLM":
        base_url = os.environ.get("LLM_BASE_URL", "").strip()
        api_key = os.environ.get("LLM_API_KEY", "").strip()
        model = os.environ.get("LLM_MODEL", "").strip()
        raw_timeout = os.environ.get("LLM_TIMEOUT_S", "60").strip()

        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL", base_url),
                ("LLM_API_KEY", api_key),
                ("LLM_MODEL", model),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing LLM environment variables: " + ", ".join(missing)
            )

        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise RuntimeError(
                "LLM_BASE_URL must be an absolute http(s) URL, for example "
                "https://provider.example/v1"
            )

        try:
            timeout_s = int(raw_timeout)
        except ValueError as exc:
            raise RuntimeError("LLM_TIMEOUT_S must be a positive integer.") from exc
        if timeout_s <= 0:
            raise RuntimeError("LLM_TIMEOUT_S must be a positive integer.")

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_s=timeout_s,
        )

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMReply:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "temperature": 0,
        }
        response = await asyncio.to_thread(self._post_json, payload)

        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "Unexpected LLM response format: missing choices[0].message"
            ) from exc

        content = message.get("content") or ""
        if not isinstance(content, str):
            raise RuntimeError("LLM message content must be a string or null.")

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return LLMReply(content=content)
        if not isinstance(tool_calls, list) or len(tool_calls) != 1:
            count = len(tool_calls) if isinstance(tool_calls, list) else "non-list"
            raise RuntimeError(
                "Day 3 only supports exactly one browser tool call per step. "
                f"Received {count}."
            )

        call = tool_calls[0]
        try:
            function = call["function"]
            name = function["name"]
            raw_arguments = function.get("arguments", "{}")
            if not isinstance(name, str) or not name:
                raise TypeError("function.name must be a non-empty string")
            if isinstance(raw_arguments, str):
                arguments = json.loads(raw_arguments)
            elif isinstance(raw_arguments, dict):
                arguments = raw_arguments
            else:
                raise TypeError("function.arguments must be an object or JSON string")
            if not isinstance(arguments, dict):
                raise TypeError("function.arguments must decode to an object")
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Invalid tool call returned by LLM.") from exc

        return LLMReply(
            content=content,
            tool_call=LLMToolCall(name=name, arguments=arguments),
        )

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_s,
            ) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LLM HTTP error {exc.code}: {body[:1000]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Unable to reach LLM API: {exc}") from exc

        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"LLM returned non-JSON response: {body[:1000]}"
            ) from exc
        if not isinstance(result, dict):
            raise RuntimeError("Unexpected LLM response: root must be an object.")
        return result

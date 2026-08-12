from typing import Any

import pytest

from webpilot.llm.adapter import OpenAICompatibleLLM


class StubOpenAICompatibleLLM(OpenAICompatibleLLM):
    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__(
            base_url="https://provider.example/v1",
            api_key="test-key",
            model="test-model",
        )
        self.response = response
        self.payload: dict[str, Any] | None = None

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payload = payload
        return self.response


@pytest.mark.asyncio
async def test_adapter_parses_one_json_tool_call() -> None:
    llm = StubOpenAICompatibleLLM(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "click",
                                    "arguments": '{"ref": "e2"}',
                                }
                            }
                        ],
                    }
                }
            ]
        }
    )

    reply = await llm.chat(messages=[{"role": "user", "content": "go"}], tools=[])

    assert reply.tool_call is not None
    assert reply.tool_call.name == "click"
    assert reply.tool_call.arguments == {"ref": "e2"}
    assert llm.payload is not None
    assert llm.payload["model"] == "test-model"
    assert llm.payload["temperature"] == 0


@pytest.mark.asyncio
async def test_adapter_rejects_non_object_tool_arguments() -> None:
    llm = StubOpenAICompatibleLLM(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "click",
                                    "arguments": "[]",
                                }
                            }
                        ],
                    }
                }
            ]
        }
    )

    with pytest.raises(RuntimeError, match="Invalid tool call"):
        await llm.chat(messages=[], tools=[])


@pytest.mark.asyncio
async def test_adapter_rejects_multiple_tool_calls() -> None:
    llm = StubOpenAICompatibleLLM(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "click", "arguments": "{}"}},
                            {"function": {"name": "fill", "arguments": "{}"}},
                        ]
                    }
                }
            ]
        }
    )

    with pytest.raises(RuntimeError, match="exactly one"):
        await llm.chat(messages=[], tools=[])


def test_adapter_env_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TIMEOUT_S"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
        OpenAICompatibleLLM.from_env()

    monkeypatch.setenv("LLM_BASE_URL", "not-a-url")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "model")
    with pytest.raises(RuntimeError, match="absolute http"):
        OpenAICompatibleLLM.from_env()

    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_TIMEOUT_S", "0")
    with pytest.raises(RuntimeError, match="positive"):
        OpenAICompatibleLLM.from_env()

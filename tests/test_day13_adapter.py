import json

from webpilot.llm.adapter import OpenAICompatibleLLM


def test_adapter_disables_parallel_tool_calls(monkeypatch) -> None:
    adapter = OpenAICompatibleLLM("http://127.0.0.1:8001/v1", "local", "Qwen/Qwen2.5-7B-Instruct")
    observed: dict[str, object] = {}

    def capture(payload):
        observed.update(payload)
        return {"choices": [{"message": {"content": "done"}}]}

    monkeypatch.setattr(adapter, "_post_json", capture)
    import asyncio
    asyncio.run(adapter.chat(messages=[{"role": "user", "content": "hi"}], tools=[]))
    assert observed["parallel_tool_calls"] is False

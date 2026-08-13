from __future__ import annotations

import argparse
import json
import urllib.request


def request(url: str, payload: dict[str, object] | None, api_key: str) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    assert isinstance(data, dict)
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--api-key", default="local-webpilot-only")
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    models = request(f"{base}/models", None, args.api_key)
    reply = request(f"{base}/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "Reply with exactly: WebPilot local model ready"}],
        "temperature": 0,
        "max_tokens": 32,
    }, args.api_key)
    tool_reply = request(f"{base}/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "Use the ping function exactly once with message WebPilot."}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "ping",
                "description": "Return a diagnostic message.",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
        }],
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "temperature": 0,
        "max_tokens": 64,
    }, args.api_key)
    choices = tool_reply.get("choices")
    assert isinstance(choices, list) and choices, "tool-call response has no choices"
    message = choices[0].get("message")
    assert isinstance(message, dict), "tool-call response has no message"
    tool_calls = message.get("tool_calls")
    assert isinstance(tool_calls, list) and tool_calls, "model did not return a tool call"
    function = tool_calls[0].get("function")
    assert isinstance(function, dict) and function.get("name") == "ping", "unexpected tool call"
    print(json.dumps({"models": models, "sample_reply": reply, "tool_reply": tool_reply}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

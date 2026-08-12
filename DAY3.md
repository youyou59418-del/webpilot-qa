# Day 3: Single Browser Agent

Day 3 adds the smallest model-driven browser loop:

```text
Observe -> Actor -> one allowlisted tool call -> Observe
```

It intentionally does **not** add a Planner, Verifier, retry/recovery policy,
LangGraph, local vLLM, or service layer. Those begin after this baseline is
recorded.

## Safety boundary

The Actor can only call `open_url`, `click(ref)`, `fill(ref, value)`, and
`get_page_state()`. It never receives a raw CSS selector, XPath, JavaScript,
or shell execution capability. `open_url` accepts only `http`, `https`, and
local `file` URLs. Element refs are valid only for the latest observation.

## External API configuration

Use an OpenAI-compatible Chat Completions endpoint. Do not put a secret in Git
or in a command history. Configure the values in the current shell or a
machine-local secret manager:

```bash
export LLM_BASE_URL='https://your-provider.example/v1'
export LLM_API_KEY='your-secret-key'
export LLM_MODEL='your-model-id'
export LLM_TIMEOUT_S='60'
```

`LLM_BASE_URL` must include the provider's API version prefix when required;
the adapter appends `/chat/completions`.

## One-task API run

From the repository root:

```bash
.venv/bin/python scripts/run_agent.py \
  --goal 'Search for laptop and stop only when the page says Results for: laptop.' \
  --start-url "file://$(pwd)/tests/fixtures/day3_agent.html" \
  --max-steps 6
```

The command prints a structured run result. `completed` means the Actor issued
an evidence-based `DONE`; Day 4 will add an independent Verifier, so do not
treat the Actor's own statement as final production-grade verification.

## Fixed local baseline

The task catalog contains 20 repeatable search tasks. With the same model,
prompt, browser version, and step budget, run:

```bash
.venv/bin/python scripts/run_day3_baseline.py
```

It writes `artifacts/day3/baseline.json` and reports Task Success Rate,
Average Steps, Average Tool Calls, and Average Duration. A task counts as
successful only when the Actor returns `DONE` **and** the fixture's expected
page text is present. This final fixture assertion is benchmark bookkeeping,
not the Day 4 Verifier module.

## Offline contract checks

These do not use an external API or evaluate model quality:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/day3_tool_demo.py
.venv/bin/python scripts/day3_agent_demo.py
```

The agent demo deliberately uses a controlled test double to prove that the
loop, ref lifecycle, tool boundary, result logging, and max-step guard work in
a deterministic environment.

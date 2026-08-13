# WebPilot-QA

WebPilot-QA is a verifiable browser-testing agent: it turns a natural-language testing goal into a structured plan, uses restricted Playwright tools against a current semantic observation, independently verifies page state, performs bounded recovery and self-healing, and stores redacted evidence.

## What is implemented

- Browser runtime, structured observation, strict tool boundary and OpenAI-compatible model adapter.
- Planner, rule verifier, bounded recovery and self-healing locator.
- Risk-aware action gate with semantic approval fingerprints.
- FastAPI run control plane, durable single-worker queue, SSE, screenshots, traces and redacted artifacts.
- Next.js console and 100-task controlled ShopBench v1.
- Evaluation/reporting framework and verified-trajectory to Playwright regression generation.
- A separate vLLM/Qwen local-model environment for controlled model comparison.

See [architecture](docs/ARCHITECTURE.md), [demo](docs/DEMO.md), [verified run status](docs/RUN_STATUS.md), and [interview evidence rules](docs/INTERVIEW.md).

## Quick start

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python scripts/run_shopbench.py --port 8080
./.venv/bin/python -m uvicorn webpilot.service.api:create_app --host 127.0.0.1 --port 8000
./scripts/bootstrap_console.sh
PATH="$PWD/.tools/node/bin:$PATH" ./.tools/node/bin/npm --prefix console run dev
```

Browse ShopBench at `http://127.0.0.1:8080/?reset=1` and the console at `http://127.0.0.1:3000`. Before issuing a real browser run, set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`, or source the local profile after Day 13.

## Reproducible evaluation

Every ShopBench task starts from `/?reset=1`. Run the same task IDs, model identifier, budgets and retry policy for every variant. The evaluation runner writes JSON, CSV and Markdown results under `artifacts/evaluation/`; only `live_model` reports are valid performance evidence.

`scripts/summarize_day11_ablations.py` combines equal-budget `live_model` reports into a CSV, Markdown table, JSON and SVG chart. A local model being reachable is an integration result, not a performance result.

## Safety boundary

The agent cannot execute arbitrary JavaScript, CSS selectors or shell commands. Destructive/external action names and sensitive form fields require approval. Use the controlled benchmark for evidence; real websites are optional demonstrations only.

# WebPilot-QA Environment Baseline

## Verified AutoDL snapshot

Last revalidated on 2026-08-12. Re-run the checks below after replacing the
AutoDL instance; do not treat an older plan as the live machine configuration.

- Platform: AutoDL
- Project root: `/root/autodl-tmp/webpilot-qa`
- GPU: NVIDIA GeForce RTX 4090, 24,564 MiB visible memory
- CPU: 128 logical CPUs
- Memory: 755 GiB total
- Project data disk: `/root/autodl-tmp`, 100 GiB XFS volume
- NVIDIA Driver: 580.142
- `nvidia-smi` CUDA capability: 13.0

## Python and CUDA

- Base Python: 3.12.3 at `/root/miniconda3/bin/python`
- Base PyTorch: 2.5.1+cu124
- PyTorch CUDA Runtime: 12.4
- `torch.cuda.is_available()`: `True`
- WebPilot virtual environment: `.venv`, Python 3.12.3

The Day 1-Day 3 browser work does not depend on PyTorch or CUDA. Build a
separate environment for vLLM later; do not install vLLM into `.venv`.

## Playwright browser cache

Playwright 1.62.0 Chromium is installed on the data disk at
`/root/autodl-tmp/cache/playwright`. `BrowserRuntime` and the Smoke Test
automatically discover this cache in a fresh shell. An explicit
`PLAYWRIGHT_BROWSERS_PATH` takes precedence, and
`WEBPILOT_PLAYWRIGHT_BROWSERS_PATH` provides a project-specific override.

For a clean cache installation:

```bash
export PLAYWRIGHT_BROWSERS_PATH=/root/autodl-tmp/cache/playwright
.venv/bin/python -m playwright install chromium
```

## Day 1-Day 2 acceptance commands

Run these commands from the project root without manually exporting a browser
cache path:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/browser_runtime_demo.py
.venv/bin/python scripts/observation_demo.py
.venv/bin/python scripts/ref_action_demo.py
.venv/bin/python scripts/playwright_smoke_test.py
```

Expected result: the test suite passes; the Day 1 local interaction and
external Smoke Test pass; Day 2 filters hidden/noninteractive candidates and
performs a ref-to-locator action on the fixture.

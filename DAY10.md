# Day 10 - ShopBench v1

## Delivered

`shopbench/` is a local, controlled shopping test station with 100 fixed tasks: 30 Easy, 40 Medium, and 30 Hard. It exposes a catalog API at `/api/tasks` and a deterministic browser page at `/?reset=1`.

The station covers Login, Search, Filter, Cart, Forms, Tables, Pagination, Dialog, Tabs, Dynamic DOM, Toast, Loading, and Error State. Every task has an ID, start path, natural-language goal, expected state, risk level, and covered modules. The checkout dialog is only a local state change; it never contacts a payment provider.

## Run and verify

```bash
./.venv/bin/python scripts/run_shopbench.py --host 127.0.0.1 --port 8080
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/tasks
./.venv/bin/python -m pytest -q tests/test_shopbench.py tests/test_shopbench_browser.py
```

For agent evaluation, create a new BrowserContext and open `http://127.0.0.1:8080/?reset=1` for every task. This guarantees an independent, repeated initial state before Day 11 evaluation.

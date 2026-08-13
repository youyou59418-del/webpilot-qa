# Day 9 - Next.js Web Console

## Delivered

`console/` is a standalone Next.js console that only renders the WebPilot API's durable run state. It creates a run, consumes the SSE event stream, and shows the saved plan, verifier evidence, action/recovery trace, current screenshot, Playwright trace, artifacts, duration, tool-call count, and retry count.

The backend adds a read-only `GET /runs/{run_id}/console` projection and safe individual artifact downloads. Response payloads are redacted before reaching the browser. CORS is limited by `WEBPILOT_CORS_ORIGINS` (localhost ports 3000 by default).

## Run

```bash
./scripts/bootstrap_console.sh
./.tools/node/bin/npm --prefix console run dev
# Browse http://127.0.0.1:3000 after the API is running on :8000.
```

`bootstrap_console.sh` pins a project-local Node runtime and installs exactly the locked console dependencies; it does not modify the AutoDL base image. Copy `console/.env.example` to `console/.env.local` only if API or ShopBench uses a non-default local URL. The browser console is intentionally not an authority for run outcome; it always refreshes server state after an SSE event.

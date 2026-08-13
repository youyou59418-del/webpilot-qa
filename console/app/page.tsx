"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  apiBaseUrl,
  approveRun,
  cancelRun,
  ConsoleView,
  createRun,
  getConsoleView,
} from "../lib/api";

const eventTypes = [
  "queued", "started", "approval_required", "approved", "completed",
  "failed", "cancel_requested", "cancelled", "cancelled_before_start",
];

function JsonBlock({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

export default function ConsolePage() {
  const [goal, setGoal] = useState("Search the ShopBench catalog for laptop and verify results are shown.");
  const [targetUrl, setTargetUrl] = useState(
    process.env.NEXT_PUBLIC_SHOPBENCH_URL ?? "http://127.0.0.1:8080/?reset=1",
  );
  const [runId, setRunId] = useState("");
  const [view, setView] = useState<ConsoleView | null>(null);
  const [message, setMessage] = useState("Create a run to observe its server-authoritative state.");

  const refresh = useCallback(async (id = runId) => {
    if (!id) return;
    try {
      setView(await getConsoleView(id));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to read run state.");
    }
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    void refresh(runId);
    const source = new EventSource(`${apiBaseUrl}/runs/${runId}/events/stream`);
    eventTypes.forEach((type) => source.addEventListener(type, () => void refresh(runId)));
    source.onerror = () => source.close();
    return () => source.close();
  }, [runId, refresh]);

  const run = view?.run ?? {};
  const status = typeof run.status === "string" ? run.status : "not_created";
  const artifactUrl = useMemo(() => (name: string) => `${apiBaseUrl}/runs/${runId}/artifacts/${name}`, [runId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const record = await createRun({ goal, target_url: targetUrl, max_steps: 12, max_retries: 2 });
      const id = String(record.run_id);
      setRunId(id);
      await refresh(id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create run.");
    }
  }

  async function mutate(operation: "approve" | "cancel") {
    if (!runId) return;
    try {
      if (operation === "approve") await approveRun(runId);
      else await cancelRun(runId);
      await refresh(runId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Run action failed.");
    }
  }

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">WebPilot-QA / Day 9</p>
          <h1>Verifiable Browser Run Console</h1>
          <p className="muted">This interface renders backend state and events; it never decides pass/fail locally.</p>
        </div>
        <span className={`status status-${status}`}>{status}</span>
      </header>

      <section className="card launch">
        <h2>Launch a controlled run</h2>
        <form onSubmit={submit}>
          <label>Goal<textarea value={goal} onChange={(event) => setGoal(event.target.value)} required /></label>
          <label>Target URL<input value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} required /></label>
          <button type="submit">Create run</button>
        </form>
        {runId && <p className="mono">Run ID: {runId}</p>}
        {message && <p className="message">{message}</p>}
      </section>

      {view && <>
        <section className="metrics" aria-label="Run metrics">
          <Metric label="Duration" value={`${view.metrics.duration_ms} ms`} />
          <Metric label="Tool calls" value={String(view.metrics.tool_calls)} />
          <Metric label="Retries" value={String(view.metrics.retries)} />
          <Metric label="Events" value={String(view.events.length)} />
        </section>

        <section className="actions">
          <button onClick={() => void refresh()} type="button">Refresh from API</button>
          {status === "approval_required" && <button className="approve" onClick={() => void mutate("approve")} type="button">Approve displayed action</button>}
          {!["completed", "failed", "cancelled"].includes(status) && <button className="danger" onClick={() => void mutate("cancel")} type="button">Cancel run</button>}
        </section>

        <div className="grid">
          <section className="card"><h2>Test plan</h2><JsonBlock value={view.plan ?? { pending: true }} /></section>
          <section className="card"><h2>Verifier evidence</h2><JsonBlock value={view.verifier_evidence} /></section>
          <section className="card"><h2>Agent trace</h2><JsonBlock value={view.action_trace} /></section>
          <section className="card"><h2>Recovery trace</h2><JsonBlock value={view.recovery_history} /></section>
          <section className="card"><h2>Event stream</h2><JsonBlock value={view.events} /></section>
          <section className="card"><h2>Run record</h2><JsonBlock value={run} /></section>
        </div>

        <section className="media-grid">
          <section className="card"><h2>Current screenshot</h2>
            {view.current_screenshot ? <img alt="Latest browser state" src={artifactUrl(view.current_screenshot.name)} /> : <p className="muted">No browser screenshot has been captured yet.</p>}
          </section>
          <section className="card"><h2>Artifacts</h2>
            <ul>{view.artifacts.map((artifact) => <li key={artifact.name}><a href={artifactUrl(artifact.name)} target="_blank">{artifact.name}</a></li>)}</ul>
            {view.trace && <p><a href={artifactUrl(view.trace.name)}>Download Playwright trace</a></p>}
          </section>
        </section>
      </>}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

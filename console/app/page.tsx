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

const statusLabels: Record<string, string> = {
  not_created: "未创建",
  queued: "排队中",
  running: "执行中",
  approval_required: "等待人工确认",
  completed: "已完成",
  failed: "执行失败",
  cancel_requested: "正在取消",
  cancelled: "已取消",
  cancelled_before_start: "启动前已取消",
};

function JsonBlock({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

export default function ConsolePage() {
  const [goal, setGoal] = useState("打开 ShopBench 商品目录，将 Laptop Pro 加入购物车，并确认购物车数量为 1 且包含 Laptop Pro。");
  const [targetUrl, setTargetUrl] = useState(
    process.env.NEXT_PUBLIC_SHOPBENCH_URL ?? "http://127.0.0.1:8080/?reset=1",
  );
  const [runId, setRunId] = useState("");
  const [view, setView] = useState<ConsoleView | null>(null);
  const [message, setMessage] = useState("创建任务后，可查看由服务端记录的执行状态。");

  const refresh = useCallback(async (id = runId) => {
    if (!id) return;
    try {
      setView(await getConsoleView(id));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法读取任务状态。");
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
  const statusLabel = statusLabels[status] ?? status;
  const artifactUrl = useMemo(() => (name: string) => `${apiBaseUrl}/runs/${runId}/artifacts/${name}`, [runId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const record = await createRun({ goal, target_url: targetUrl, max_steps: 12, max_retries: 2 });
      const id = String(record.run_id);
      setRunId(id);
      await refresh(id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法创建任务。");
    }
  }

  async function mutate(operation: "approve" | "cancel") {
    if (!runId) return;
    try {
      if (operation === "approve") await approveRun(runId);
      else await cancelRun(runId);
      await refresh(runId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "任务操作失败。");
    }
  }

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">WebPilot-QA / 浏览器智能体</p>
          <h1>可验证浏览器任务控制台</h1>
          <p className="muted">本界面仅展示服务端状态与事件，不在前端自行判定任务成败。</p>
        </div>
        <span className={`status status-${status}`}>{statusLabel}</span>
      </header>

      <section className="card launch">
        <h2>创建受控浏览器任务</h2>
        <form onSubmit={submit}>
          <label>任务目标<textarea value={goal} onChange={(event) => setGoal(event.target.value)} required /></label>
          <label>目标地址<input value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} required /></label>
          <button type="submit">创建任务</button>
        </form>
        {runId && <p className="mono">任务 ID: {runId}</p>}
        {message && <p className="message">{message}</p>}
      </section>

      {view && <>
        <section className="metrics" aria-label="任务指标">
          <Metric label="执行耗时" value={`${view.metrics.duration_ms} ms`} />
          <Metric label="工具调用" value={String(view.metrics.tool_calls)} />
          <Metric label="重试次数" value={String(view.metrics.retries)} />
          <Metric label="事件数" value={String(view.events.length)} />
        </section>

        <section className="actions">
          <button onClick={() => void refresh()} type="button">从 API 刷新</button>
          {status === "approval_required" && <button className="approve" onClick={() => void mutate("approve")} type="button">批准当前操作</button>}
          {!["completed", "failed", "cancelled"].includes(status) && <button className="danger" onClick={() => void mutate("cancel")} type="button">取消任务</button>}
        </section>

        <div className="grid">
          <section className="card"><h2>任务计划</h2><JsonBlock value={view.plan ?? { pending: true }} /></section>
          <section className="card"><h2>验证证据</h2><JsonBlock value={view.verifier_evidence} /></section>
          <section className="card"><h2>智能体操作轨迹</h2><JsonBlock value={view.action_trace} /></section>
          <section className="card"><h2>恢复轨迹</h2><JsonBlock value={view.recovery_history} /></section>
          <section className="card"><h2>事件流</h2><JsonBlock value={view.events} /></section>
          <section className="card"><h2>任务记录</h2><JsonBlock value={run} /></section>
        </div>

        <section className="media-grid">
          <section className="card"><h2>当前页面截图</h2>
            {view.current_screenshot ? <img alt="最新浏览器状态截图" src={artifactUrl(view.current_screenshot.name)} /> : <p className="muted">尚未捕获浏览器截图。</p>}
          </section>
          <section className="card"><h2>任务产物</h2>
            <ul>{view.artifacts.map((artifact) => <li key={artifact.name}><a href={artifactUrl(artifact.name)} target="_blank">{artifact.name}</a></li>)}</ul>
            {view.trace && <p><a href={artifactUrl(view.trace.name)}>下载 Playwright 追踪文件</a></p>}
          </section>
        </section>
      </>}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

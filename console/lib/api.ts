export type ConsoleView = {
  run: Record<string, unknown>;
  events: Array<Record<string, unknown>>;
  plan: Record<string, unknown> | null;
  action_trace: Array<Record<string, unknown>>;
  verifier_evidence: Array<Record<string, unknown>>;
  recovery_history: Array<Record<string, unknown>>;
  current_screenshot: { name: string } | null;
  trace: { name: string } | null;
  metrics: { duration_ms: number; tool_calls: number; retries: number };
  artifacts: Array<{ name: string; path: string }>;
};

export const apiBaseUrl = (
  process.env.NEXT_PUBLIC_WEBPILOT_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function asJson(response: Response) {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `请求失败 (${response.status})`);
  }
  return response.json();
}

export async function createRun(input: Record<string, unknown>) {
  return asJson(await fetch(`${apiBaseUrl}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }));
}

export async function getConsoleView(runId: string): Promise<ConsoleView> {
  return asJson(await fetch(`${apiBaseUrl}/runs/${runId}/console`, { cache: "no-store" }));
}

export async function approveRun(runId: string) {
  return asJson(await fetch(`${apiBaseUrl}/runs/${runId}/approve`, { method: "POST" }));
}

export async function cancelRun(runId: string) {
  return asJson(await fetch(`${apiBaseUrl}/runs/${runId}/cancel`, { method: "POST" }));
}

# WebPilot-QA architecture

```mermaid
flowchart LR
  U[Task / Console] --> API[FastAPI control plane]
  API --> Store[(Durable run and event store)]
  API --> Queue[Worker queue]
  Queue --> W[Browser worker]
  W --> P[Planner]
  P --> A[Actor + bounded tools]
  A --> O[Structured observation]
  A --> G[Safety gate]
  A --> V[Rule verifier]
  V --> R[Recovery + self-healing]
  W --> Art[Redacted artifacts / screenshot / trace]
  Art --> API
  B[ShopBench] --> O
  M[OpenAI API or local vLLM/Qwen] --> P
  M --> A
```

The console is read-only with respect to run truth: it renders API state and SSE events. Browser actions are restricted to structured tools; high-risk side effects require an approval fingerprint. The worker is the only component that owns browser execution.

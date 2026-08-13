from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable
from typing import Protocol


class RunQueue(Protocol):
    """Notification transport for durable run IDs; the database remains authoritative."""

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def enqueue(self, run_id: str) -> None: ...

    async def dequeue(self) -> str: ...

    async def task_done(self) -> None: ...

    async def wait_for_idle(self) -> None: ...


class InMemoryRunQueue:
    """Deterministic test/development queue used when Redis is not configured."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def enqueue(self, run_id: str) -> None:
        await self._queue.put(run_id)

    async def dequeue(self) -> str:
        return await self._queue.get()

    async def task_done(self) -> None:
        self._queue.task_done()

    async def wait_for_idle(self) -> None:
        await self._queue.join()


class RedisRunQueue:
    """Redis list queue for run notifications.

    A run is always first persisted in PostgreSQL.  Duplicate notifications are
    harmless because the worker atomically claims only queued runs.  On worker
    restart, the database requeues interrupted runs, which prevents a BLPOP
    message from becoming the sole source of truth.
    """

    def __init__(self, *, redis_url: str, key: str) -> None:
        self.redis_url = redis_url
        self.key = key
        self._client = None
        self._active = 0

    async def start(self) -> None:
        try:
            from redis.asyncio import Redis
        except ImportError as exc:  # pragma: no cover - configuration error
            raise RuntimeError("Redis mode requires the 'redis' package.") from exc
        self._client = Redis.from_url(self.redis_url, decode_responses=True)
        await self._client.ping()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def enqueue(self, run_id: str) -> None:
        await self._require_client().rpush(self.key, run_id)

    async def dequeue(self) -> str:
        client = self._require_client()
        while True:
            item = await client.blpop(self.key, timeout=1)
            if item is not None:
                _, run_id = item
                self._active += 1
                return str(run_id)

    async def task_done(self) -> None:
        self._active = max(0, self._active - 1)

    async def wait_for_idle(self) -> None:
        client = self._require_client()
        while self._active or await client.llen(self.key):
            await asyncio.sleep(0.02)

    def _require_client(self):
        if self._client is None:
            raise RuntimeError("RedisRunQueue.start() must be awaited before use.")
        return self._client


def build_run_queue_from_env() -> RunQueue:
    redis_url = os.environ.get("WEBPILOT_REDIS_URL", "").strip()
    if not redis_url:
        return InMemoryRunQueue()
    return RedisRunQueue(
        redis_url=redis_url,
        key=os.environ.get("WEBPILOT_QUEUE_KEY", "webpilot:run-queue"),
    )

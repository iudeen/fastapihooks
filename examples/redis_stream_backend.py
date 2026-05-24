"""
Redis Streams Backend for Fasthooks
====================================
A queue-backed transport that uses Redis Streams with consumer groups for
reliable, horizontally-scalable webhook delivery.

Install dependency:
    pip install redis[asyncio]

Usage with the sidecar engine:
    fasthooks start \
        --backend-module examples.redis_stream_backend:redis_backend \
        --store-module myapp.stores:store \
        --signing-secret "your-secret"

Or wire it up in your FastAPI app for the emit path:
    from examples.redis_stream_backend import RedisStreamBackend
    from fasthooks import Fasthooks

    backend = RedisStreamBackend(redis_url="redis://localhost:6379")
    hooks = Fasthooks(backend=backend)

Design notes:
- publish()  → XADD to a Redis Stream.
- consume()  → XREADGROUP from a consumer group; yields one event at a time.
- ack()      → XACK so the message is not re-delivered to another worker.
- Multiple workers sharing the same consumer_group process events exactly once
  (at-least-once delivery with proper ack).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fasthooks.backends import BaseBackend
from fasthooks.stores.base_store import WebhookSubscription

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError as e:
    raise ImportError(
        "redis[asyncio] is required for RedisStreamBackend. "
        "Install it with: pip install redis[asyncio]"
    ) from e


@dataclass
class RedisWebhookEvent:
    """Envelope returned by consume() that the sidecar engine reads."""
    id: str
    event_name: str
    payload: Any
    owner_id: str | None = None


class RedisStreamBackend(BaseBackend):
    """
    Redis Streams backend using consumer groups for horizontal scale.

    Each worker instance in the same consumer_group receives a unique slice of
    events — no duplicate processing across workers.

    Args:
        redis_url:       Redis connection URL (default: redis://localhost:6379).
        stream_key:      Name of the Redis Stream (default: fasthooks:events).
        consumer_group:  Consumer group name shared across all workers.
        consumer_name:   Unique name for this worker instance.
        block_ms:        How long XREADGROUP blocks waiting for new messages (ms).
        batch_size:      Max messages to fetch per XREADGROUP call.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        stream_key: str = "fasthooks:events",
        consumer_group: str = "fasthooks-workers",
        consumer_name: str = "worker-1",
        block_ms: int = 5000,
        batch_size: int = 10,
    ) -> None:
        self._redis_url = redis_url
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.block_ms = block_ms
        self.batch_size = batch_size
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    # ------------------------------------------------------------------
    # BaseBackend interface
    # ------------------------------------------------------------------

    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: str | None,
        subscribers: list[WebhookSubscription] | None = None,
    ) -> None:
        """Enqueue an event onto the Redis Stream."""
        client = await self._get_client()
        await client.xadd(
            self.stream_key,
            {
                "event_name": event_name,
                "payload": json.dumps(payload),
                "owner_id": owner_id or "",
            },
        )
        logger.debug("Published event %r to stream %s", event_name, self.stream_key)

    async def consume(self) -> AsyncIterator[RedisWebhookEvent]:
        """
        Yield events from the stream via consumer group.

        Blocks up to block_ms waiting for new messages, then loops.
        The caller (FasthooksEngine) is responsible for calling ack() after
        successful dispatch.
        """
        client = await self._get_client()
        await self._ensure_group(client)

        while True:
            results = await client.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {self.stream_key: ">"},
                count=self.batch_size,
                block=self.block_ms,
            )

            if not results:
                continue

            for _, messages in results:
                for message_id, data in messages:
                    yield RedisWebhookEvent(
                        id=message_id,
                        event_name=data["event_name"],
                        payload=json.loads(data["payload"]),
                        owner_id=data.get("owner_id") or None,
                    )

    async def ack(self, event_id: str) -> None:
        """Acknowledge a successfully processed event."""
        client = await self._get_client()
        await client.xack(self.stream_key, self.consumer_group, event_id)
        logger.debug("Acked event %s", event_id)

    async def aclose(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("Redis connection closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_group(self, client: aioredis.Redis) -> None:
        """Create the consumer group if it does not already exist."""
        try:
            await client.xgroup_create(
                self.stream_key,
                self.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Created consumer group %r on stream %s",
                self.consumer_group,
                self.stream_key,
            )
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise


# ---------------------------------------------------------------------------
# Reusable singleton — referenced by the CLI example in the module docstring.
# Override these values via env vars or replace with your own instance.
# ---------------------------------------------------------------------------
redis_backend = RedisStreamBackend()

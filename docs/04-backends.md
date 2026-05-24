# 04. Backends

## Policy
Fasthooks ships with one built-in backend:
- BackgroundTaskBackend

Other transports should be implemented externally by subclassing BaseBackend.

## BaseBackend Contract
Methods expected:
- publish(event_name, payload, owner_id, subscribers=None)
- consume()
- ack(event_id)
- aclose()

Design intent:
- publish is required for emit path.
- consume and ack are for worker-driven queue backends.
- aclose releases client/network resources.

## BackgroundTaskBackend
What it does:
- Delivers to direct subscribers when provided.
- Delivers via store-resolved subscriptions when store is configured.
- Uses WebhookDispatcher for HTTP fan-out.

Features:
- HMAC signing support.
- Retry/backoff controls.
- Dead-letter callback hook.
- Async context manager and aclose support.

## Custom Backend Template
```python
from typing import Any

from fasthooks.backends import BaseBackend
from fasthooks.stores.base_store import WebhookSubscription

class MyQueueBackend(BaseBackend):
    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: str | None,
        subscribers: list[WebhookSubscription] | None = None,
    ):
        ...

    async def consume(self):
        ...

    async def ack(self, event_id: str):
        ...

    async def aclose(self) -> None:
        return None
```

## Implementation Guidance
- Keep signature parity with BaseBackend.
- Do not mutate payload in transport layer unless documented.
- Keep retry semantics in one place to avoid double retries.

## Reference Implementation: Redis Streams

`examples/redis_stream_backend.py` provides a production-ready Redis Streams backend.

Key design:
- `publish()` calls `XADD` to enqueue the event.
- `consume()` uses `XREADGROUP` with a consumer group — multiple workers share the stream without processing the same event twice.
- `ack()` calls `XACK` to confirm delivery.

```python
from examples.redis_stream_backend import RedisStreamBackend
from fasthooks import Fasthooks

backend = RedisStreamBackend(
    redis_url="redis://localhost:6379",
    consumer_group="prod-workers",
    consumer_name="worker-1",  # unique per worker instance
)
hooks = Fasthooks(backend=backend)
```

Run a worker:
```bash
fasthooks start \
    --backend-module examples.redis_stream_backend:redis_backend \
    --store-module myapp.stores:store \
    --signing-secret "your-secret"
```

Scale horizontally by launching additional workers with different `consumer_name` values in the same `consumer_group`. Redis ensures each event is processed exactly once across the group.

Install: `pip install redis[asyncio]`

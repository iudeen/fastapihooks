# 11. Building Extensions

This page explains how to build your own Fastapihooks backends and stores as reusable
packages or project-local modules. The reference implementations in `examples/` follow
these patterns exactly.

---

## Building a Custom Backend

A backend controls **how events travel from your API to the dispatcher**. The built-in
`BackgroundTaskBackend` dispatches inline via FastAPI `BackgroundTasks`. A custom
backend typically enqueues events into a durable transport (Redis, SQS, Kafka) so that
a separate sidecar worker can consume and deliver them.

### Contract

Subclass `BaseBackend` and implement:

| Method | Required | Purpose |
|---|---|---|
| `publish(event_name, payload, owner_id, subscribers)` | **Yes** | Enqueue or immediately dispatch an event |
| `consume()` | For queue backends | Async generator yielding event objects |
| `ack(event_id)` | For queue backends | Acknowledge successful processing |
| `aclose()` | Optional | Release connections/resources on shutdown |

### Minimal template

```python
from typing import Any
from fastapihooks.backends import BaseBackend
from fastapihooks.stores.base_store import WebhookSubscription


class MyBackend(BaseBackend):
    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: str | None,
        subscribers: list[WebhookSubscription] | None = None,
    ) -> None:
        # Enqueue to your transport
        ...

    async def aclose(self) -> None:
        # Close any open connections
        ...
```

### Queue backend template (with sidecar worker)

```python
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapihooks.backends import BaseBackend
from fastapihooks.stores.base_store import WebhookSubscription


@dataclass
class MyEvent:
    id: str
    event_name: str
    payload: Any


class MyQueueBackend(BaseBackend):
    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: str | None,
        subscribers: list[WebhookSubscription] | None = None,
    ) -> None:
        # Write event to your queue
        await self._queue.put(event_name, payload)

    async def consume(self) -> AsyncIterator[MyEvent]:
        # Yield events one at a time for the engine to dispatch
        async for raw in self._queue.listen():
            yield MyEvent(
                id=raw["id"],
                event_name=raw["event_name"],
                payload=raw["payload"],
            )

    async def ack(self, event_id: str) -> None:
        # Mark the event as successfully processed
        await self._queue.ack(event_id)

    async def aclose(self) -> None:
        await self._queue.close()
```

> **Event object shape:** The sidecar engine (`FastapihooksEngine`) reads `.id`,
> `.event_name`, and `.payload` from each yielded object. Your dataclass or model
> must expose these three attributes.

### Wiring it into a FastAPI app

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapihooks import Fastapihooks

backend = MyQueueBackend(...)
hooks = Fastapihooks(backend=backend)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with hooks:   # calls backend.aclose() on shutdown
        yield

app = FastAPI(lifespan=lifespan)

@app.post("/orders")
@hooks.hook("order.created")
async def create_order(background_tasks: BackgroundTasks):
    return {"id": "ord_123"}
```

### Running the sidecar worker

```bash
fastapihooks start \
    --backend-module myapp.backends:my_backend_instance \
    --store-module myapp.stores:my_store_instance \
    --signing-secret "your-secret" \
    --max-concurrency 50
```

Scale horizontally by launching additional worker processes. If your transport
supports consumer groups (Redis Streams, Kafka), configure each worker with a
unique consumer name so events are distributed without duplication.

### Reference implementation

See `examples/redis_stream_backend.py` for a full Redis Streams backend that covers:
- Lazy connection management
- Consumer group auto-creation
- `XADD` / `XREADGROUP` / `XACK` usage
- Graceful `aclose()`

---

## Building a Custom Store

A store manages **webhook subscriptions** — which URLs receive which events.
The built-in stores are `MemoryStore` (dev/test) and `SQLStore` (relational DBs).
Build a custom store to use MongoDB, DynamoDB, Redis, or any other data layer.

### Contract

Subclass `BaseStore` and implement:

| Method | Returns | Purpose |
|---|---|---|
| `add_subscription(event_name, target_url, ...)` | `str` (ID) | Persist a new subscription |
| `remove_subscription(subscription_id)` | `bool` | Delete by ID; True if found |
| `get_subscriptions(event_name)` | `Iterable[StoredWebhookSubscription]` | Fetch all subscribers for an event |
| `update_subscription(subscription_id, ...)` | `bool` | Partial update; True if found |
| `get_subscription(subscription_id)` | `StoredWebhookSubscription \| None` | Fetch a single subscription |

### Minimal template

```python
import uuid
from collections.abc import Iterable
from typing import Any, Literal

from fastapihooks.stores import BaseStore, StoredWebhookSubscription


class MyStore(BaseStore):

    async def add_subscription(
        self,
        event_name: str,
        target_url: str,
        auth_type: Literal["bearer", "none"] = "none",
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        sid = str(uuid.uuid4())
        # persist to your data layer
        return sid

    async def remove_subscription(self, subscription_id: str) -> bool:
        # delete and return True if found
        ...

    async def get_subscriptions(self, event_name: str) -> Iterable[StoredWebhookSubscription]:
        # query by event_name, return a list of StoredWebhookSubscription
        ...

    async def update_subscription(
        self,
        subscription_id: str,
        target_url: str | None = None,
        auth_type: Literal["bearer", "none"] | None = None,
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        # apply partial update, return True if found
        ...

    async def get_subscription(self, subscription_id: str) -> StoredWebhookSubscription | None:
        # fetch single subscription or return None
        ...
```

### Implementation guidance

**Index `event_name`.**
`get_subscriptions` is called on every webhook emit. Without an index it becomes
a full-collection scan at scale. Always create an index (or equivalent) on `event_name`.

**Merge metadata on update, don't replace.**
Users expect `update_subscription(id, metadata={"new_key": "v"})` to preserve
existing keys. The pattern:
```python
merged = {**existing_metadata, **incoming_metadata}
```

**Return the right booleans.**
`remove_subscription` and `update_subscription` must return `False` (not raise)
when the ID is not found — the caller uses the boolean to decide response codes.

**Validate at the boundary.**
Validate `target_url` format and `auth_type` values before writing. Pydantic's
`WebhookSubscription` model validates these on read, but write paths go through
your store directly.

### Wiring into the app

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapihooks import Fastapihooks
from fastapihooks.backends import BackgroundTaskBackend

store = MyStore(...)
backend = BackgroundTaskBackend(signing_secret="your-secret", store=store)
hooks = Fastapihooks(backend=backend)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init_indexes()   # if your store requires startup work
    async with hooks:
        yield

app = FastAPI(lifespan=lifespan)
```

### Reference implementation

See `examples/mongodb_store.py` for a full Motor-based store that covers:
- `init_indexes()` for startup index creation
- Async cursor iteration with `async for`
- Metadata merge on update
- `_to_model()` helper to convert raw documents to `StoredWebhookSubscription`

---

## Testing your extension

Mock your external dependency at the `sys.modules` level before importing your
extension module. This lets tests run without a live Redis/MongoDB/etc. server.

```python
# test_my_backend.py
import sys
from unittest.mock import AsyncMock, MagicMock

# Inject mock before importing your extension
_mock_client_lib = MagicMock()
sys.modules["my_queue_lib"] = _mock_client_lib
sys.modules.pop("myapp.backends", None)  # force reimport with mock

from myapp.backends import MyQueueBackend

async def test_publish_enqueues_event():
    backend = MyQueueBackend()
    mock_queue = AsyncMock()
    backend._queue = mock_queue
    await backend.publish("order.created", {"id": "1"}, owner_id=None)
    mock_queue.put.assert_called_once()
```

See `tests/test_example_redis_backend.py` and `tests/test_example_mongodb_store.py`
for complete worked examples of this pattern.

---

## Packaging your extension

Extensions can live in your application codebase or be published as standalone
packages. If publishing to PyPI:

1. Name the package `fastapihooks-<transport>` (e.g., `fastapihooks-redis`, `fastapihooks-sqs`).
2. Declare `fastapihooks` as a dependency without pinning the minor version: `fastapihooks>=0.1`.
3. Add the optional transport library as a dependency with extras:
   ```toml
   [project]
   dependencies = ["fastapihooks>=0.1", "redis[asyncio]>=5.0"]
   ```
4. Export your class from the package root so users can do:
   ```python
   from fastapihooks_redis import RedisStreamBackend
   ```

# 🪝 Fasthooks

Fasthooks is a high-performance, and pluggable webhook management system for FastAPI. It allows you to "webhook-enable" any router with a single decorator, offloading the heavy lifting to a scalable sidecar worker while keeping your API response times near zero.

## 📚 Documentation
- Full multi-page docs: [docs/index.md](docs/index.md)

## ✨ Key Features
- ⚡ Zero-Impact Emission: Uses FastAPI BackgroundTasks to ensure webhook processing never slows down your API flow.

- 🔌 Backend by Design, Extensions by You: Fasthooks ships with `BackgroundTaskBackend` only. Build Redis/Kafka/SQS backends by implementing `BaseBackend`.

- 🛠️ Sidecar Worker: A dedicated async engine designed for high-concurrency delivery with built-in retries and HMAC signing.

- 🛡️ Secure by Default: Optional HMAC-SHA256 signing — when a `signing_secret` is provided, every delivery includes a verifiable `X-Fasthooks-Signature` header.

- 📊 Observable: Telemetry support (Logfire, OpenTelemetry, Prometheus) planned for a future release.

- 📝 Type-Safe: Powered by Pydantic for flexible payload transformations.

## Quick Start
1. Install 
    ```bash 
    pip install fasthooks
    ```
2. Configure
    ```python
    from contextlib import asynccontextmanager
    from fastapi import FastAPI, BackgroundTasks, Request
    from fasthooks import Fasthooks
    from fasthooks.backends import BackgroundTaskBackend

    hooks = Fasthooks(backend=BackgroundTaskBackend(signing_secret="your-secret"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with hooks:   # closes HTTP connections on shutdown
            yield

    app = FastAPI(lifespan=lifespan)

    @app.post("/orders")
    @hooks.hook("order.created")
    async def create_order(request: Request, background_tasks: BackgroundTasks):
        # Your business logic here
        return {"id": "ord_123", "status": "confirmed"}
    ```
3. Run the Worker (The Sidecar)
    ```bash 
    # Not required for BackgroundTaskBackend; dispatch runs in FastAPI BackgroundTasks.
    # Use the sidecar only when you implement a queue backend with consume()/ack().
    fasthooks start --backend-module myapp.backends:custom_backend --store-module myapp.stores:store --signing-secret "your-secret"
    ```

## Advanced Capabilities 

#### Flexible Transformations
Don't just dump your API response. Use the FasthooksContext to shape exactly what your subscribers see.
```python
def my_transformer(ctx: FasthooksContext):
    return {
        "event": ctx.event_name,
        "order_id": ctx.response_payload["id"],
        "user_agent": ctx.headers.get("user-agent")
    }

@app.post("/orders")
@hooks.hook("order.created", transform=my_transformer, include_headers=True)
async def create_order(...):
    ...
```

#### Pluggable Architecture

| Component | Responsibility | Available Drivers |
|---|---|---|
|Backend| Transport Layer| `BackgroundTaskBackend` (Built-in), custom via `BaseBackend`
|Store|Subscription Data| `SQLStore` (PostgreSQL, MySQL, SQLite via SQLAlchemy), `MemoryStore` (dev/testing), custom via `BaseStore`
|Telemetry|Observability| Planned — `Logfire`, `OpenTelemetry`, `Prometheus`

#### Custom Store Contract
Use `BaseStore` to bring your own subscription storage — MongoDB, DynamoDB, Redis, or anything else.

```python
from collections.abc import Iterable
from typing import Any, Literal

from fasthooks.stores import BaseStore, StoredWebhookSubscription


class MyMongoStore(BaseStore):
    async def add_subscription(self, event_name, target_url, auth_type="none", auth_value=None, metadata=None) -> str:
        ...  # insert and return generated ID

    async def remove_subscription(self, subscription_id: str) -> bool:
        ...  # delete by ID, return True if found

    async def get_subscriptions(self, event_name: str) -> Iterable[StoredWebhookSubscription]:
        ...  # query by event_name

    async def update_subscription(self, subscription_id, target_url=None, auth_type=None, auth_value=None, metadata=None) -> bool:
        ...  # partial update, return True if found
```

#### Custom Backend Contract
Use `BaseBackend` to add your own transport backend while keeping the main library lightweight.

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
        # enqueue event to your transport
        ...

    async def consume(self):
        # yield queued events for worker mode
        ...

    async def ack(self, event_id: str):
        # ack successful processing
        ...
```

## Scalability Design
Fasthooks is designed for horizontal scale. By using an asynchronous backend (eg: Redis Stream Backend), you can run multiple sidecar workers in a Consumer Group. This allows you to process millions of webhooks across a cluster of workers without duplicate deliveries.

## Security: HMAC Verification
Fasthooks signs every payload. Your users can verify the authenticity of a webhook using the `X-Fasthooks-Signature` header.

The header value is formatted as `sha256=<hex-digest>`, matching the convention used by GitHub, Stripe, and most webhook providers.

```python
import hashlib
import hmac

def verify_signature(payload: bytes, secret: str, header: str) -> bool:
    algorithm, _, received = header.partition("=")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)
```

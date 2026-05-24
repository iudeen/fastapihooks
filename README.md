# 🪝 Fasthooks

Fasthooks is a high-performance, and pluggable webhook management system for FastAPI. It allows you to "webhook-enable" any router with a single decorator, offloading the heavy lifting to a scalable sidecar worker while keeping your API response times near zero.

## ✨ Key Features
- ⚡ Zero-Impact Emission: Uses FastAPI BackgroundTasks to ensure webhook processing never slows down your API flow.

- 🔌 Backend by Design, Extensions by You: Fasthooks ships with `BackgroundTaskBackend` only. Build Redis/Kafka/SQS backends by implementing `BaseBackend`.

- 🛠️ Sidecar Worker: A dedicated async engine designed for high-concurrency delivery with built-in retries and HMAC signing.

- 🛡️ Secure by Default: Automatic HMAC-SHA256 signatures included in every header.

- 📊 Observable: First-class support for Logfire, OpenTelemetry, and Prometheus.

- 📝 Type-Safe: Powered by Pydantic for flexible payload transformations.

## Quick Start
1. Install 
    ```bash 
    pip install fasthooks
    ```
2. Configure
    ```python
    from fastapi import FastAPI, BackgroundTasks, Request
    from fasthooks import Fasthooks
    from fasthooks.backends import BackgroundTaskBackend

    app = FastAPI()

    hooks = Fasthooks(backend=BackgroundTaskBackend(signing_secret="your-secret"))

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
|Backend| Transport Layer| `BackgroundTaskBackend` (Built-in), `Custom Backends via BaseBackend`
|Store|Subscription Data| `MongoDB`, `SQLAlchemy`, `Memory`
|Telemetry|Observability| `Logfire`, `OpenTelemetry`, `Prometheus`

#### Custom Backend Contract
Use `BaseBackend` to add your own transport backend while keeping the main library lightweight.

```python
from typing import Any, Optional

from fasthooks.backends import BaseBackend
from fasthooks.stores.base_store import WebhookSubscription


class MyQueueBackend(BaseBackend):
    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: Optional[str],
        subscribers: Optional[list[WebhookSubscription]] = None,
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
Fasthooks is designed for horizontal scale. By using the a asynchronous backend (eg: Redis Stream Backend), you can run multiple sidecar workers in a Consumer Group. This allows you to process millions of webhooks across a cluster of workers without duplicate deliveries.

## Security: HMAC Verification
Fasthooks signs every payload. Your users can verify the authenticity of a webhook using the `X-Fasthooks-Signature` header.



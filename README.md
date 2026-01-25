# 🪝 Fasthooks

Fasthooks is a high-performance, and pluggable webhook management system for FastAPI. It allows you to "webhook-enable" any router with a single decorator, offloading the heavy lifting to a scalable sidecar worker while keeping your API response times near zero.

## ✨ Key Features
- ⚡ Zero-Impact Emission: Uses FastAPI BackgroundTasks to ensure webhook processing never slows down your API flow.

- 🔌 Fully Pluggable: Swap out Backends (Redis, Kafka, SQS) and Subscription Stores (Mongo, Postgres, Memory) with zero changes to your business logic.

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
    from fasthooks.backends import RedisBackend

    app = FastAPI()

    # Point to your production Redis
    hooks = Fasthooks(backend=RedisBackend(url="redis://localhost:6379"))

    @app.post("/orders")
    @hooks.hook("order.created")
    async def create_order(request: Request, background_tasks: BackgroundTasks):
        # Your business logic here
        return {"id": "ord_123", "status": "confirmed"}
    ```
3. Run the Worker (The Sidecar)
    ```bash 
    fasthooks worker --backend redis --store mongodb --signing-secret "your-secret"
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
|Backend| Transport Layer| `RedisStream`, `Kafka`, `BackgroundTasks` (Local)
|Store|Subscription Data| `MongoDB`, `SQLAlchemy`, `Memory`
|Telemetry|Observability| `Logfire`, `OpenTelemetry`, `Prometheus`

## Scalability Design
Fasthooks is designed for horizontal scale. By using the a asynchronous backend (eg: Redis Stream Backend), you can run multiple sidecar workers in a Consumer Group. This allows you to process millions of webhooks across a cluster of workers without duplicate deliveries.

## Security: HMAC Verification
Fasthooks signs every payload. Your users can verify the authenticity of a webhook using the `X-Fasthooks-Signature` header.



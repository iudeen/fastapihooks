# 02. Quick Start

## Requirements
- Python 3.10+
- FastAPI app

## Install
```bash
pip install fastapihooks
```

## Minimal Setup
```python
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, Request

from fastapihooks import Fastapihooks
from fastapihooks.backends import BackgroundTaskBackend

hooks = Fastapihooks(
    backend=BackgroundTaskBackend(signing_secret="dev-secret")
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with hooks:
        yield

app = FastAPI(lifespan=lifespan)

@app.post("/orders")
@hooks.hook("order.created")
async def create_order(request: Request, background_tasks: BackgroundTasks):
    return {"id": "ord_123", "status": "confirmed"}
```

## Add Direct Subscribers
```python
from fastapihooks.stores import WebhookSubscription

hooks = Fastapihooks(
    backend=BackgroundTaskBackend(signing_secret="dev-secret"),
    subscribers={
        "order.created": [
            WebhookSubscription(
                event_name="order.created",
                target_url="https://example.com/webhooks/orders",
                auth_type="none",
            )
        ]
    },
)
```

## Transform Payloads
```python
from fastapihooks import FastapihooksContext

def transform_order(ctx: FastapihooksContext):
    return {
        "event": ctx.event_name,
        "owner": ctx.owner_id,
        "order_id": ctx.response_payload["id"],
    }

@app.post("/orders")
@hooks.hook("order.created", transform=transform_order)
async def create_order(request: Request, background_tasks: BackgroundTasks):
    return {"id": "ord_123", "status": "confirmed"}
```

## Notes
- BackgroundTaskBackend does not require a separate worker process.
- Use the sidecar engine only for custom queue backends that implement consume and ack.

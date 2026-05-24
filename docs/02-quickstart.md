# 02. Quick Start

## Requirements
- Python 3.10+
- FastAPI app

## Install
```bash
pip install fasthooks
```

## Minimal Setup
```python
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, Request

from fasthooks import Fasthooks
from fasthooks.backends import BackgroundTaskBackend

hooks = Fasthooks(
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
from fasthooks.stores import WebhookSubscription

hooks = Fasthooks(
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
from fasthooks import FasthooksContext

def transform_order(ctx: FasthooksContext):
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

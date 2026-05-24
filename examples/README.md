# Fasthooks Examples

Reference implementations for extending Fasthooks with external transports and stores.
These files are ready to copy into your own project and adapt.

## redis_stream_backend.py

A Redis Streams backend with consumer group support for horizontal scale.

**Dependency:** `pip install redis[asyncio]`

**When to use:**
- You need multiple worker processes delivering webhooks without duplicates.
- You want durable event queuing (events survive app restarts).
- You need fan-out across a cluster.

**How it works:**

```
Your API  ──► publish() ──► XADD ──► Redis Stream
                                          │
                              ┌───────────┴───────────┐
                           Worker 1               Worker 2
                        XREADGROUP             XREADGROUP
                        (consumer group — each event goes to one worker)
                              │
                         dispatch webhooks
                              │
                           XACK
```

**Quick start:**
```python
from examples.redis_stream_backend import RedisStreamBackend
from fasthooks import Fasthooks

backend = RedisStreamBackend(
    redis_url="redis://localhost:6379",
    consumer_group="prod-workers",
    consumer_name="worker-1",   # unique per worker instance
)
hooks = Fasthooks(backend=backend)
```

**Run the sidecar worker:**
```bash
fasthooks start \
    --backend-module examples.redis_stream_backend:redis_backend \
    --store-module myapp.stores:store \
    --signing-secret "your-secret"
```

---

## mongodb_store.py

A MongoDB subscription store using the Motor async driver.

**Dependency:** `pip install motor`

**When to use:**
- You are already running MongoDB.
- You need durable, shared subscriptions across multiple app instances.
- You want schema-free subscription metadata.

**Quick start:**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from examples.mongodb_store import MongoDBStore
from fasthooks import Fasthooks
from fasthooks.backends import BackgroundTaskBackend

store = MongoDBStore(
    mongo_url="mongodb://localhost:27017",
    database="myapp",
)

backend = BackgroundTaskBackend(signing_secret="your-secret", store=store)
hooks = Fasthooks(backend=backend)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init_indexes()   # creates event_name index on first run
    async with hooks:
        yield
    store.close()

app = FastAPI(lifespan=lifespan)
```

**Managing subscriptions at runtime:**
```python
# Register a subscriber
sid = await store.add_subscription(
    event_name="order.created",
    target_url="https://partner.example.com/webhooks",
    auth_type="bearer",
    auth_value="partner-token",
)

# Update it
await store.update_subscription(sid, target_url="https://partner.example.com/v2/webhooks")

# Remove it
await store.remove_subscription(sid)
```

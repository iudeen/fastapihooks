# 05. Stores

## BaseStore Contract
Stores manage webhook subscriptions by event name.

Required methods:
- add_subscription(...)
- remove_subscription(subscription_id)
- get_subscriptions(event_name)
- update_subscription(subscription_id, ...)

Optional method:
- get_subscription(subscription_id)

## Included Stores
- MemoryStore: in-memory implementation for development/testing.
- SQLStore: SQLAlchemy async store for relational databases.

## Subscription Model
WebhookSubscription fields:
- event_name
- target_url
- auth_type: bearer or none
- auth_value
- metadata

StoredWebhookSubscription adds:
- id

## Choosing a Store
Use MemoryStore when:
- local prototyping
- short-lived process
- test scenarios

Use SQLStore when:
- durable subscriptions are needed
- multiple instances share subscriptions
- operational visibility is required

## Custom Store Guidance
- Keep event_name indexing efficient.
- Use partial metadata merges for update paths.
- Validate target_url and auth constraints near write boundaries.

## Reference Implementation: MongoDB

`examples/mongodb_store.py` provides a ready-to-use MongoDB store via Motor (async driver).

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from examples.mongodb_store import MongoDBStore
from fastapihooks import Fastapihooks
from fastapihooks.backends import BackgroundTaskBackend

store = MongoDBStore(mongo_url="mongodb://localhost:27017", database="myapp")
backend = BackgroundTaskBackend(signing_secret="your-secret", store=store)
hooks = Fastapihooks(backend=backend)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init_indexes()   # creates event_name index on first run
    async with hooks:
        yield
    store.close()

app = FastAPI(lifespan=lifespan)
```

Managing subscriptions at runtime:
```python
sid = await store.add_subscription(
    event_name="order.created",
    target_url="https://partner.example.com/webhooks",
    auth_type="bearer",
    auth_value="partner-token",
)
await store.update_subscription(sid, target_url="https://partner.example.com/v2/webhooks")
await store.remove_subscription(sid)
```

Install: `pip install motor`

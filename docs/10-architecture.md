# 10. Concepts and Architecture

This page explains how Fasthooks is built from the inside out.
No prior framework knowledge required — if you know what an API is, you can follow along.

---

## The Problem Fasthooks Solves

Imagine you run a shop. When a customer places an order, you need to:

1. Confirm the order quickly — the customer is waiting on the screen.
2. Notify five other systems (inventory, shipping, CRM, email, analytics) about the order.

If you notify all five systems *before* responding to the customer, the response takes forever.
If you notify them *after*, you have to make sure it actually happens — reliably.

That is exactly the problem webhooks solve, and Fasthooks is a framework that handles the "notify after" part cleanly.

---

## High-Level Picture

```
Your FastAPI app
      │
      ▼
┌─────────────────────────────────────────────────┐
│  @hooks.hook("order.created")                   │
│  async def create_order(...)                    │
│       │                                         │
│       1. Run your business logic                │
│       2. Capture event context                  │
│       3. Hand off to backend (non-blocking)     │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Backend             │
          │  (publishes event)   │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Dispatcher          │
          │  (fan-out delivery)  │
          └──────────┬───────────┘
                     │
           ┌─────────┴──────────┐
           ▼                    ▼
   Subscriber A         Subscriber B
   (your user's         (your analytics
    webhook URL)         webhook URL)
```

Your API response returns at step 1.
Everything below is asynchronous — the customer never waits for it.

---

## The Five Building Blocks

### 1. The Decorator (`hooks.hook`)

This is the entry point you add to any FastAPI route.

```python
@app.post("/orders")
@hooks.hook("order.created")
async def create_order(request: Request, background_tasks: BackgroundTasks):
    return {"id": "ord_123", "status": "confirmed"}
```

What it does internally:
- Wraps your function without changing its behavior.
- After your function returns a response, it triggers the emit path.
- The emit path runs in the background (via FastAPI's `BackgroundTasks`) so it never delays the API response.

Think of it as a listener attached to your function's exit door.

---

### 2. The Context (`FasthooksContext`)

Before dispatching anything, Fasthooks packages what happened into a context object.

```python
class FasthooksContext:
    event_name: str          # e.g. "order.created"
    owner_id: str | None     # e.g. a tenant or user ID
    timestamp: datetime      # when the event happened
    headers: dict | None     # request headers (opt-in)
    request_payload: bytes | None  # request body (opt-in)
    response_payload: Any          # your endpoint's return value
```

You can use this context to transform what gets sent to subscribers.

```python
def my_transform(ctx: FasthooksContext):
    return {
        "event": ctx.event_name,
        "order_id": ctx.response_payload["id"],
    }
```

Without a transform, the raw response payload is sent as-is.

---

### 3. The Backend

The backend decides **how** the event gets published.

Fasthooks ships with one backend built in: `BackgroundTaskBackend`.

```
BackgroundTaskBackend
  ├── Receives publish(event_name, payload, owner_id, subscribers)
  ├── Resolves subscriber list (direct or from store)
  └── Hands off to WebhookDispatcher for HTTP delivery
```

No queue, no external service, no extra process needed.
The backend runs inside your existing FastAPI process.

For production scale (millions of events), you would implement a custom backend backed by Redis Streams, Kafka, or SQS. The contract is simple — implement `publish`, `consume`, and `ack`.

---

### 4. The Store

The store is a database of who is subscribed to what event.

```
Store
  ├── add_subscription(event_name, target_url, ...)
  ├── remove_subscription(id)
  ├── get_subscriptions(event_name)    ← used by dispatcher
  └── update_subscription(id, ...)
```

Built-in options:

| Store | Use When |
|---|---|
| `MemoryStore` | Local development, tests, one-off scripts |
| `SQLStore` | Production apps with a relational database |

The store is optional. If you pass subscribers directly to `Fasthooks(subscribers={...})`, no store is needed at all.

---

### 5. The Dispatcher (`WebhookDispatcher`)

The dispatcher is the engine that actually sends HTTP POST requests to each subscriber URL.

```
WebhookDispatcher
  ├── Takes a list of subscriptions for an event
  ├── Sends each one concurrently (bounded by semaphore)
  ├── Signs each payload with HMAC-SHA256
  ├── Retries on network/5xx failures with exponential backoff + jitter
  └── Calls on_failure callback when all retries are exhausted
```

The concurrency limit prevents overloading slow subscriber endpoints.
The jitter on backoff prevents a thundering herd when many retries happen at the same time.

---

## Data Flow — Step by Step

Here is what happens every time a decorated endpoint receives a request:

```
1.  HTTP POST /orders hits your FastAPI route
        │
2.  Your business logic runs (creates the order)
        │
3.  Your function returns {"id": "ord_123", "status": "confirmed"}
        │
4.  FastAPI sends the HTTP response to the caller  ← customer gets their answer here
        │
5.  BackgroundTasks fires the emit task (non-blocking)
        │
6.  FasthooksContext is built from response + optional request data
        │
7.  transform(ctx) runs if provided, else response_payload is used directly
        │
8.  Backend.publish() is called with event_name, payload, subscribers
        │
9.  Dispatcher resolves subscribers (direct list or store query)
        │
10. HTTP POST is sent concurrently to each subscriber URL
        │
11. On success: done
    On 5xx / network error: retry with backoff
    On 4xx / all retries exhausted: on_failure callback fires
```

Steps 1–4 are on the critical path (the user waits).
Steps 5–11 happen in the background (no user waiting).

---

## The Sidecar Worker (Optional)

The `BackgroundTaskBackend` runs entirely inside your app process.

If you build a custom backend backed by a real queue (Redis, Kafka, SQS), you need a separate process to consume events from that queue and deliver them. That is the sidecar worker.

```
Your FastAPI app                  Sidecar Worker Process
      │                                   │
      │  publish → enqueue to Redis       │  consume ← dequeue from Redis
      │                                   │
                                          │  dispatch to subscriber URLs
                                          │
                                          │  ack event when done
```

You start it with:

```bash
fasthooks start \
  --backend-module myapp.backends:redis_backend \
  --store-module myapp.stores:sql_store \
  --signing-secret "secret"
```

This separation means your API process and delivery process can scale independently.

---

## Pluggability — Why Each Layer Is Separate

Fasthooks keeps each layer independent by design.

```
Layer        | Swappable Via        | Default
-------------|----------------------|---------------------------
Backend      | BaseBackend          | BackgroundTaskBackend
Store        | BaseStore            | None (direct list) or MemoryStore/SQLStore
Dispatcher   | Not swappable        | WebhookDispatcher (built-in)
```

You can use any combination:

- No store + direct subscribers: fastest, no DB needed.
- MemoryStore + BackgroundTaskBackend: local dev with subscription management.
- SQLStore + BackgroundTaskBackend: production with durable subscriptions.
- Custom queue backend + SQLStore: production with horizontal scale and sidecar workers.

---

## What Fasthooks Does NOT Do

Knowing the boundaries helps you design around them correctly.

| Not in Core | Where to Handle It |
|---|---|
| Subscription management API (CRUD endpoints) | Your app routes + a store |
| Event replay or history | Your queue backend |
| Exactly-once delivery | Your queue backend (e.g. Redis consumer groups) |
| Observability dashboards | External telemetry (OpenTelemetry, Prometheus) |
| Tenant subscription isolation | owner_id field + your query logic |

---

## Summary

| Concept | One-Line Explanation |
|---|---|
| `@hooks.hook` | Attaches webhook emission to any FastAPI route |
| `FasthooksContext` | The event snapshot passed to your transform function |
| `BaseBackend` | The interface for how events are published/consumed |
| `BackgroundTaskBackend` | The built-in backend — runs inside FastAPI, no extra process |
| `BaseStore` | The interface for subscription storage |
| `WebhookDispatcher` | The HTTP fan-out engine with retries and signing |
| Sidecar engine | A separate process for queue-backed backends |

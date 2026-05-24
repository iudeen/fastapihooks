# 03. Core API

## Fastapihooks
Main entry point that wires your backend, optional store, owner scope, and direct subscribers.

Constructor parameters:
- backend: BaseBackend implementation.
- store: optional store instance.
- owner_id: optional global owner scope.
- subscribers: optional event-to-subscriber map.

Lifecycle:
- aclose() closes backend resources.
- async context manager support is available via __aenter__/__aexit__.

## hook Decorator
`hook(event_name, include_headers=False, include_request=False, include_response=True, transform=None, owner_id_resolver=None)`

Behavior:
1. Calls original endpoint (sync or async).
2. Builds FastapihooksContext.
3. Resolves payload through optional transform.
4. Publishes using backend.publish(...).
5. Uses FastAPI BackgroundTasks when provided.

Important details:
- include_headers/include_request require request injection.
- owner_id can come from constructor, endpoint kwargs, or owner_id_resolver.
- If no BackgroundTasks instance is injected, emit path runs inline.

### `include_request=True` — Body Consumption Caveat

When FastAPI parses a route parameter as a Pydantic model (e.g. `body: OrderIn`), it reads
and decodes the request body before your handler runs. After that point `await request.body()`
returns empty bytes — Starlette does not buffer it a second time by default.

**`include_request=True` only works reliably when the raw `Request` object is injected and
the body is not also consumed by a Pydantic model parameter.**

Safe pattern — read the body yourself:
```python
@app.post("/orders")
@hooks.hook("order.created", include_request=True)
async def create_order(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()          # read once; Starlette caches it after this
    data = json.loads(body)
    return {"id": "ord_123", **data}
```

Unsafe pattern — Pydantic already consumed the body:
```python
@app.post("/orders")
@hooks.hook("order.created", include_request=True)   # request_payload will be b""
async def create_order(request: Request, body: OrderIn, background_tasks: BackgroundTasks):
    ...
```

If you only need request *headers*, use `include_headers=True` instead — that is always safe.

## FastapihooksContext
Fields:
- event_name
- owner_id
- timestamp
- headers
- request_payload
- response_payload

Use it for deterministic payload shaping and metadata-aware transforms.

## Error Surface
- Missing request while include_headers/include_request is enabled raises RuntimeError.
- `include_request=True` returns empty bytes if a Pydantic model parameter already consumed the body — see caveat above.
- Backend-specific delivery errors are handled by backend/dispatcher behavior.

# 03. Core API

## Fasthooks
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
2. Builds FasthooksContext.
3. Resolves payload through optional transform.
4. Publishes using backend.publish(...).
5. Uses FastAPI BackgroundTasks when provided.

Important details:
- include_headers/include_request require request injection.
- owner_id can come from constructor, endpoint kwargs, or owner_id_resolver.
- If no BackgroundTasks instance is injected, emit path runs inline.

## FasthooksContext
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
- Backend-specific delivery errors are handled by backend/dispatcher behavior.

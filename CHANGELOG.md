# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-05-25

### Added
- `BackgroundTaskBackend` — zero-dependency webhook emission via FastAPI `BackgroundTasks`.
- `WebhookDispatcher` — concurrent HTTP fan-out with HMAC-SHA256 signing, exponential-backoff retries, and a dead-letter callback.
- `InMemoryDeadLetterQueue` — drop-in `on_failure` handler that captures exhausted deliveries in memory.
- `MemoryStore` — in-process subscription store for development and testing.
- `SQLStore` — durable subscription store backed by SQLAlchemy 2.x (PostgreSQL, MySQL, SQLite).
- `FastapihooksContext` — Pydantic model carrying event name, owner ID, timestamp, headers, request body, and response payload.
- `@hooks.hook` decorator — attaches webhook emission to any FastAPI route with optional transform, header capture, and request body capture.
- `aclose()` and async context manager support on `Fastapihooks` and `BackgroundTaskBackend`.
- `py.typed` PEP 561 marker — full type-checking support.
- Reference examples: Redis Streams backend (`examples/redis_stream_backend.py`), MongoDB store (`examples/mongodb_store.py`).
- Full documentation: quickstart, core API, backends, stores, worker engine, security/reliability, architecture deep-dive, extension guide, roadmap.

### Notes
- Signing secret is optional. When omitted, the `X-Fastapihooks-Signature` header is not sent.
- `include_request=True` returns empty bytes if a Pydantic model parameter already consumed the request body. See [Core API docs](docs/03-core-api.md) for the safe usage pattern.

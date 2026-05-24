# 09. Roadmap

## Current State
- Built-in backend: BackgroundTaskBackend.
- Built-in stores: MemoryStore and SQLStore.
- Dispatcher supports retries, backoff, HMAC signing, and dead-letter callback.
- Reference examples: Redis Streams backend (`examples/redis_stream_backend.py`), MongoDB store (`examples/mongodb_store.py`).

## Planned Integration Areas
- Publish reference examples as standalone installable packages.
- Telemetry integrations (OpenTelemetry, Prometheus, Logfire).
- Additional store adapters (DynamoDB, Redis).

## Help Wanted
1. Publish a custom backend reference package.
2. Publish a production dead-letter adapter package.
3. Add end-to-end examples for queue-backed worker mode.
4. Add observability docs with concrete exporter setup.

## Compatibility Strategy
- Keep core API stable.
- Add functionality through extension points.
- Keep optional integrations out of default dependency graph.

## Contribution Direction
Good contributions:
- Better extension docs and examples.
- Hardening for retries/failure callbacks.
- Tests around contracts and API behavior.

Avoid by default:
- Bundling heavy transport dependencies into core.
- Changing backend/store contracts without migration notes.

# Fasthooks Documentation 
Welcome to documentation for Fasthooks.

## Navigation
- [01-overview.md](01-overview.md) - Product overview and mental model.
- [02-quickstart.md](02-quickstart.md) - Installation and runnable setup.
- [03-core-api.md](03-core-api.md) - Core classes, context, and hook behavior.
- [04-backends.md](04-backends.md) - Built-in backend and custom backend contract.
- [05-stores.md](05-stores.md) - Subscription stores and extension guidance.
- [06-worker-engine.md](06-worker-engine.md) - Sidecar worker engine and CLI.
- [07-security-reliability.md](07-security-reliability.md) - Signatures, retries, and failure handling.
- [08-agent-playbook.md](08-agent-playbook.md) - Agent-agnostic repo workflow.
- [09-roadmap.md](09-roadmap.md) - Planned integrations and recommended milestones.
- [10-architecture.md](10-architecture.md) - Deep-dive on how Fasthooks works internally (newbie-friendly).
- [11-extending.md](11-extending.md) - How to build and package custom backends and stores.

## Documentation Scope
This documentation tracks shipped behavior in the repository while preserving the long-term product vision.

## Fast Path
1. Read [02-quickstart.md](02-quickstart.md).
2. If you need custom transport, jump to [04-backends.md](04-backends.md).
3. If you need a queue sidecar, read [06-worker-engine.md](06-worker-engine.md).

## Reference Examples
Ready-to-use implementations in the `examples/` folder:

- **Redis Streams backend** — horizontal scale with consumer groups (`examples/redis_stream_backend.py`)
- **MongoDB store** — durable subscriptions via Motor (`examples/mongodb_store.py`)

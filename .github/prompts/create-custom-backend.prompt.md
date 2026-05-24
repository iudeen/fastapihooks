---
mode: "ask"
description: "Create a custom fasthooks backend by subclassing BaseBackend (for Redis, Kafka, SQS, or any queue)."
---

Create a production-ready custom backend for this repository by subclassing BaseBackend.

Requirements:
- Keep core policy intact: do not add this backend as a built-in export by default.
- Implement publish(event_name, payload, owner_id, subscribers), consume(), and ack(event_id).
- Add clear docstrings and type hints.
- Include a minimal usage example showing Fasthooks initialization with the custom backend.
- Keep changes scoped and backward compatible.

Validation:
- Run diagnostics on edited files.
- Run at least one import smoke test for touched modules.
- Summarize tradeoffs and operational assumptions.

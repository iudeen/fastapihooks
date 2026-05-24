# 06. Worker Engine

## Why It Exists
The sidecar engine is for queue-backed custom backends that expose consume and ack behavior.

BackgroundTaskBackend does not use this loop.

## FastapihooksEngine Flow
1. Consume event from backend.
2. Dispatch to matching subscribers.
3. Acknowledge via backend.ack(event.id).
4. Continue processing even when one event fails.

## CLI
Entry point command:
```bash
fastapihooks start --backend-module myapp.backends:backend --store-module myapp.stores:store --signing-secret "secret"
```

Main options:
- --backend-module module_path:instance
- --store-module module_path:instance
- --signing-secret value
- --max-concurrency integer
- --log-level level

## Import Resolution Rules
Module path format:
- module.submodule:instance_name

Failure modes:
- Invalid path format raises import error.
- Missing module or attribute exits with code 1.

## Operational Notes
- Keep backend.consume as an async iterator.
- Ensure event objects include id, event_name, payload fields.
- Tune max_concurrency based on downstream capacity.

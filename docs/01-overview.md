# 01. Overview

## What Fasthooks Is
Fasthooks is a webhook framework for FastAPI applications that focuses on low-latency API responses and pluggable delivery architecture.

Core idea:
1. Your API route runs business logic.
2. Fasthooks captures event context.
3. Webhook delivery is offloaded through a backend path.

## Design Principles
- Keep core lightweight.
- Ship only one backend by default: BackgroundTaskBackend.
- Allow custom transports through BaseBackend.
- Keep subscription storage abstract via BaseStore.

## Components
- Core decorator and event context.
- Backend abstraction and default implementation.
- Subscription stores.
- Dispatcher for fan-out delivery with retries.
- Optional sidecar engine for queue-style backends.

## Mental Model
Use Fasthooks as a pipeline:
- Emit phase in your API process.
- Resolve subscribers from direct list or store.
- Deliver to endpoints with signing/auth/retry behavior.

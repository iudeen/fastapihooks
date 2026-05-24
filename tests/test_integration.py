"""Integration tests: real FastAPI app + fastapihooks decorator end-to-end."""

import json
from contextlib import asynccontextmanager

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.testclient import TestClient

from fastapihooks import Fastapihooks, InMemoryDeadLetterQueue
from fastapihooks.backends import BackgroundTaskBackend
from fastapihooks.stores import MemoryStore, WebhookSubscription
from fastapihooks.worker.dispatcher import WebhookDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_app(hooks: Fastapihooks) -> FastAPI:
    """Build a minimal FastAPI app wired to the given Fastapihooks instance."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with hooks:
            yield

    app = FastAPI(lifespan=lifespan)

    @app.post("/orders")
    @hooks.hook("order.created")
    async def create_order(background_tasks: BackgroundTasks):
        return {"id": "ord_123", "status": "confirmed"}

    return app


def recorded_backend(signing_secret: str = "test-secret", store=None):
    """BackgroundTaskBackend whose HTTP client records outbound webhook requests."""
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    backend = BackgroundTaskBackend(store=store, signing_secret=signing_secret)
    backend.dispatcher = WebhookDispatcher(
        store=store,
        signing_secret=signing_secret,
        client=client,
        max_retries=0,
    )
    return backend, received


# ---------------------------------------------------------------------------
# Basic decorator behaviour
# ---------------------------------------------------------------------------

class TestBasicHook:
    def test_endpoint_returns_response(self):
        backend, _ = recorded_backend()
        hooks = Fastapihooks(backend=backend)
        app = make_app(hooks)

        with TestClient(app) as client:
            response = client.post("/orders")

        assert response.status_code == 200
        assert response.json() == {"id": "ord_123", "status": "confirmed"}

    def test_webhook_delivered_to_direct_subscriber(self):
        sub = WebhookSubscription(event_name="order.created", target_url="https://recv.example.com/hook")
        backend, received = recorded_backend()
        hooks = Fastapihooks(backend=backend, subscribers={"order.created": [sub]})
        app = make_app(hooks)

        with TestClient(app) as client:
            client.post("/orders")

        assert len(received) == 1
        assert str(received[0].url) == "https://recv.example.com/hook"

    def test_webhook_payload_matches_response(self):
        sub = WebhookSubscription(event_name="order.created", target_url="https://recv.example.com/hook")
        backend, received = recorded_backend()
        hooks = Fastapihooks(backend=backend, subscribers={"order.created": [sub]})
        app = make_app(hooks)

        with TestClient(app) as client:
            client.post("/orders")

        body = json.loads(received[0].content)
        assert body == {"id": "ord_123", "status": "confirmed"}

    def test_no_subscriber_no_delivery(self):
        backend, received = recorded_backend()
        hooks = Fastapihooks(backend=backend)
        app = make_app(hooks)

        with TestClient(app) as client:
            client.post("/orders")

        assert received == []


# ---------------------------------------------------------------------------
# HMAC signature
# ---------------------------------------------------------------------------

class TestSignature:
    def test_signature_header_present_when_secret_set(self):
        import hashlib
        import hmac as hmac_mod

        sub = WebhookSubscription(event_name="order.created", target_url="https://recv.example.com/hook")
        secret = "my-signing-secret"
        backend, received = recorded_backend(signing_secret=secret)
        hooks = Fastapihooks(backend=backend, subscribers={"order.created": [sub]})
        app = make_app(hooks)

        with TestClient(app) as client:
            client.post("/orders")

        req = received[0]
        assert "x-fastapihooks-signature" in req.headers
        sig_header = req.headers["x-fastapihooks-signature"]
        assert sig_header.startswith("sha256=")

        expected = hmac_mod.new(secret.encode(), req.content, hashlib.sha256).hexdigest()
        assert sig_header == f"sha256={expected}"

    def test_event_name_header_present(self):
        sub = WebhookSubscription(event_name="order.created", target_url="https://recv.example.com/hook")
        backend, received = recorded_backend()
        hooks = Fastapihooks(backend=backend, subscribers={"order.created": [sub]})
        app = make_app(hooks)

        with TestClient(app) as client:
            client.post("/orders")

        assert received[0].headers["x-fastapihooks-event"] == "order.created"


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

class TestTransform:
    def test_transform_shapes_payload(self):
        from fastapihooks import FastapihooksContext

        def transformer(ctx: FastapihooksContext):
            return {"event": ctx.event_name, "order_id": ctx.response_payload["id"]}

        sub = WebhookSubscription(event_name="order.created", target_url="https://recv.example.com/hook")
        backend, received = recorded_backend()
        hooks = Fastapihooks(backend=backend, subscribers={"order.created": [sub]})

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with hooks:
                yield

        app = FastAPI(lifespan=lifespan)

        @app.post("/orders")
        @hooks.hook("order.created", transform=transformer)
        async def create_order(background_tasks: BackgroundTasks):
            return {"id": "ord_123", "status": "confirmed"}

        with TestClient(app) as client:
            client.post("/orders")

        body = json.loads(received[0].content)
        assert body == {"event": "order.created", "order_id": "ord_123"}


# ---------------------------------------------------------------------------
# Store-based subscriptions
# ---------------------------------------------------------------------------

class TestStoreIntegration:
    def test_subscriptions_from_memory_store_are_delivered(self):
        received: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            received.append(request)
            return httpx.Response(200)

        store = MemoryStore()
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        backend = BackgroundTaskBackend(store=store, signing_secret="secret")
        backend.dispatcher = WebhookDispatcher(store=store, signing_secret="secret", client=client, max_retries=0)
        hooks = Fastapihooks(backend=backend)
        app = make_app(hooks)

        import asyncio
        asyncio.run(store.add_subscription("order.created", "https://store-sub.example.com/hook"))

        with TestClient(app) as client_app:
            client_app.post("/orders")

        assert len(received) == 1
        assert str(received[0].url) == "https://store-sub.example.com/hook"

    def test_multiple_store_subscribers_all_receive_event(self):
        received: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            received.append(request)
            return httpx.Response(200)

        store = MemoryStore()
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        backend = BackgroundTaskBackend(store=store, signing_secret="secret")
        backend.dispatcher = WebhookDispatcher(store=store, signing_secret="secret", client=http_client, max_retries=0)
        hooks = Fastapihooks(backend=backend)
        app = make_app(hooks)

        import asyncio
        asyncio.run(store.add_subscription("order.created", "https://a.example.com/hook"))
        asyncio.run(store.add_subscription("order.created", "https://b.example.com/hook"))

        with TestClient(app) as client_app:
            client_app.post("/orders")

        assert len(received) == 2
        urls = {str(r.url) for r in received}
        assert urls == {"https://a.example.com/hook", "https://b.example.com/hook"}


# ---------------------------------------------------------------------------
# Dead-letter queue integration
# ---------------------------------------------------------------------------

class TestDeadLetterIntegration:
    def test_failed_delivery_lands_in_dlq(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        sub = WebhookSubscription(event_name="order.created", target_url="https://failing.example.com/hook")
        dlq = InMemoryDeadLetterQueue()
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        backend = BackgroundTaskBackend(signing_secret="secret")
        backend.dispatcher = WebhookDispatcher(
            signing_secret="secret",
            client=client,
            max_retries=0,
            on_failure=dlq,
        )
        hooks = Fastapihooks(backend=backend, subscribers={"order.created": [sub]})
        app = make_app(hooks)

        with TestClient(app) as client_app:
            client_app.post("/orders")

        assert len(dlq) == 1
        assert dlq.entries[0].subscription.target_url == "https://failing.example.com/hook"


# ---------------------------------------------------------------------------
# Sync endpoint
# ---------------------------------------------------------------------------

class TestSyncEndpoint:
    def test_sync_endpoint_is_wrapped_correctly(self):
        sub = WebhookSubscription(event_name="item.created", target_url="https://recv.example.com/hook")
        backend, received = recorded_backend()
        hooks = Fastapihooks(backend=backend, subscribers={"item.created": [sub]})

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with hooks:
                yield

        app = FastAPI(lifespan=lifespan)

        @app.post("/items")
        @hooks.hook("item.created")
        def create_item(background_tasks: BackgroundTasks):  # sync, not async
            return {"id": "item_456"}

        with TestClient(app) as client:
            response = client.post("/items")

        assert response.status_code == 200
        assert response.json() == {"id": "item_456"}
        assert len(received) == 1
        body = json.loads(received[0].content)
        assert body == {"id": "item_456"}


# ---------------------------------------------------------------------------
# include_headers / include_request
# ---------------------------------------------------------------------------

class TestIncludeOptions:
    def test_include_headers_populates_ctx(self):
        from fastapihooks import FastapihooksContext

        captured_ctx: list[FastapihooksContext] = []

        def transformer(ctx: FastapihooksContext):
            captured_ctx.append(ctx)
            return ctx.response_payload

        sub = WebhookSubscription(event_name="order.created", target_url="https://recv.example.com/hook")
        backend, received = recorded_backend()
        hooks = Fastapihooks(backend=backend, subscribers={"order.created": [sub]})

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with hooks:
                yield

        app = FastAPI(lifespan=lifespan)

        @app.post("/orders")
        @hooks.hook("order.created", include_headers=True, transform=transformer)
        async def create_order(request: Request, background_tasks: BackgroundTasks):
            return {"id": "ord_123"}

        with TestClient(app) as client:
            client.post("/orders", headers={"x-custom": "my-value"})

        assert captured_ctx[0].headers is not None
        assert "x-custom" in captured_ctx[0].headers

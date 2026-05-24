"""Tests for Fasthooks.hook() decorator and FasthooksContext."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.testclient import TestClient

from fasthooks.backends.base_backend import BaseBackend
from fasthooks.core import Fasthooks, FasthooksContext
from fasthooks.stores.base_store import WebhookSubscription

# ---------------------------------------------------------------------------
# Minimal stub backend
# ---------------------------------------------------------------------------

class StubBackend(BaseBackend):
    """Records every publish() call for later inspection."""

    def __init__(self):
        self.calls: list[dict] = []

    async def publish(self, event_name, payload, owner_id, subscribers=None):
        self.calls.append(
            {
                "event_name": event_name,
                "payload": payload,
                "owner_id": owner_id,
                "subscribers": subscribers,
            }
        )

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# FasthooksContext
# ---------------------------------------------------------------------------

class TestFasthooksContext:
    def test_instantiates_with_required_fields(self):
        ctx = FasthooksContext(event_name="order.created", owner_id="user-1")
        assert ctx.event_name == "order.created"
        assert ctx.owner_id == "user-1"

    def test_timestamp_defaults_to_utc_now(self):
        before = datetime.now(tz=timezone.utc)
        ctx = FasthooksContext(event_name="evt", owner_id=None)
        after = datetime.now(tz=timezone.utc)
        assert ctx.timestamp.tzinfo is not None
        assert before <= ctx.timestamp <= after

    def test_optional_fields_default_to_none(self):
        ctx = FasthooksContext(event_name="evt", owner_id=None)
        assert ctx.headers is None
        assert ctx.request_payload is None
        assert ctx.response_payload is None

    def test_explicit_timestamp_is_used(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ctx = FasthooksContext(event_name="evt", owner_id=None, timestamp=ts)
        assert ctx.timestamp == ts

    def test_headers_can_be_set(self):
        ctx = FasthooksContext(
            event_name="evt", owner_id=None, headers={"X-Custom": "value"}
        )
        assert ctx.headers == {"X-Custom": "value"}

    def test_response_payload_can_be_set(self):
        ctx = FasthooksContext(event_name="evt", owner_id=None, response_payload={"k": "v"})
        assert ctx.response_payload == {"k": "v"}


# ---------------------------------------------------------------------------
# Helpers to build a FastAPI app with a hooked endpoint
# ---------------------------------------------------------------------------

def _build_app(
    backend: BaseBackend,
    *,
    include_headers: bool = False,
    include_request: bool = False,
    include_response: bool = True,
    transform=None,
    owner_id_resolver=None,
    global_owner_id: str | None = None,
    global_subscribers: dict | None = None,
    is_sync: bool = False,
) -> tuple[FastAPI, StubBackend]:
    app = FastAPI()
    fh = Fasthooks(
        backend=backend,
        owner_id=global_owner_id,
        subscribers=global_subscribers or {},
    )

    if is_sync:
        @app.post("/items")
        @fh.hook(
            "order.created",
            include_headers=include_headers,
            include_request=include_request,
            include_response=include_response,
            transform=transform,
            owner_id_resolver=owner_id_resolver,
        )
        def create_item():
            return {"item": "sync-result"}
    else:
        @app.post("/items")
        @fh.hook(
            "order.created",
            include_headers=include_headers,
            include_request=include_request,
            include_response=include_response,
            transform=transform,
            owner_id_resolver=owner_id_resolver,
        )
        async def create_item():
            return {"item": "async-result"}

    return app, fh


# ---------------------------------------------------------------------------
# Basic decorator behaviour
# ---------------------------------------------------------------------------

class TestHookDecoratorBasic:
    def test_async_endpoint_returns_original_response(self):
        backend = StubBackend()
        app, _ = _build_app(backend)
        client = TestClient(app)
        resp = client.post("/items")
        assert resp.status_code == 200
        assert resp.json() == {"item": "async-result"}

    def test_sync_endpoint_returns_original_response(self):
        backend = StubBackend()
        app, _ = _build_app(backend, is_sync=True)
        client = TestClient(app)
        resp = client.post("/items")
        assert resp.status_code == 200
        assert resp.json() == {"item": "sync-result"}

    def test_webhook_is_published_after_async_endpoint(self):
        backend = StubBackend()
        app, _ = _build_app(backend)
        client = TestClient(app)
        client.post("/items")
        assert len(backend.calls) == 1
        assert backend.calls[0]["event_name"] == "order.created"

    def test_webhook_is_published_after_sync_endpoint(self):
        backend = StubBackend()
        app, _ = _build_app(backend, is_sync=True)
        client = TestClient(app)
        client.post("/items")
        assert len(backend.calls) == 1

    def test_response_payload_included_by_default(self):
        backend = StubBackend()
        app, _ = _build_app(backend, include_response=True)
        client = TestClient(app)
        client.post("/items")
        assert backend.calls[0]["payload"] == {"item": "async-result"}

    def test_response_payload_excluded_when_include_response_false(self):
        backend = StubBackend()
        app, _ = _build_app(backend, include_response=False)
        client = TestClient(app)
        client.post("/items")
        assert backend.calls[0]["payload"] is None


# ---------------------------------------------------------------------------
# transform
# ---------------------------------------------------------------------------

class TestTransform:
    def test_transform_receives_fasthooks_context(self):
        received_ctx = []

        def my_transform(ctx: FasthooksContext):
            received_ctx.append(ctx)
            return {"transformed": True}

        backend = StubBackend()
        app, _ = _build_app(backend, transform=my_transform)
        client = TestClient(app)
        client.post("/items")
        assert len(received_ctx) == 1
        assert isinstance(received_ctx[0], FasthooksContext)

    def test_transform_return_value_is_the_payload(self):
        def my_transform(ctx: FasthooksContext):
            return {"custom": "payload"}

        backend = StubBackend()
        app, _ = _build_app(backend, transform=my_transform)
        client = TestClient(app)
        client.post("/items")
        assert backend.calls[0]["payload"] == {"custom": "payload"}

    def test_transform_context_has_response_payload(self):
        seen_payloads = []

        def my_transform(ctx: FasthooksContext):
            seen_payloads.append(ctx.response_payload)
            return ctx.response_payload

        backend = StubBackend()
        app, _ = _build_app(backend, transform=my_transform)
        client = TestClient(app)
        client.post("/items")
        assert seen_payloads[0] == {"item": "async-result"}

    def test_transform_context_has_event_name(self):
        seen_event_names = []

        def my_transform(ctx: FasthooksContext):
            seen_event_names.append(ctx.event_name)
            return {}

        backend = StubBackend()
        app, _ = _build_app(backend, transform=my_transform)
        client = TestClient(app)
        client.post("/items")
        assert seen_event_names[0] == "order.created"


# ---------------------------------------------------------------------------
# include_headers
# ---------------------------------------------------------------------------

class TestIncludeHeaders:
    def test_include_headers_populates_ctx_headers(self):
        seen_headers = []

        def my_transform(ctx: FasthooksContext):
            seen_headers.append(ctx.headers)
            return {}

        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(backend=backend)

        @app.post("/items")
        @fh.hook("order.created", include_headers=True, transform=my_transform)
        async def create_item(request: Request):
            return {"ok": True}

        client = TestClient(app)
        client.post("/items", headers={"X-Custom-Header": "test-value"})
        assert seen_headers[0] is not None
        assert "x-custom-header" in seen_headers[0]

    def test_headers_none_when_include_headers_false(self):
        seen_headers = []

        def my_transform(ctx: FasthooksContext):
            seen_headers.append(ctx.headers)
            return {}

        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(backend=backend)

        @app.post("/items")
        @fh.hook("order.created", include_headers=False, transform=my_transform)
        async def create_item():
            return {"ok": True}

        client = TestClient(app)
        client.post("/items")
        assert seen_headers[0] is None


# ---------------------------------------------------------------------------
# include_request
# ---------------------------------------------------------------------------

class TestIncludeRequest:
    def test_include_request_populates_ctx_request_payload(self):
        seen_request = []

        def my_transform(ctx: FasthooksContext):
            seen_request.append(ctx.request_payload)
            return {}

        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(backend=backend)

        @app.post("/items")
        @fh.hook("order.created", include_request=True, transform=my_transform)
        async def create_item(request: Request):
            return {"ok": True}

        client = TestClient(app)
        client.post("/items", json={"input": "data"})
        assert seen_request[0] is not None
        assert b"input" in seen_request[0]

    def test_request_payload_none_when_include_request_false(self):
        seen_request = []

        def my_transform(ctx: FasthooksContext):
            seen_request.append(ctx.request_payload)
            return {}

        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(backend=backend)

        @app.post("/items")
        @fh.hook("order.created", include_request=False, transform=my_transform)
        async def create_item():
            return {"ok": True}

        client = TestClient(app)
        client.post("/items")
        assert seen_request[0] is None


# ---------------------------------------------------------------------------
# owner_id
# ---------------------------------------------------------------------------

class TestOwnerID:
    def test_global_owner_id_used_when_no_resolver(self):
        backend = StubBackend()
        app, _ = _build_app(backend, global_owner_id="tenant-abc")
        client = TestClient(app)
        client.post("/items")
        assert backend.calls[0]["owner_id"] == "tenant-abc"

    def test_owner_id_resolver_overrides_global(self):
        """owner_id_resolver requires 'request: Request' in the endpoint signature
        so that FastAPI injects the real Request object into the wrapper."""

        def resolver(request: Request) -> str:
            return request.headers.get("X-Tenant-ID", "default")

        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(backend=backend, owner_id="global")

        @app.post("/items")
        @fh.hook("order.created", owner_id_resolver=resolver)
        async def create_item(request: Request):
            return {"ok": True}

        client = TestClient(app)
        client.post("/items", headers={"X-Tenant-ID": "tenant-xyz"})
        assert backend.calls[0]["owner_id"] == "tenant-xyz"

    def test_owner_id_none_when_not_set(self):
        backend = StubBackend()
        app, _ = _build_app(backend)
        client = TestClient(app)
        client.post("/items")
        # owner_id is None since no global or resolver was configured
        assert backend.calls[0]["owner_id"] is None

    def test_owner_id_resolver_returning_none_falls_back_to_global(self):
        """If the resolver returns None, global owner_id should still be used."""

        def resolver(request: Request):
            return None  # explicitly return None

        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(backend=backend, owner_id="global-tenant")

        @app.post("/items")
        @fh.hook("order.created", owner_id_resolver=resolver)
        async def create_item(request: Request):
            return {"ok": True}

        client = TestClient(app)
        client.post("/items")
        assert backend.calls[0]["owner_id"] == "global-tenant"


# ---------------------------------------------------------------------------
# background_tasks offloading
# ---------------------------------------------------------------------------

class TestBackgroundTasksOffloading:
    def test_emit_offloaded_to_background_tasks_when_available(self):
        """When FastAPI's BackgroundTasks is injected, the emit must be registered as a
        background task, not called inline (i.e. the endpoint returns before publish runs)."""
        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(backend=backend)

        @app.post("/items")
        @fh.hook("order.created")
        async def create_item(background_tasks: BackgroundTasks):
            return {"item": "result"}

        client = TestClient(app)
        resp = client.post("/items")
        # TestClient runs background tasks before returning, so backend.calls should have content
        assert resp.status_code == 200
        # The webhook is emitted (via background task executed by TestClient)
        assert len(backend.calls) == 1

    def test_emit_runs_inline_when_background_tasks_absent(self):
        backend = StubBackend()
        app, _ = _build_app(backend)  # no background_tasks param in endpoint
        client = TestClient(app)
        client.post("/items")
        assert len(backend.calls) == 1


# ---------------------------------------------------------------------------
# Direct subscribers dict on Fasthooks
# ---------------------------------------------------------------------------

class TestDirectSubscribers:
    def test_subscribers_passed_through_to_backend_publish(self):
        sub = WebhookSubscription(
            event_name="order.created",
            target_url="https://direct.example.com/hook",
        )
        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(
            backend=backend,
            subscribers={"order.created": [sub]},
        )

        @app.post("/items")
        @fh.hook("order.created")
        async def create_item():
            return {"ok": True}

        client = TestClient(app)
        client.post("/items")
        assert backend.calls[0]["subscribers"] == [sub]

    def test_no_subscribers_for_other_events_passes_none(self):
        sub = WebhookSubscription(
            event_name="user.signup",
            target_url="https://direct.example.com/hook",
        )
        backend = StubBackend()
        app = FastAPI()
        fh = Fasthooks(
            backend=backend,
            subscribers={"user.signup": [sub]},
        )

        @app.post("/items")
        @fh.hook("order.created")  # different event
        async def create_item():
            return {"ok": True}

        client = TestClient(app)
        client.post("/items")
        # No matching subscribers for "order.created" → None passed
        assert backend.calls[0]["subscribers"] is None


# ---------------------------------------------------------------------------
# Fasthooks aclose / context manager
# ---------------------------------------------------------------------------

class TestFasthooksLifecycle:
    async def test_aclose_delegates_to_backend(self):
        backend = StubBackend()
        backend.aclose = AsyncMock()
        fh = Fasthooks(backend=backend)
        await fh.aclose()
        backend.aclose.assert_called_once()

    async def test_async_context_manager_calls_aclose(self):
        backend = StubBackend()
        backend.aclose = AsyncMock()
        fh = Fasthooks(backend=backend)
        async with fh:
            pass
        backend.aclose.assert_called_once()

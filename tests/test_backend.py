"""Tests for BackgroundTaskBackend."""

from unittest.mock import AsyncMock

from fastapihooks.backends.background_task_backend import BackgroundTaskBackend
from fastapihooks.stores.base_store import WebhookSubscription
from fastapihooks.stores.memory_store import MemoryStore
from fastapihooks.worker.dispatcher import WebhookDispatcher


def _make_sub(url: str = "https://target.example.com/hook") -> WebhookSubscription:
    return WebhookSubscription(event_name="order.created", target_url=url)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_dispatcher_created_at_init(self):
        backend = BackgroundTaskBackend()
        assert backend.dispatcher is not None
        assert isinstance(backend.dispatcher, WebhookDispatcher)

    def test_dispatcher_not_recreated_on_access(self):
        backend = BackgroundTaskBackend()
        d1 = backend.dispatcher
        d2 = backend.dispatcher
        assert d1 is d2

    def test_store_forwarded_to_dispatcher(self):
        store = MemoryStore()
        backend = BackgroundTaskBackend(store=store)
        assert backend.dispatcher.store is store

    def test_signing_secret_forwarded_to_dispatcher(self):
        backend = BackgroundTaskBackend(signing_secret="my-secret")
        # The dispatcher encodes the secret to bytes
        assert backend.dispatcher.secret == b"my-secret"


# ---------------------------------------------------------------------------
# publish with explicit subscribers
# ---------------------------------------------------------------------------

class TestPublishWithSubscribers:
    async def test_calls_broadcast_to_subscribers_when_subscribers_provided(self):
        backend = BackgroundTaskBackend()
        backend.dispatcher.broadcast_to_subscribers = AsyncMock()
        backend.dispatcher.broadcast = AsyncMock()

        subs = [_make_sub()]
        await backend.publish(
            event_name="order.created",
            payload={"order": 1},
            owner_id="user-1",
            subscribers=subs,
        )
        backend.dispatcher.broadcast_to_subscribers.assert_called_once_with(
            payload={"order": 1}, subscribers=subs
        )

    async def test_does_not_call_broadcast_when_only_subscribers_provided_and_no_store(self):
        backend = BackgroundTaskBackend()  # no store
        backend.dispatcher.broadcast_to_subscribers = AsyncMock()
        backend.dispatcher.broadcast = AsyncMock()

        await backend.publish(
            event_name="order.created",
            payload={"order": 1},
            owner_id="user-1",
            subscribers=[_make_sub()],
        )
        backend.dispatcher.broadcast.assert_not_called()

    async def test_empty_subscribers_skips_broadcast_to_subscribers(self):
        backend = BackgroundTaskBackend()
        backend.dispatcher.broadcast_to_subscribers = AsyncMock()
        backend.dispatcher.broadcast = AsyncMock()

        await backend.publish(
            event_name="order.created",
            payload={},
            owner_id=None,
            subscribers=[],  # empty list → falsy
        )
        backend.dispatcher.broadcast_to_subscribers.assert_not_called()

    async def test_none_subscribers_skips_broadcast_to_subscribers(self):
        backend = BackgroundTaskBackend()
        backend.dispatcher.broadcast_to_subscribers = AsyncMock()
        backend.dispatcher.broadcast = AsyncMock()

        await backend.publish(
            event_name="order.created",
            payload={},
            owner_id=None,
            subscribers=None,
        )
        backend.dispatcher.broadcast_to_subscribers.assert_not_called()


# ---------------------------------------------------------------------------
# publish with store
# ---------------------------------------------------------------------------

class TestPublishWithStore:
    async def test_calls_broadcast_when_store_is_set(self):
        store = MemoryStore()
        backend = BackgroundTaskBackend(store=store)
        backend.dispatcher.broadcast = AsyncMock()
        backend.dispatcher.broadcast_to_subscribers = AsyncMock()

        await backend.publish(
            event_name="order.created",
            payload={"order": 1},
            owner_id="user-1",
        )
        backend.dispatcher.broadcast.assert_called_once_with("order.created", {"order": 1})

    async def test_does_not_call_broadcast_without_store(self):
        backend = BackgroundTaskBackend()  # no store → dispatcher.store is None
        backend.dispatcher.broadcast = AsyncMock()
        backend.dispatcher.broadcast_to_subscribers = AsyncMock()

        await backend.publish(
            event_name="order.created",
            payload={},
            owner_id=None,
        )
        backend.dispatcher.broadcast.assert_not_called()

    async def test_calls_both_when_subscribers_and_store_both_present(self):
        """When both subscribers and a store are provided, both delivery paths fire."""
        store = MemoryStore()
        backend = BackgroundTaskBackend(store=store)
        backend.dispatcher.broadcast = AsyncMock()
        backend.dispatcher.broadcast_to_subscribers = AsyncMock()

        subs = [_make_sub()]
        await backend.publish(
            event_name="order.created",
            payload={"order": 1},
            owner_id="user-1",
            subscribers=subs,
        )
        backend.dispatcher.broadcast_to_subscribers.assert_called_once()
        backend.dispatcher.broadcast.assert_called_once()


# ---------------------------------------------------------------------------
# aclose
# ---------------------------------------------------------------------------

class TestAclose:
    async def test_aclose_propagates_to_dispatcher(self):
        backend = BackgroundTaskBackend()
        backend.dispatcher.aclose = AsyncMock()
        await backend.aclose()
        backend.dispatcher.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------

class TestAsyncContextManager:
    async def test_aenter_returns_backend(self):
        backend = BackgroundTaskBackend()
        result = await backend.__aenter__()
        assert result is backend

    async def test_aexit_calls_aclose(self):
        backend = BackgroundTaskBackend()
        backend.dispatcher.aclose = AsyncMock()
        async with backend:
            pass
        backend.dispatcher.aclose.assert_called_once()

    async def test_context_manager_usage(self):
        """Full async-with block should not raise."""
        backend = BackgroundTaskBackend()
        backend.dispatcher.aclose = AsyncMock()
        async with backend as b:
            assert b is backend
        backend.dispatcher.aclose.assert_called_once()

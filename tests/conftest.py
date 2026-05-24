"""Shared fixtures for fastapihooks test suite."""


import httpx
import pytest

from fastapihooks.stores.base_store import WebhookSubscription
from fastapihooks.stores.memory_store import MemoryStore
from fastapihooks.worker.dispatcher import WebhookDispatcher

# ---------------------------------------------------------------------------
# HTTP mock helpers
# ---------------------------------------------------------------------------

def make_mock_transport(status_code: int = 200):
    """Return an httpx.MockTransport that always responds with the given status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    return httpx.MockTransport(handler)


def make_recording_transport(recorded: list, status_code: int = 200):
    """Return an httpx.MockTransport that records every request it receives."""

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(status_code)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Dispatcher fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def recorded_requests() -> list:
    """Mutable list populated by the recording transport fixture."""
    return []


@pytest.fixture()
def mock_http_client(recorded_requests):
    """httpx.AsyncClient backed by a recording MockTransport."""
    transport = make_recording_transport(recorded_requests)
    return httpx.AsyncClient(transport=transport)


@pytest.fixture()
def dispatcher(mock_http_client):
    """WebhookDispatcher with a mock HTTP client and no store."""
    return WebhookDispatcher(client=mock_http_client)


@pytest.fixture()
def signing_secret() -> str:
    return "super-secret-key"


@pytest.fixture()
def signing_dispatcher(mock_http_client, signing_secret):
    """WebhookDispatcher with HMAC signing enabled."""
    return WebhookDispatcher(client=mock_http_client, signing_secret=signing_secret)


# ---------------------------------------------------------------------------
# Store fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
async def populated_store() -> MemoryStore:
    """MemoryStore pre-loaded with three subscriptions across two events."""
    store = MemoryStore()
    await store.add_subscription(
        event_name="order.created",
        target_url="https://subscriber-a.example.com/hooks",
    )
    await store.add_subscription(
        event_name="order.created",
        target_url="https://subscriber-b.example.com/hooks",
    )
    await store.add_subscription(
        event_name="user.signup",
        target_url="https://subscriber-c.example.com/hooks",
    )
    return store


# ---------------------------------------------------------------------------
# WebhookSubscription helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def subscription_a() -> WebhookSubscription:
    return WebhookSubscription(
        event_name="order.created",
        target_url="https://subscriber-a.example.com/hooks",
    )


@pytest.fixture()
def bearer_subscription() -> WebhookSubscription:
    return WebhookSubscription(
        event_name="order.created",
        target_url="https://subscriber-b.example.com/hooks",
        auth_type="bearer",
        auth_value="my-token",
    )

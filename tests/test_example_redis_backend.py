"""Tests for examples/redis_stream_backend.py.

redis[asyncio] is not installed in the dev environment, so we inject a mock
into sys.modules before importing the example. The tests verify contract
behaviour (XADD / XREADGROUP / XACK calls and response handling) without
a real Redis server.
"""

import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Inject redis mock BEFORE the example module is imported so the
# try/except ImportError inside it succeeds with our stub.
# ---------------------------------------------------------------------------
class _FakeResponseError(Exception):
    """Stand-in for redis.asyncio.ResponseError."""


_mock_aioredis = MagicMock()
_mock_aioredis.ResponseError = _FakeResponseError

# Use direct assignment so our mock wins even if redis was partially cached.
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = _mock_aioredis
# Remove any cached copy of the example so it re-imports with our mock.
sys.modules.pop("examples.redis_stream_backend", None)

import examples.redis_stream_backend as _redis_mod  # noqa: E402
from examples.redis_stream_backend import (  # noqa: E402
    RedisStreamBackend,
    RedisWebhookEvent,
)

# Patch the module-level `aioredis` binding so `except aioredis.ResponseError`
# resolves to our fake class at runtime, regardless of how `import ... as` bound it.
_redis_mod.aioredis = _mock_aioredis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend(**kwargs) -> tuple[RedisStreamBackend, AsyncMock]:
    """Return a backend wired to a fresh AsyncMock redis client."""
    client = AsyncMock()
    client.xadd = AsyncMock()
    client.xreadgroup = AsyncMock(return_value=[])
    client.xack = AsyncMock()
    client.xgroup_create = AsyncMock()
    client.aclose = AsyncMock()

    backend = RedisStreamBackend(**kwargs)
    backend._client = client  # bypass lazy from_url init
    return backend, client


# ---------------------------------------------------------------------------
# publish()
# ---------------------------------------------------------------------------

class TestPublish:
    async def test_calls_xadd_with_correct_stream_key(self):
        backend, client = _make_backend(stream_key="myapp:events")
        await backend.publish("order.created", {"id": "ord_1"}, owner_id=None)
        client.xadd.assert_called_once()
        args = client.xadd.call_args
        assert args[0][0] == "myapp:events"

    async def test_serializes_payload_as_json(self):
        backend, client = _make_backend()
        payload = {"id": "ord_1", "amount": 99}
        await backend.publish("order.created", payload, owner_id=None)
        sent = client.xadd.call_args[0][1]
        assert json.loads(sent["payload"]) == payload

    async def test_includes_event_name_in_message(self):
        backend, client = _make_backend()
        await backend.publish("user.signup", {"uid": 42}, owner_id=None)
        sent = client.xadd.call_args[0][1]
        assert sent["event_name"] == "user.signup"

    async def test_owner_id_none_becomes_empty_string(self):
        backend, client = _make_backend()
        await backend.publish("x", {}, owner_id=None)
        sent = client.xadd.call_args[0][1]
        assert sent["owner_id"] == ""

    async def test_owner_id_value_is_preserved(self):
        backend, client = _make_backend()
        await backend.publish("x", {}, owner_id="tenant-42")
        sent = client.xadd.call_args[0][1]
        assert sent["owner_id"] == "tenant-42"


# ---------------------------------------------------------------------------
# consume()
# ---------------------------------------------------------------------------

class TestConsume:
    async def test_yields_event_from_xreadgroup_response(self):
        backend, client = _make_backend()
        payload = {"id": "ord_1"}
        client.xreadgroup.side_effect = [
            [("fasthooks:events", [("1-0", {"event_name": "order.created", "payload": json.dumps(payload), "owner_id": ""})])],
            [],  # second call returns nothing → generator yields nothing more
        ]

        gen = backend.consume()
        event = await gen.__anext__()
        await gen.aclose()

        assert isinstance(event, RedisWebhookEvent)
        assert event.id == "1-0"
        assert event.event_name == "order.created"
        assert event.payload == payload

    async def test_empty_owner_id_becomes_none(self):
        backend, client = _make_backend()
        client.xreadgroup.side_effect = [
            [("fasthooks:events", [("2-0", {"event_name": "e", "payload": "{}", "owner_id": ""})])],
            [],
        ]
        gen = backend.consume()
        event = await gen.__anext__()
        await gen.aclose()
        assert event.owner_id is None

    async def test_non_empty_owner_id_is_preserved(self):
        backend, client = _make_backend()
        client.xreadgroup.side_effect = [
            [("fasthooks:events", [("3-0", {"event_name": "e", "payload": "{}", "owner_id": "tenant-7"})])],
            [],
        ]
        gen = backend.consume()
        event = await gen.__anext__()
        await gen.aclose()
        assert event.owner_id == "tenant-7"

    async def test_uses_configured_consumer_group_and_name(self):
        backend, client = _make_backend(consumer_group="grp", consumer_name="w2")
        client.xreadgroup.side_effect = [
            [("fasthooks:events", [("1-0", {"event_name": "e", "payload": "{}", "owner_id": ""})])],
            [],
        ]
        gen = backend.consume()
        await gen.__anext__()
        await gen.aclose()
        call_args = client.xreadgroup.call_args
        assert call_args[0][0] == "grp"
        assert call_args[0][1] == "w2"


# ---------------------------------------------------------------------------
# ack()
# ---------------------------------------------------------------------------

class TestAck:
    async def test_calls_xack_with_stream_key_group_and_id(self):
        backend, client = _make_backend(stream_key="s", consumer_group="g")
        await backend.ack("5-0")
        client.xack.assert_called_once_with("s", "g", "5-0")


# ---------------------------------------------------------------------------
# aclose()
# ---------------------------------------------------------------------------

class TestAclose:
    async def test_closes_client_and_clears_reference(self):
        backend, client = _make_backend()
        await backend.aclose()
        client.aclose.assert_called_once()
        assert backend._client is None

    async def test_noop_when_client_never_connected(self):
        backend = RedisStreamBackend()
        # _client is None — should not raise
        await backend.aclose()


# ---------------------------------------------------------------------------
# _ensure_group()
# ---------------------------------------------------------------------------

class TestEnsureGroup:
    async def test_creates_group_with_mkstream(self):
        backend, client = _make_backend(stream_key="s", consumer_group="g")
        await backend._ensure_group(client)
        client.xgroup_create.assert_called_once_with("s", "g", id="0", mkstream=True)

    async def test_ignores_busygroup_error(self):
        backend, client = _make_backend()
        client.xgroup_create.side_effect = _FakeResponseError("BUSYGROUP Consumer Group name already exists")
        # should not raise
        await backend._ensure_group(client)

    async def test_reraises_other_response_errors(self):
        backend, client = _make_backend()
        client.xgroup_create.side_effect = _FakeResponseError("ERR some other error")
        with pytest.raises(_FakeResponseError):
            await backend._ensure_group(client)

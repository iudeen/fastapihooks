"""Tests for examples/mongodb_store.py.

motor is not installed in the dev environment, so we inject a mock into
sys.modules before importing the example. Tests verify CRUD contract
behaviour (insert, delete, find, update_one calls) against a mock
Motor collection.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Inject motor mock BEFORE the example module is imported.
# ---------------------------------------------------------------------------
_mock_motor_module = MagicMock()
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", _mock_motor_module)

from examples.mongodb_store import MongoDBStore  # noqa: E402
from fastapihooks.stores import StoredWebhookSubscription  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(
    sub_id="id-1",
    event_name="order.created",
    target_url="https://recv.example.com/hook",
    auth_type="none",
    auth_value=None,
    metadata=None,
) -> dict:
    return {
        "id": sub_id,
        "event_name": event_name,
        "target_url": target_url,
        "auth_type": auth_type,
        "auth_value": auth_value,
        "metadata": metadata or {},
    }


def _async_cursor(*docs):
    """Return an object that can be used with `async for`."""
    async def _gen():
        for doc in docs:
            yield doc
    return _gen()


def _make_store() -> tuple[MongoDBStore, AsyncMock]:
    """Return a store wired to a mock Motor collection."""
    col = AsyncMock()
    col.insert_one = AsyncMock()
    col.delete_one = AsyncMock()
    col.find_one = AsyncMock(return_value=None)
    col.find = MagicMock(return_value=_async_cursor())
    col.update_one = AsyncMock()
    col.create_index = AsyncMock()

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=col)
    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    _mock_motor_module.AsyncIOMotorClient.return_value = mock_client

    store = MongoDBStore()
    store._col = col
    store._client = mock_client
    return store, col


# ---------------------------------------------------------------------------
# add_subscription()
# ---------------------------------------------------------------------------

class TestAddSubscription:
    async def test_inserts_document_and_returns_id(self):
        store, col = _make_store()
        sid = await store.add_subscription("order.created", "https://recv.example.com/hook")
        col.insert_one.assert_called_once()
        doc = col.insert_one.call_args[0][0]
        assert doc["id"] == sid
        assert doc["event_name"] == "order.created"
        assert doc["target_url"] == "https://recv.example.com/hook"

    async def test_defaults_auth_type_to_none(self):
        store, col = _make_store()
        await store.add_subscription("e", "https://x.example.com")
        doc = col.insert_one.call_args[0][0]
        assert doc["auth_type"] == "none"
        assert doc["auth_value"] is None

    async def test_stores_bearer_auth(self):
        store, col = _make_store()
        await store.add_subscription("e", "https://x.example.com", auth_type="bearer", auth_value="tok")
        doc = col.insert_one.call_args[0][0]
        assert doc["auth_type"] == "bearer"
        assert doc["auth_value"] == "tok"

    async def test_stores_metadata(self):
        store, col = _make_store()
        await store.add_subscription("e", "https://x.example.com", metadata={"env": "prod"})
        doc = col.insert_one.call_args[0][0]
        assert doc["metadata"] == {"env": "prod"}

    async def test_returns_unique_ids(self):
        store, col = _make_store()
        id1 = await store.add_subscription("e", "https://a.example.com")
        id2 = await store.add_subscription("e", "https://b.example.com")
        assert id1 != id2


# ---------------------------------------------------------------------------
# remove_subscription()
# ---------------------------------------------------------------------------

class TestRemoveSubscription:
    async def test_returns_true_when_document_deleted(self):
        store, col = _make_store()
        col.delete_one.return_value = MagicMock(deleted_count=1)
        result = await store.remove_subscription("id-1")
        assert result is True
        col.delete_one.assert_called_once_with({"id": "id-1"})

    async def test_returns_false_when_not_found(self):
        store, col = _make_store()
        col.delete_one.return_value = MagicMock(deleted_count=0)
        result = await store.remove_subscription("nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# get_subscriptions()
# ---------------------------------------------------------------------------

class TestGetSubscriptions:
    async def test_returns_subscriptions_for_event(self):
        store, col = _make_store()
        col.find.return_value = _async_cursor(_doc("id-1"), _doc("id-2"))
        results = list(await store.get_subscriptions("order.created"))
        assert len(results) == 2
        assert all(isinstance(r, StoredWebhookSubscription) for r in results)
        col.find.assert_called_once_with({"event_name": "order.created"})

    async def test_returns_empty_for_unknown_event(self):
        store, col = _make_store()
        col.find.return_value = _async_cursor()
        results = list(await store.get_subscriptions("unknown.event"))
        assert results == []

    async def test_model_fields_are_mapped_correctly(self):
        store, col = _make_store()
        col.find.return_value = _async_cursor(
            _doc("sid", event_name="order.created", target_url="https://t.example.com",
                 auth_type="bearer", auth_value="tok", metadata={"k": "v"})
        )
        results = list(await store.get_subscriptions("order.created"))
        sub = results[0]
        assert sub.id == "sid"
        assert sub.target_url == "https://t.example.com"
        assert sub.auth_type == "bearer"
        assert sub.auth_value == "tok"
        assert sub.metadata == {"k": "v"}


# ---------------------------------------------------------------------------
# update_subscription()
# ---------------------------------------------------------------------------

class TestUpdateSubscription:
    async def test_returns_false_when_not_found(self):
        store, col = _make_store()
        col.find_one.return_value = None
        result = await store.update_subscription("nonexistent", target_url="https://new.example.com")
        assert result is False
        col.update_one.assert_not_called()

    async def test_updates_target_url(self):
        store, col = _make_store()
        col.find_one.return_value = _doc()
        result = await store.update_subscription("id-1", target_url="https://new.example.com")
        assert result is True
        _, kwargs = col.update_one.call_args
        update = col.update_one.call_args[0][1]
        assert update["$set"]["target_url"] == "https://new.example.com"

    async def test_merges_metadata_with_existing(self):
        store, col = _make_store()
        col.find_one.return_value = _doc(metadata={"existing": "value"})
        await store.update_subscription("id-1", metadata={"new_key": "new_val"})
        update = col.update_one.call_args[0][1]
        assert update["$set"]["metadata"] == {"existing": "value", "new_key": "new_val"}

    async def test_metadata_update_overwrites_existing_keys(self):
        store, col = _make_store()
        col.find_one.return_value = _doc(metadata={"key": "old"})
        await store.update_subscription("id-1", metadata={"key": "new"})
        update = col.update_one.call_args[0][1]
        assert update["$set"]["metadata"]["key"] == "new"

    async def test_noop_when_no_fields_provided(self):
        store, col = _make_store()
        col.find_one.return_value = _doc()
        result = await store.update_subscription("id-1")
        assert result is True
        col.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# get_subscription()
# ---------------------------------------------------------------------------

class TestGetSubscription:
    async def test_returns_model_when_found(self):
        store, col = _make_store()
        col.find_one.return_value = _doc("sid")
        result = await store.get_subscription("sid")
        assert isinstance(result, StoredWebhookSubscription)
        assert result.id == "sid"
        col.find_one.assert_called_once_with({"id": "sid"})

    async def test_returns_none_when_not_found(self):
        store, col = _make_store()
        col.find_one.return_value = None
        result = await store.get_subscription("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# init_indexes()
# ---------------------------------------------------------------------------

class TestInitIndexes:
    async def test_creates_event_name_and_id_indexes(self):
        store, col = _make_store()
        await store.init_indexes()
        calls = [c[0][0] for c in col.create_index.call_args_list]
        assert "event_name" in calls
        assert "id" in calls


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------

class TestClose:
    def test_closes_motor_client(self):
        store, _ = _make_store()
        store.close()
        store._client.close.assert_called_once()

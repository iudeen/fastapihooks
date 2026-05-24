"""Tests for MemoryStore."""


from fasthooks.stores.base_store import StoredWebhookSubscription
from fasthooks.stores.memory_store import MemoryStore


class TestAddSubscription:
    async def test_returns_string_id(self):
        store = MemoryStore()
        sub_id = await store.add_subscription(
            event_name="order.created",
            target_url="https://example.com/hook",
        )
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0

    async def test_each_call_returns_unique_id(self):
        store = MemoryStore()
        id1 = await store.add_subscription("evt", "https://a.example.com/hook")
        id2 = await store.add_subscription("evt", "https://b.example.com/hook")
        assert id1 != id2

    async def test_stored_fields_match_inputs(self):
        store = MemoryStore()
        sub_id = await store.add_subscription(
            event_name="order.created",
            target_url="https://example.com/hook",
            auth_type="bearer",
            auth_value="tok",
            metadata={"env": "prod"},
        )
        sub = await store.get_subscription(sub_id)
        assert sub is not None
        assert sub.event_name == "order.created"
        assert sub.target_url == "https://example.com/hook"
        assert sub.auth_type == "bearer"
        assert sub.auth_value == "tok"
        assert sub.metadata == {"env": "prod"}

    async def test_default_metadata_is_empty_dict(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://example.com/hook")
        sub = await store.get_subscription(sub_id)
        assert sub.metadata == {}

    async def test_default_auth_type_is_none(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://example.com/hook")
        sub = await store.get_subscription(sub_id)
        assert sub.auth_type == "none"


class TestGetSubscriptions:
    async def test_filters_by_event_name(self, populated_store):
        subs = list(await populated_store.get_subscriptions("order.created"))
        assert len(subs) == 2
        for sub in subs:
            assert sub.event_name == "order.created"

    async def test_different_event_returns_correct_subs(self, populated_store):
        subs = list(await populated_store.get_subscriptions("user.signup"))
        assert len(subs) == 1
        assert subs[0].event_name == "user.signup"

    async def test_unknown_event_returns_empty(self, populated_store):
        subs = list(await populated_store.get_subscriptions("nonexistent.event"))
        assert subs == []

    async def test_returns_stored_webhook_subscription_instances(self, populated_store):
        subs = list(await populated_store.get_subscriptions("order.created"))
        for sub in subs:
            assert isinstance(sub, StoredWebhookSubscription)
            assert hasattr(sub, "id")


class TestRemoveSubscription:
    async def test_returns_true_when_found(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://example.com/hook")
        result = await store.remove_subscription(sub_id)
        assert result is True

    async def test_subscription_gone_after_removal(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://example.com/hook")
        await store.remove_subscription(sub_id)
        sub = await store.get_subscription(sub_id)
        assert sub is None

    async def test_returns_false_for_unknown_id(self):
        store = MemoryStore()
        result = await store.remove_subscription("nonexistent-id")
        assert result is False

    async def test_does_not_affect_other_subscriptions(self):
        store = MemoryStore()
        id1 = await store.add_subscription("evt", "https://a.example.com/hook")
        id2 = await store.add_subscription("evt", "https://b.example.com/hook")
        await store.remove_subscription(id1)
        sub2 = await store.get_subscription(id2)
        assert sub2 is not None


class TestUpdateSubscription:
    async def test_returns_true_when_found(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://old.example.com/hook")
        result = await store.update_subscription(sub_id, target_url="https://new.example.com/hook")
        assert result is True

    async def test_returns_false_for_unknown_id(self):
        store = MemoryStore()
        result = await store.update_subscription("nonexistent-id", target_url="https://x.example.com")
        assert result is False

    async def test_updates_target_url(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://old.example.com/hook")
        await store.update_subscription(sub_id, target_url="https://new.example.com/hook")
        sub = await store.get_subscription(sub_id)
        assert sub.target_url == "https://new.example.com/hook"

    async def test_updates_auth_type_and_value(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://example.com/hook")
        await store.update_subscription(sub_id, auth_type="bearer", auth_value="token123")
        sub = await store.get_subscription(sub_id)
        assert sub.auth_type == "bearer"
        assert sub.auth_value == "token123"

    async def test_metadata_is_merged_not_replaced(self):
        store = MemoryStore()
        sub_id = await store.add_subscription(
            "evt", "https://example.com/hook", metadata={"key1": "val1"}
        )
        await store.update_subscription(sub_id, metadata={"key2": "val2"})
        sub = await store.get_subscription(sub_id)
        assert sub.metadata == {"key1": "val1", "key2": "val2"}

    async def test_metadata_update_overrides_existing_keys(self):
        store = MemoryStore()
        sub_id = await store.add_subscription(
            "evt", "https://example.com/hook", metadata={"key": "old"}
        )
        await store.update_subscription(sub_id, metadata={"key": "new"})
        sub = await store.get_subscription(sub_id)
        assert sub.metadata["key"] == "new"

    async def test_none_fields_are_not_applied(self):
        store = MemoryStore()
        sub_id = await store.add_subscription(
            "evt", "https://original.example.com/hook"
        )
        await store.update_subscription(sub_id)  # no fields → no changes
        sub = await store.get_subscription(sub_id)
        assert sub.target_url == "https://original.example.com/hook"

    async def test_uses_model_copy(self):
        """update_subscription must not mutate the original object in place; it should
        replace it with a new instance (model_copy behaviour)."""
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://example.com/hook")
        original = await store.get_subscription(sub_id)
        await store.update_subscription(sub_id, target_url="https://new.example.com/hook")
        updated = await store.get_subscription(sub_id)
        # The original snapshot should not have changed
        assert original.target_url == "https://example.com/hook"
        assert updated.target_url == "https://new.example.com/hook"
        assert original is not updated


class TestGetSubscription:
    async def test_returns_correct_subscription(self):
        store = MemoryStore()
        sub_id = await store.add_subscription("evt", "https://example.com/hook")
        sub = await store.get_subscription(sub_id)
        assert sub is not None
        assert sub.id == sub_id

    async def test_returns_none_for_unknown_id(self):
        store = MemoryStore()
        sub = await store.get_subscription("does-not-exist")
        assert sub is None

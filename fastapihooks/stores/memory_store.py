import uuid
from collections.abc import Iterable
from typing import Any, Literal

from fastapihooks.stores.base_store import (
    BaseStore,
    StoredWebhookSubscription,
)


class MemoryStore(BaseStore):
    """In-memory store for webhook subscriptions. Suitable for development and BackgroundTasks backend."""

    def __init__(self):
        self._subscriptions: dict[str, StoredWebhookSubscription] = {}

    async def add_subscription(
        self,
        event_name: str,
        target_url: str,
        auth_type: Literal["bearer", "none"] = "none",
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        subscription_id = str(uuid.uuid4())
        subscription = StoredWebhookSubscription(
            id=subscription_id,
            event_name=event_name,
            target_url=target_url,
            auth_type=auth_type,
            auth_value=auth_value,
            metadata=metadata or {},
        )
        self._subscriptions[subscription_id] = subscription
        return subscription_id

    async def remove_subscription(self, subscription_id: str) -> bool:
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]
            return True
        return False

    async def get_subscriptions(
        self,
        event_name: str,
    ) -> Iterable[StoredWebhookSubscription]:
        return [
            sub
            for sub in self._subscriptions.values()
            if sub.event_name == event_name
        ]

    async def update_subscription(
        self,
        subscription_id: str,
        target_url: str | None = None,
        auth_type: Literal["bearer", "none"] | None = None,
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if subscription_id not in self._subscriptions:
            return False

        sub = self._subscriptions[subscription_id]

        changes: dict = {}
        if target_url is not None:
            changes["target_url"] = target_url
        if auth_type is not None:
            changes["auth_type"] = auth_type
        if auth_value is not None:
            changes["auth_value"] = auth_value
        if metadata is not None:
            changes["metadata"] = {**(sub.metadata or {}), **metadata}

        self._subscriptions[subscription_id] = sub.model_copy(update=changes)
        return True

    async def get_subscription(self, subscription_id: str) -> StoredWebhookSubscription | None:
        return self._subscriptions.get(subscription_id)

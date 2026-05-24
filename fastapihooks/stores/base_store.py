from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field


class WebhookSubscription(BaseModel):
    """Represents a webhook subscription."""

    event_name: str
    target_url: str
    auth_type: Literal["bearer", "none"] = "none"
    auth_value: str | None = None
    metadata: dict[str, Any] | None = Field(default_factory=dict)


class StoredWebhookSubscription(WebhookSubscription):
    """Represents a stored webhook subscription with an ID."""

    id: str


class BaseStore(ABC):
    """Abstract interface for storing and retrieving webhook subscriptions."""

    @abstractmethod
    async def add_subscription(
        self,
        event_name: str,
        target_url: str,
        auth_type: Literal["bearer", "none"] = "none",
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a new webhook subscription.

        Returns the subscription ID.
        """

    @abstractmethod
    async def remove_subscription(self, subscription_id: str) -> bool:
        """Remove a webhook subscription. Returns True if found and removed."""

    @abstractmethod
    async def get_subscriptions(
        self,
        event_name: str,
    ) -> Iterable[StoredWebhookSubscription]:
        """Get all subscriptions for an event."""

    @abstractmethod
    async def update_subscription(
        self,
        subscription_id: str,
        target_url: str | None = None,
        auth_type: Literal["bearer", "none"] | None = None,
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update a subscription. Returns True if found and updated."""

    async def get_subscription(self, subscription_id: str) -> StoredWebhookSubscription | None:
        """Get a single subscription by ID. Optional default implementation."""
        raise NotImplementedError

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from fasthooks.stores.base_store import WebhookSubscription


class BaseDispatcher(ABC):
    """Abstract interface for dispatching webhook events."""

    @abstractmethod
    async def broadcast(self, event_name: str, payload: Any) -> None:
        """Deliver an event to all subscriptions resolved from a store.

        Args:
            event_name: Name of the event being delivered.
            payload: JSON-serializable payload to send.
        """
        raise NotImplementedError

    @abstractmethod
    async def broadcast_to_subscribers(
        self, payload: Any, subscribers: Iterable[WebhookSubscription]
    ) -> None:
        """Deliver an event to an explicit list of subscribers.

        Args:
            payload: JSON-serializable payload to send.
            subscribers: Iterable of `WebhookSubscription`-like objects (including `StoredWebhookSubscription`).
        """
        raise NotImplementedError

    async def aclose(self) -> None:  # noqa: B027
        """Optional cleanup hook. Override if needed."""
        pass

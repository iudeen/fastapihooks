from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from fastapihooks.stores.base_store import WebhookSubscription


class BaseBackend(ABC):
    """Extension contract for fastapihooks transport backends.

    Fastapihooks intentionally ships with only `BackgroundTaskBackend` by default.
    Additional transports (Redis, Kafka, SQS, etc.) should be implemented by
    users or external packages by subclassing this base class.
    """

    @abstractmethod
    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: str | None,
        subscribers: list[WebhookSubscription] | None = None,
    ):
        """Enqueue or immediately dispatch a webhook event."""

    async def consume(self) -> AsyncIterator[Any]:
        """Yield events for worker-driven backends.

        Backends that dispatch inline (for example, BackgroundTaskBackend)
        can keep the default NotImplemented behavior.
        """
        raise NotImplementedError

    async def ack(self, event_id: str):
        """Acknowledge successful processing for queue-like backends."""
        raise NotImplementedError

    async def aclose(self) -> None:  # noqa: B027
        """Release any resources held by the backend (connections, thread pools, etc.).

        Called automatically when using the backend as an async context manager.
        Override in subclasses that hold long-lived resources.
        """
        pass

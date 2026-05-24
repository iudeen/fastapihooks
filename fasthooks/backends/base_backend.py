from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Optional

from fasthooks.stores.base_store import WebhookSubscription


class BaseBackend(ABC):
    """Extension contract for fasthooks transport backends.

    Fasthooks intentionally ships with only `BackgroundTaskBackend` by default.
    Additional transports (Redis, Kafka, SQS, etc.) should be implemented by
    users or external packages by subclassing this base class.
    """

    @abstractmethod
    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: Optional[str],
        subscribers: Optional[list[WebhookSubscription]] = None,
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

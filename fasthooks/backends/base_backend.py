from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional


class BaseBackend(ABC):
    """Abstract interface for publishing and consuming webhook events."""

    @abstractmethod
    async def publish(self, event_name: str, payload: Any, owner_id: Optional[str]):
        """Enqueue or immediately dispatch a webhook event."""

    async def consume(self) -> AsyncIterator[Any]:
        """Yield events for the worker sidecar. BackgroundTask backend does not implement."""
        raise NotImplementedError

    async def ack(self, event_id: str):
        """Acknowledge successful processing of an event (noop by default)."""
        raise NotImplementedError

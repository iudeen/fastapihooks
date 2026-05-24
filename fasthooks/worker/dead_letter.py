from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fasthooks.stores.base_store import WebhookSubscription


@dataclass
class DeadLetterEntry:
    subscription: WebhookSubscription
    payload: Any
    error: BaseException
    failed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class InMemoryDeadLetterQueue:
    """Collects failed webhook deliveries in memory after all retries are exhausted.

    Pass an instance as ``on_failure`` to ``WebhookDispatcher``::

        dlq = InMemoryDeadLetterQueue()
        dispatcher = WebhookDispatcher(signing_secret="...", on_failure=dlq)

    Inspect failures via ``dlq.entries`` or drain them with ``dlq.drain()``.
    """

    def __init__(self, maxlen: int = 1000) -> None:
        self._queue: deque[DeadLetterEntry] = deque(maxlen=maxlen)

    async def __call__(
        self,
        subscription: WebhookSubscription,
        payload: Any,
        error: BaseException,
    ) -> None:
        self._queue.append(DeadLetterEntry(subscription=subscription, payload=payload, error=error))

    @property
    def entries(self) -> list[DeadLetterEntry]:
        """All current dead-letter entries (oldest first)."""
        return list(self._queue)

    def drain(self) -> list[DeadLetterEntry]:
        """Return all entries and clear the queue."""
        entries = list(self._queue)
        self._queue.clear()
        return entries

    def __len__(self) -> int:
        return len(self._queue)

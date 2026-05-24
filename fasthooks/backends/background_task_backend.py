from collections.abc import Callable, Coroutine
from typing import Any

from fasthooks.backends.base_backend import BaseBackend
from fasthooks.stores.base_store import WebhookSubscription
from fasthooks.worker.dispatcher import WebhookDispatcher


class BackgroundTaskBackend(BaseBackend):
    def __init__(
        self,
        store=None,
        signing_secret: str = "",
        *,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
        on_failure: Callable[..., Coroutine] | None = None,
    ):
        self.dispatcher = WebhookDispatcher(
            store=store,
            signing_secret=signing_secret,
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
            on_failure=on_failure,
        )

    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: str | None,
        subscribers: list[WebhookSubscription] | None = None,
    ):
        if subscribers:
            await self.dispatcher.broadcast_to_subscribers(payload=payload, subscribers=subscribers)

        if self.dispatcher.store:
            await self.dispatcher.broadcast(event_name, payload)

    async def consume(self):
        raise NotImplementedError("BackgroundTaskBackend does not use a separate worker.")

    async def aclose(self) -> None:
        """Close the underlying HTTP client. Call on application shutdown."""
        await self.dispatcher.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

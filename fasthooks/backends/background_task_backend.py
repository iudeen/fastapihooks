from typing import Any, Optional

from fasthooks.backends.base_backend import BaseBackend
from fasthooks.stores.base_store import WebhookSubscription
from fasthooks.worker.dispatcher import WebhookDispatcher


class BackgroundTaskBackend(BaseBackend):
    def __init__(self, store=None, signing_secret: str = ""):
        # Store is optional - only needed if using store-based subscriptions
        self.dispatcher = WebhookDispatcher(store, signing_secret) if store else None
        self.signing_secret = signing_secret

    async def publish(
        self,
        event_name: str,
        payload: Any,
        owner_id: Optional[str],
        subscribers: Optional[list[WebhookSubscription]] = None,
    ):       
        # Dispatch to direct subscribers if provided
        if subscribers:
            if self.dispatcher is None:
                from fasthooks.worker.dispatcher import WebhookDispatcher
                self.dispatcher = WebhookDispatcher(store=None, signing_secret=self.signing_secret)
            await self.dispatcher.broadcast_to_subscribers(payload=payload, subscribers=subscribers)
        
        # Also dispatch through store if available
        if self.dispatcher and self.dispatcher.store:
            await self.dispatcher.broadcast(event_name, payload)

    async def consume(self):
        raise NotImplementedError("BackgroundTaskBackend does not use a separate worker.")
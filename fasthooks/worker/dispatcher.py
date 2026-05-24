import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any, Iterable

import httpx

from fasthooks.stores.base_store import StoredWebhookSubscription, WebhookSubscription
from fasthooks.worker.base_dispatcher import BaseDispatcher

logger = logging.getLogger(__name__)


class WebhookDispatcher(BaseDispatcher):
    """Fan-out dispatcher for delivering webhook payloads.
    
    Supports both store-based subscriptions and direct subscriber lists.
    Uses HMAC-SHA256 signing and optional bearer token authentication.
    """

    def __init__(
        self,
        store=None,
        signing_secret: str = "",
        *,
        client: httpx.AsyncClient | None = None,
        max_concurrency: int = 100,
    ) -> None:
        """Initialize the dispatcher.

        Args:
            store: Store instance that exposes `get_subscriptions(event_name)` and returns stored subscriptions; can be None when only direct subscribers are used.
            signing_secret: Shared secret used to compute the `X-Fasthooks-Signature` header.
            client: Optional shared `httpx.AsyncClient`; if omitted a new client is created with a 10s timeout.
            max_concurrency: Maximum number of concurrent webhook deliveries.
        """
        self.store = store
        self.secret = signing_secret.encode() if signing_secret else None
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.client = client or httpx.AsyncClient(timeout=10.0)

    async def broadcast(self, event_name: str, payload: Any) -> None:
        """Deliver an event to all subscriptions resolved from the store.

        Args:
            event_name: Name of the event being delivered.
            payload: JSON-serializable payload to send.
        """
        if not self.store:
            return
        subscriptions = await self._get_subscriptions(event_name)
        if not subscriptions:
            return

        tasks = [self._send(subscription, payload) for subscription in subscriptions]
        await self._gather(tasks)

    async def broadcast_to_subscribers(
        self, payload: Any, subscribers: Iterable[WebhookSubscription]
    ) -> None:
        """Deliver an event to an explicit list of subscribers.

        Args:
            payload: JSON-serializable payload to send.
            subscribers: Iterable of `WebhookSubscription`-like objects (including `StoredWebhookSubscription`).
        """
        if not subscribers:
            return

        tasks = [self._send(subscription, payload) for subscription in subscribers]
        await self._gather(tasks)

    @staticmethod
    async def _gather(tasks: list) -> None:
        """Run delivery tasks concurrently, logging each failure without aborting siblings."""
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Webhook delivery failed: %s", result, exc_info=result)

    async def _get_subscriptions(self, event_name: str) -> Iterable[StoredWebhookSubscription]:
        """Fetch subscriptions for an event from the store."""
        return await self.store.get_subscriptions(event_name=event_name)

    async def _send(self, subscription: WebhookSubscription, payload: Any) -> None:
        """Send a single webhook to a subscriber (direct or stored)."""
        payload_bytes = json.dumps(payload).encode()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Fasthooks-Event": subscription.event_name,
        }
        if self.secret:
            hex_digest = hmac.new(self.secret, payload_bytes, hashlib.sha256).hexdigest()
            headers["X-Fasthooks-Signature"] = f"sha256={hex_digest}"

        auth = self._build_auth(subscription)

        async with self.semaphore:
            response = await self.client.post(
                str(subscription.target_url),
                content=payload_bytes,
                headers=headers,
                auth=auth,
            )
            response.raise_for_status()

    def _build_auth(self, subscription: WebhookSubscription) -> httpx.Auth | None:
        """Construct an httpx auth handler for the subscription if configured."""
        if subscription.auth_type == "bearer" and subscription.auth_value:
            class _BearerAuth(httpx.Auth):
                def __init__(self, token: str) -> None:
                    self.token = token

                def auth_flow(self, request):  # type: ignore[override]
                    request.headers["Authorization"] = f"Bearer {self.token}"
                    yield request

            return _BearerAuth(subscription.auth_value)
        return None

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()
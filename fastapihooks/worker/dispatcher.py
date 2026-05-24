import asyncio
import hashlib
import hmac
import json
import logging
import random
from collections.abc import Callable, Coroutine, Iterable
from typing import Any

import httpx

from fastapihooks.stores.base_store import StoredWebhookSubscription, WebhookSubscription
from fastapihooks.worker.base_dispatcher import BaseDispatcher

logger = logging.getLogger(__name__)

# Retry on network errors and server-side failures; never retry 4xx (client errors).
_RETRYABLE_STATUS = range(500, 600)


class _BearerAuth(httpx.Auth):
    def __init__(self, token: str) -> None:
        self.token = token

    def auth_flow(self, request):  # type: ignore[override]
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class WebhookDispatcher(BaseDispatcher):
    """Fan-out dispatcher for delivering webhook payloads.

    Supports both store-based subscriptions and direct subscriber lists.
    Uses HMAC-SHA256 signing, optional bearer token auth, exponential-backoff
    retries, and an optional dead-letter callback for exhausted deliveries.
    """

    def __init__(
        self,
        store=None,
        signing_secret: str = "",
        *,
        client: httpx.AsyncClient | None = None,
        max_concurrency: int = 100,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
        on_failure: Callable[..., Coroutine] | None = None,
    ) -> None:
        """
        Args:
            store: Store exposing ``get_subscriptions(event_name)``; can be None.
            signing_secret: Shared secret for ``X-Fastapihooks-Signature``; omit to skip signing.
            client: Shared ``httpx.AsyncClient``; a new one is created with a 10s timeout if omitted.
            max_concurrency: Maximum parallel webhook deliveries.
            max_retries: Number of retry attempts after the initial failure (0 = no retries).
            backoff_base: Base delay in seconds for exponential backoff.
            backoff_max: Maximum delay cap in seconds.
            on_failure: Async callable ``(subscription, payload, error)`` invoked when all
                retries are exhausted. Use ``InMemoryDeadLetterQueue`` or supply your own.
        """
        self.store = store
        self.secret = signing_secret.encode() if signing_secret else None
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.on_failure = on_failure

    async def broadcast(self, event_name: str, payload: Any) -> None:
        """Deliver an event to all subscriptions resolved from the store."""
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
        """Deliver an event to an explicit list of subscribers."""
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
        return await self.store.get_subscriptions(event_name=event_name)

    async def _send(self, subscription: WebhookSubscription, payload: Any) -> None:
        """Deliver one webhook with retry + exponential backoff."""
        payload_bytes = json.dumps(payload).encode()
        headers = self._build_headers(subscription, payload_bytes)
        auth = self._build_auth(subscription)

        last_exc: BaseException | None = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_max)
                delay *= random.uniform(0.75, 1.25)  # jitter
                logger.warning(
                    "Retrying delivery to %s (attempt %d/%d) in %.2fs",
                    subscription.target_url, attempt + 1, self.max_retries + 1, delay,
                )
                await asyncio.sleep(delay)

            try:
                async with self.semaphore:
                    response = await self.client.post(
                        str(subscription.target_url),
                        content=payload_bytes,
                        headers=headers,
                        auth=auth,
                    )
                    if response.status_code not in _RETRYABLE_STATUS:
                        response.raise_for_status()
                        return  # success
                    # 5xx — treat as retryable
                    last_exc = httpx.HTTPStatusError(
                        f"Server error {response.status_code}",
                        request=response.request,
                        response=response,
                    )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    # 4xx — subscriber bug, no point retrying
                    await self._handle_failure(subscription, payload, exc)
                    return
                last_exc = exc
            except httpx.RequestError as exc:
                # Network-level error — always retryable
                last_exc = exc

        # All attempts exhausted
        logger.error(
            "All %d delivery attempts failed for %s",
            self.max_retries + 1, subscription.target_url,
        )
        if last_exc is not None:
            await self._handle_failure(subscription, payload, last_exc)

    async def _handle_failure(
        self,
        subscription: WebhookSubscription,
        payload: Any,
        error: BaseException,
    ) -> None:
        """Invoke the dead-letter callback or log if none is configured."""
        if self.on_failure is not None:
            try:
                await self.on_failure(subscription, payload, error)
            except Exception:
                logger.exception("Dead-letter callback raised an exception")
        else:
            logger.error(
                "Webhook delivery permanently failed for %s (no dead-letter handler configured): %s",
                subscription.target_url, error,
            )

    def _build_headers(self, subscription: WebhookSubscription, payload_bytes: bytes) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Fastapihooks-Event": subscription.event_name,
        }
        if self.secret:
            hex_digest = hmac.new(self.secret, payload_bytes, hashlib.sha256).hexdigest()
            headers["X-Fastapihooks-Signature"] = f"sha256={hex_digest}"
        return headers

    def _build_auth(self, subscription: WebhookSubscription) -> httpx.Auth | None:
        if subscription.auth_type == "bearer" and subscription.auth_value:
            return _BearerAuth(subscription.auth_value)
        return None

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

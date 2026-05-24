"""Tests for WebhookDispatcher."""

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import httpx

from fastapihooks.stores.base_store import WebhookSubscription
from fastapihooks.stores.memory_store import MemoryStore
from fastapihooks.worker.dead_letter import InMemoryDeadLetterQueue
from fastapihooks.worker.dispatcher import WebhookDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sub(url: str = "https://target.example.com/hook", **kwargs) -> WebhookSubscription:
    return WebhookSubscription(
        event_name="order.created",
        target_url=url,
        **kwargs,
    )


def _expected_signature(secret: str, payload: dict) -> str:
    body = json.dumps(payload).encode()
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# HMAC signature
# ---------------------------------------------------------------------------

class TestHmacSignature:
    async def test_signature_header_present_when_secret_provided(self, signing_dispatcher, recorded_requests, signing_secret):
        sub = _make_sub()
        payload = {"order_id": 42}
        await signing_dispatcher.broadcast_to_subscribers(payload=payload, subscribers=[sub])
        assert len(recorded_requests) == 1
        sig_header = recorded_requests[0].headers.get("X-Fastapihooks-Signature")
        assert sig_header is not None
        assert sig_header.startswith("sha256=")

    async def test_signature_value_is_correct(self, signing_dispatcher, recorded_requests, signing_secret):
        sub = _make_sub()
        payload = {"order_id": 42}
        await signing_dispatcher.broadcast_to_subscribers(payload=payload, subscribers=[sub])
        received_sig = recorded_requests[0].headers["X-Fastapihooks-Signature"]
        expected_sig = _expected_signature(signing_secret, payload)
        assert received_sig == expected_sig

    async def test_signature_header_absent_when_no_secret(self, dispatcher, recorded_requests):
        sub = _make_sub()
        await dispatcher.broadcast_to_subscribers(payload={"x": 1}, subscribers=[sub])
        assert "X-Fastapihooks-Signature" not in recorded_requests[0].headers

    async def test_content_type_is_json(self, dispatcher, recorded_requests):
        sub = _make_sub()
        await dispatcher.broadcast_to_subscribers(payload={"x": 1}, subscribers=[sub])
        assert recorded_requests[0].headers["Content-Type"] == "application/json"

    async def test_event_name_header_set(self, dispatcher, recorded_requests):
        sub = _make_sub()
        await dispatcher.broadcast_to_subscribers(payload={"x": 1}, subscribers=[sub])
        assert recorded_requests[0].headers["X-Fastapihooks-Event"] == "order.created"


# ---------------------------------------------------------------------------
# Bearer auth
# ---------------------------------------------------------------------------

class TestBearerAuth:
    async def test_authorization_header_set_for_bearer(self, recorded_requests):
        transport = httpx.MockTransport(lambda req: httpx.Response(200))
        client = httpx.AsyncClient(transport=transport)
        dispatcher = WebhookDispatcher(client=client)
        sub = _make_sub(auth_type="bearer", auth_value="secret-token")

        # We need to capture the actual outgoing request; patch the client.post
        sent_headers = {}

        async def capturing_post(url, *, content, headers, auth):
            req = httpx.Request("POST", url, content=content, headers=headers)
            if auth:
                # Simulate auth_flow
                for mutated in auth.auth_flow(req):
                    req = mutated
            sent_headers.update(dict(req.headers))
            return httpx.Response(200)

        dispatcher.client.post = capturing_post  # type: ignore[method-assign]
        await dispatcher.broadcast_to_subscribers(payload={"x": 1}, subscribers=[sub])
        assert sent_headers.get("authorization") == "Bearer secret-token"

    async def test_no_auth_header_when_auth_type_none(self, dispatcher, recorded_requests):
        sub = _make_sub()  # auth_type="none" by default
        await dispatcher.broadcast_to_subscribers(payload={"x": 1}, subscribers=[sub])
        assert "Authorization" not in recorded_requests[0].headers
        assert "authorization" not in recorded_requests[0].headers


# ---------------------------------------------------------------------------
# broadcast_to_subscribers
# ---------------------------------------------------------------------------

class TestBroadcastToSubscribers:
    async def test_sends_to_all_subscribers(self, dispatcher, recorded_requests):
        subs = [
            _make_sub("https://a.example.com/hook"),
            _make_sub("https://b.example.com/hook"),
            _make_sub("https://c.example.com/hook"),
        ]
        await dispatcher.broadcast_to_subscribers(payload={"k": "v"}, subscribers=subs)
        assert len(recorded_requests) == 3

    async def test_empty_subscriber_list_sends_nothing(self, dispatcher, recorded_requests):
        await dispatcher.broadcast_to_subscribers(payload={"k": "v"}, subscribers=[])
        assert recorded_requests == []

    async def test_failure_for_one_does_not_abort_others(self, recorded_requests):
        """A 4xx/5xx response for one subscriber must not prevent delivery to the rest."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if "fail" in str(request.url):
                return httpx.Response(500)
            return httpx.Response(200)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dispatcher = WebhookDispatcher(client=client, max_retries=0)
        subs = [
            _make_sub("https://fail.example.com/hook"),
            _make_sub("https://success.example.com/hook"),
        ]
        # Should not raise even though one subscriber returns 500
        await dispatcher.broadcast_to_subscribers(payload={"k": "v"}, subscribers=subs)
        assert call_count == 2

    async def test_network_error_for_one_does_not_abort_others(self):
        """A network exception for one subscriber must not cancel the rest."""
        call_urls = []

        def handler(request: httpx.Request) -> httpx.Response:
            call_urls.append(str(request.url))
            if "error" in str(request.url):
                raise httpx.ConnectError("connection refused")
            return httpx.Response(200)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dispatcher = WebhookDispatcher(client=client, max_retries=0)
        subs = [
            _make_sub("https://error.example.com/hook"),
            _make_sub("https://ok.example.com/hook"),
        ]
        await dispatcher.broadcast_to_subscribers(payload={"k": "v"}, subscribers=subs)
        assert len(call_urls) == 2


# ---------------------------------------------------------------------------
# broadcast (store-based)
# ---------------------------------------------------------------------------

class TestBroadcast:
    async def test_broadcast_delivers_to_all_store_subscriptions(self, recorded_requests):
        store = MemoryStore()
        await store.add_subscription("order.created", "https://a.example.com/hook")
        await store.add_subscription("order.created", "https://b.example.com/hook")
        transport = make_recording_transport(recorded_requests)
        client = httpx.AsyncClient(transport=transport)
        dispatcher = WebhookDispatcher(store=store, client=client)
        await dispatcher.broadcast("order.created", {"x": 1})
        assert len(recorded_requests) == 2

    async def test_broadcast_filters_by_event_name(self, recorded_requests):
        store = MemoryStore()
        await store.add_subscription("order.created", "https://a.example.com/hook")
        await store.add_subscription("user.signup", "https://b.example.com/hook")
        transport = make_recording_transport(recorded_requests)
        client = httpx.AsyncClient(transport=transport)
        dispatcher = WebhookDispatcher(store=store, client=client)
        await dispatcher.broadcast("order.created", {"x": 1})
        assert len(recorded_requests) == 1

    async def test_broadcast_does_nothing_without_store(self, recorded_requests):
        transport = make_recording_transport(recorded_requests)
        client = httpx.AsyncClient(transport=transport)
        dispatcher = WebhookDispatcher(store=None, client=client)
        await dispatcher.broadcast("order.created", {"x": 1})
        assert recorded_requests == []

    async def test_broadcast_does_nothing_when_no_matching_subscriptions(self, recorded_requests):
        store = MemoryStore()
        await store.add_subscription("user.signup", "https://a.example.com/hook")
        transport = make_recording_transport(recorded_requests)
        client = httpx.AsyncClient(transport=transport)
        dispatcher = WebhookDispatcher(store=store, client=client)
        await dispatcher.broadcast("order.created", {"x": 1})
        assert recorded_requests == []


# ---------------------------------------------------------------------------
# max_concurrency semaphore
# ---------------------------------------------------------------------------

class TestMaxConcurrency:
    async def test_max_concurrency_limits_parallel_deliveries(self):
        """Ensure the semaphore actually restricts concurrency."""

        concurrent_high_water = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            nonlocal concurrent_high_water, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > concurrent_high_water:
                    concurrent_high_water = current_concurrent
            await asyncio.sleep(0.05)  # hold the slot briefly
            async with lock:
                current_concurrent -= 1
            return httpx.Response(200)

        client = httpx.AsyncClient(transport=httpx.MockTransport(slow_handler))
        dispatcher = WebhookDispatcher(client=client, max_concurrency=2)
        subs = [_make_sub(f"https://sub{i}.example.com/hook") for i in range(6)]
        await dispatcher.broadcast_to_subscribers(payload={}, subscribers=subs)
        assert concurrent_high_water <= 2


# ---------------------------------------------------------------------------
# aclose
# ---------------------------------------------------------------------------

class TestAclose:
    async def test_aclose_closes_httpx_client(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        dispatcher = WebhookDispatcher(client=client)
        await dispatcher.aclose()
        client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Retry + backoff
# ---------------------------------------------------------------------------

class TestRetry:
    async def test_retries_on_5xx_and_succeeds(self):
        """Dispatcher retries on 5xx and records success on eventual 200."""
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            if len(attempts) < 3:
                return httpx.Response(500)
            return httpx.Response(200)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dispatcher = WebhookDispatcher(
            client=client,
            max_retries=3,
            backoff_base=0.01,  # tiny delay so test is fast
        )
        await dispatcher._send(_make_sub(), {"x": 1})
        assert len(attempts) == 3  # failed twice, succeeded on third

    async def test_does_not_retry_on_4xx(self):
        """4xx responses are not retried — they are the subscriber's fault."""
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dlq = InMemoryDeadLetterQueue()
        dispatcher = WebhookDispatcher(client=client, max_retries=3, backoff_base=0.01, on_failure=dlq)
        await dispatcher._send(_make_sub(), {"x": 1})
        assert len(attempts) == 1  # no retries
        assert len(dlq) == 1

    async def test_exhausted_retries_route_to_dead_letter(self):
        """When all retries fail the on_failure callback receives the entry."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dlq = InMemoryDeadLetterQueue()
        dispatcher = WebhookDispatcher(
            client=client,
            max_retries=2,
            backoff_base=0.01,
            on_failure=dlq,
        )
        sub = _make_sub()
        await dispatcher._send(sub, {"order": "123"})

        assert len(dlq) == 1
        entry = dlq.entries[0]
        assert entry.subscription.target_url == sub.target_url
        assert entry.payload == {"order": "123"}
        assert isinstance(entry.error, Exception)

    async def test_network_error_is_retried(self):
        """ConnectError (network-level) triggers retries just like 5xx."""
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            if len(attempts) < 2:
                raise httpx.ConnectError("refused")
            return httpx.Response(200)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dispatcher = WebhookDispatcher(client=client, max_retries=3, backoff_base=0.01)
        await dispatcher._send(_make_sub(), {})
        assert len(attempts) == 2


# ---------------------------------------------------------------------------
# Dead-letter queue
# ---------------------------------------------------------------------------

class TestDeadLetterQueue:
    async def test_in_memory_dlq_collects_failures(self):
        dlq = InMemoryDeadLetterQueue()
        sub = _make_sub()
        error = RuntimeError("boom")
        await dlq(sub, {"k": "v"}, error)

        assert len(dlq) == 1
        entry = dlq.entries[0]
        assert entry.subscription is sub
        assert entry.payload == {"k": "v"}
        assert entry.error is error
        assert entry.failed_at is not None

    async def test_drain_clears_queue(self):
        dlq = InMemoryDeadLetterQueue()
        await dlq(_make_sub(), {}, RuntimeError("e1"))
        await dlq(_make_sub(), {}, RuntimeError("e2"))

        drained = dlq.drain()
        assert len(drained) == 2
        assert len(dlq) == 0

    async def test_maxlen_evicts_oldest(self):
        dlq = InMemoryDeadLetterQueue(maxlen=2)
        await dlq(_make_sub(), {"i": 0}, RuntimeError("e0"))
        await dlq(_make_sub(), {"i": 1}, RuntimeError("e1"))
        await dlq(_make_sub(), {"i": 2}, RuntimeError("e2"))

        assert len(dlq) == 2
        assert dlq.entries[0].payload == {"i": 1}
        assert dlq.entries[1].payload == {"i": 2}

    async def test_no_on_failure_logs_error(self, caplog):
        """When no dead-letter handler is set, failure is logged."""
        import logging
        def handler(request):
            return httpx.Response(500)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dispatcher = WebhookDispatcher(client=client, max_retries=0)

        with caplog.at_level(logging.ERROR, logger="fastapihooks.worker.dispatcher"):
            await dispatcher._send(_make_sub(), {})

        assert any("no dead-letter handler" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Helper used by broadcast tests (local copy so they are self-contained)
# ---------------------------------------------------------------------------

def make_recording_transport(recorded: list, status_code: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(status_code)
    return httpx.MockTransport(handler)

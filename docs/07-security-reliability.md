# 07. Security and Reliability

## Signature Format
Fastapihooks signs payloads with HMAC-SHA256 when a signing secret is configured.

Header:
- X-Fastapihooks-Signature: sha256=<hex_digest>

## Verification Example
```python
import hashlib
import hmac


def verify_signature(payload: bytes, secret: str, header: str) -> bool:
    algorithm, _, received = header.partition("=")
    if algorithm != "sha256" or not received:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)
```

## Retry Model
Dispatcher behavior:
- Retries network failures.
- Retries 5xx responses.
- Does not retry 4xx responses (subscriber bug — won't self-heal).
- Uses exponential backoff with jitter.

Configure via `BackgroundTaskBackend` constructor:
```python
from fastapihooks.backends import BackgroundTaskBackend

backend = BackgroundTaskBackend(
    signing_secret="your-secret",
    max_retries=5,       # default: 3
    backoff_base=1.0,    # base delay in seconds
    backoff_max=60.0,    # delay cap in seconds
)
```

## Dead-Letter Hook
Use `on_failure` to capture permanently failed deliveries after all retries are exhausted.

Callback signature: `async on_failure(subscription, payload, error)`

### Built-in: InMemoryDeadLetterQueue
```python
from fastapihooks import InMemoryDeadLetterQueue
from fastapihooks.backends import BackgroundTaskBackend

dlq = InMemoryDeadLetterQueue(maxlen=1000)

backend = BackgroundTaskBackend(
    signing_secret="your-secret",
    on_failure=dlq,
)

# Inspect or drain failures at any time
for entry in dlq.entries:
    print(entry.subscription.target_url, entry.error)

failed = dlq.drain()  # returns all entries and clears the queue
```

### Custom callback
```python
async def my_failure_handler(subscription, payload, error):
    await db.insert_dead_letter(url=subscription.target_url, payload=payload, reason=str(error))
```

Common uses:
- Persist to a dead-letter database table.
- Emit metrics / trigger alerting.
- Re-queue for manual replay.

## Hardening Checklist
- Use per-environment signing secrets.
- Set realistic timeout budgets for subscribers.
- Track delivery failures by event and endpoint.
- Define subscriber retry ownership clearly.

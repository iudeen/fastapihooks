# 07. Security and Reliability

## Signature Format
Fasthooks signs payloads with HMAC-SHA256 when a signing secret is configured.

Header:
- X-Fasthooks-Signature: sha256=<hex_digest>

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
- Does not retry 4xx responses.
- Uses exponential backoff with jitter.

Parameters:
- max_retries
- backoff_base
- backoff_max

## Dead-Letter Hook
Use on_failure callback to capture permanently failed deliveries.

Callback signature:
- async on_failure(subscription, payload, error)

Common uses:
- Write to dead-letter queue.
- Emit metrics.
- Trigger alerting.

## Hardening Checklist
- Use per-environment signing secrets.
- Set realistic timeout budgets for subscribers.
- Track delivery failures by event and endpoint.
- Define subscriber retry ownership clearly.

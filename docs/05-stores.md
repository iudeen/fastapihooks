# 05. Stores

## BaseStore Contract
Stores manage webhook subscriptions by event name.

Required methods:
- add_subscription(...)
- remove_subscription(subscription_id)
- get_subscriptions(event_name)
- update_subscription(subscription_id, ...)

Optional method:
- get_subscription(subscription_id)

## Included Stores
- MemoryStore: in-memory implementation for development/testing.
- SQLStore: SQLAlchemy async store for relational databases.

## Subscription Model
WebhookSubscription fields:
- event_name
- target_url
- auth_type: bearer or none
- auth_value
- metadata

StoredWebhookSubscription adds:
- id

## Choosing a Store
Use MemoryStore when:
- local prototyping
- short-lived process
- test scenarios

Use SQLStore when:
- durable subscriptions are needed
- multiple instances share subscriptions
- operational visibility is required

## Custom Store Guidance
- Keep event_name indexing efficient.
- Use partial metadata merges for update paths.
- Validate target_url and auth constraints near write boundaries.

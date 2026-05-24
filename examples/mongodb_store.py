"""
MongoDB Store for Fasthooks
============================
A durable subscription store backed by MongoDB using the Motor async driver.

Install dependency:
    pip install motor

Usage:
    from examples.mongodb_store import MongoDBStore
    from fasthooks import Fasthooks
    from fasthooks.backends import BackgroundTaskBackend

    store = MongoDBStore(mongo_url="mongodb://localhost:27017", database="myapp")

    @asynccontextmanager
    async def lifespan(app):
        await store.init_indexes()   # call once at startup
        async with hooks:
            yield
        store.close()

    hooks = Fasthooks(
        backend=BackgroundTaskBackend(signing_secret="your-secret", store=store),
    )

Design notes:
- Each subscription is stored as a MongoDB document with a uuid4 string id.
- An index on event_name keeps get_subscriptions() fast even at scale.
- Metadata updates are merged (partial update), not replaced wholesale.
- close() calls client.close() — wire it into your app lifespan.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Literal

from fasthooks.stores import BaseStore, StoredWebhookSubscription

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError as e:
    raise ImportError(
        "motor is required for MongoDBStore. "
        "Install it with: pip install motor"
    ) from e


class MongoDBStore(BaseStore):
    """
    MongoDB-backed webhook subscription store using Motor.

    Args:
        mongo_url:   MongoDB connection URI.
        database:    Database name (default: fasthooks).
        collection:  Collection name (default: webhook_subscriptions).
    """

    def __init__(
        self,
        mongo_url: str = "mongodb://localhost:27017",
        database: str = "fasthooks",
        collection: str = "webhook_subscriptions",
    ) -> None:
        self._client = AsyncIOMotorClient(mongo_url)
        self._col = self._client[database][collection]

    async def init_indexes(self) -> None:
        """Create collection indexes. Call once at application startup."""
        await self._col.create_index("event_name")
        await self._col.create_index("id", unique=True)

    # ------------------------------------------------------------------
    # BaseStore interface
    # ------------------------------------------------------------------

    async def add_subscription(
        self,
        event_name: str,
        target_url: str,
        auth_type: Literal["bearer", "none"] = "none",
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        subscription_id = str(uuid.uuid4())
        await self._col.insert_one({
            "id": subscription_id,
            "event_name": event_name,
            "target_url": target_url,
            "auth_type": auth_type,
            "auth_value": auth_value,
            "metadata": metadata or {},
        })
        return subscription_id

    async def remove_subscription(self, subscription_id: str) -> bool:
        result = await self._col.delete_one({"id": subscription_id})
        return result.deleted_count > 0

    async def get_subscriptions(self, event_name: str) -> Iterable[StoredWebhookSubscription]:
        cursor = self._col.find({"event_name": event_name})
        return [
            self._to_model(doc)
            async for doc in cursor
        ]

    async def update_subscription(
        self,
        subscription_id: str,
        target_url: str | None = None,
        auth_type: Literal["bearer", "none"] | None = None,
        auth_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        doc = await self._col.find_one({"id": subscription_id})
        if not doc:
            return False

        updates: dict[str, Any] = {}
        if target_url is not None:
            updates["target_url"] = target_url
        if auth_type is not None:
            updates["auth_type"] = auth_type
        if auth_value is not None:
            updates["auth_value"] = auth_value
        if metadata is not None:
            # Merge — preserve existing keys not present in the update
            updates["metadata"] = {**doc.get("metadata", {}), **metadata}

        if updates:
            await self._col.update_one({"id": subscription_id}, {"$set": updates})
        return True

    async def get_subscription(self, subscription_id: str) -> StoredWebhookSubscription | None:
        doc = await self._col.find_one({"id": subscription_id})
        return self._to_model(doc) if doc else None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the MongoDB client. Call on application shutdown."""
        self._client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_model(doc: dict) -> StoredWebhookSubscription:
        return StoredWebhookSubscription(
            id=doc["id"],
            event_name=doc["event_name"],
            target_url=doc["target_url"],
            auth_type=doc["auth_type"],
            auth_value=doc.get("auth_value"),
            metadata=doc.get("metadata", {}),
        )

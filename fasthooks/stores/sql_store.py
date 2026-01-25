from typing import Any, Iterable, Literal, Optional

try:
    from sqlalchemy import JSON, Column, String, create_engine, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import declarative_base, sessionmaker
except ImportError:
    raise ImportError(
        "SQLAlchemy is required for SQLStore. Please install it with 'uv add sqlalchemy[asyncio]' or 'pip install sqlalchemy[asyncio]'"
    )

from fasthooks.stores.base_store import BaseStore, WebhookSubscription

Base = declarative_base()


class WebhookSubscriptionModel(Base):
    """SQLAlchemy model for webhook subscriptions."""

    __tablename__ = "webhook_subscriptions"

    id = Column(String, primary_key=True)
    event_name = Column(String, index=True)
    target_url = Column(String)
    auth_type = Column(String, default="none")
    auth_value = Column(String, nullable=True)
    metadata = Column(JSON, default=dict)

    def to_subscription(self) -> WebhookSubscription:
        return WebhookSubscription(
            id=self.id,
            event_name=self.event_name,
            target_url=self.target_url,
            auth_type=self.auth_type,
            auth_value=self.auth_value,
            metadata=self.metadata or {},
        )


class SQLStore(BaseStore):
    """SQL-based store using SQLAlchemy. Supports all databases SQLAlchemy supports (PostgreSQL, MySQL, SQLite, etc.)."""

    def __init__(self, database_url: str):
        """
        Initialize the SQL store.
        
        Args:
            database_url: Async SQLAlchemy database URL (e.g., 'postgresql+asyncpg://user:pass@localhost/db')
        """
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_db(self):
        """Initialize database schema. Call once at startup."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def add_subscription(
        self,
        event_name: str,
        target_url: str,
        auth_type: Literal["bearer", "none"] = "none",
        auth_value: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        import uuid

        subscription_id = str(uuid.uuid4())
        
        async with self.async_session() as session:
            db_subscription = WebhookSubscriptionModel(
                id=subscription_id,
                event_name=event_name,
                target_url=target_url,
                auth_type=auth_type,
                auth_value=auth_value,
                metadata=metadata or {},
            )
            session.add(db_subscription)
            await session.commit()
        
        return subscription_id

    async def remove_subscription(self, subscription_id: str) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                select(WebhookSubscriptionModel).where(
                    WebhookSubscriptionModel.id == subscription_id
                )
            )
            subscription = result.scalars().first()
            
            if subscription:
                await session.delete(subscription)
                await session.commit()
                return True
            
            return False

    async def get_subscriptions(
        self,
        event_name: str,
    ) -> Iterable[WebhookSubscription]:
        async with self.async_session() as session:
            query = select(WebhookSubscriptionModel).where(
                WebhookSubscriptionModel.event_name == event_name
            )
            result = await session.execute(query)
            subscriptions = result.scalars().all()
            
            return [sub.to_subscription() for sub in subscriptions]

    async def update_subscription(
        self,
        subscription_id: str,
        target_url: Optional[str] = None,
        auth_type: Optional[Literal["bearer", "none"]] = None,
        auth_value: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                select(WebhookSubscriptionModel).where(
                    WebhookSubscriptionModel.id == subscription_id
                )
            )
            subscription = result.scalars().first()
            
            if not subscription:
                return False
            
            if target_url is not None:
                subscription.target_url = target_url
            if auth_type is not None:
                subscription.auth_type = auth_type
            if auth_value is not None:
                subscription.auth_value = auth_value
            if metadata is not None:
                subscription.metadata = {**(subscription.metadata or {}), **metadata}
            
            await session.commit()
            return True

    async def get_subscription(self, subscription_id: str) -> Optional[WebhookSubscription]:
        async with self.async_session() as session:
            result = await session.execute(
                select(WebhookSubscriptionModel).where(
                    WebhookSubscriptionModel.id == subscription_id
                )
            )
            subscription = result.scalars().first()
            
            return subscription.to_subscription() if subscription else None

    async def close(self):
        """Close the database connection. Call at shutdown."""
        await self.engine.dispose()

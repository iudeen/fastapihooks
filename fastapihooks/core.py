import inspect
from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from fastapi import BackgroundTasks, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from fastapihooks.backends.base_backend import BaseBackend
from fastapihooks.stores.base_store import WebhookSubscription


class FastapihooksContext(BaseModel):
    """
    The type-safe container passed to user-defined 'transform' functions.
    """

    event_name: str
    owner_id: str | None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Raw data captured from the request/response cycle
    headers: dict[str, str] | None = None
    request_payload: Any | None = None
    response_payload: Any | None = None


class Fastapihooks:
    def __init__(
        self,
        backend: BaseBackend,
        store=None,
        owner_id: str | None = None,
        subscribers: dict[str, list[WebhookSubscription]] | None = None,
    ):
        self.backend = backend
        self.store = store
        self.owner_id = owner_id
        self.subscribers = subscribers or {}

    async def aclose(self) -> None:
        """Close backend resources. Call on application shutdown."""
        await self.backend.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    def hook(
        self,
        event_name: str,
        include_headers: bool = False,
        include_request: bool = False,
        include_response: bool = True,
        transform: Callable[[FastapihooksContext], Any] | None = None,
        owner_id_resolver: Callable[[Request], str | None] | None = None,
    ):
        def decorator(func):
            func_sig = inspect.signature(func)

            @wraps(func)
            async def wrapper(*args, request: Request = None, background_tasks: BackgroundTasks = None, **kwargs):
                owner_id_override = kwargs.get("owner_id")

                call_kwargs = {k: v for k, v in kwargs.items() if k in func_sig.parameters}
                if "request" in func_sig.parameters and request is not None:
                    call_kwargs.setdefault("request", request)
                if "background_tasks" in func_sig.parameters and background_tasks is not None:
                    call_kwargs.setdefault("background_tasks", background_tasks)
                if "owner_id" in func_sig.parameters and owner_id_override is not None:
                    call_kwargs.setdefault("owner_id", owner_id_override)

                # 1. Call the original endpoint function (sync or async)
                if inspect.iscoroutinefunction(func):
                    response_data = await func(*args, **call_kwargs)
                else:
                    response_data = await run_in_threadpool(lambda: func(*args, **call_kwargs))

                async def _emit_task():
                    if request is None and (include_headers or include_request):
                        raise RuntimeError("Fastapihooks requires 'request: Request' when headers or request body are included.")

                    owner_id: str | None = owner_id_override if owner_id_override is not None else self.owner_id
                    if owner_id_resolver is not None and request is not None:
                        resolved_owner = owner_id_resolver(request)
                        if resolved_owner is not None:
                            owner_id = resolved_owner

                    ctx = FastapihooksContext(
                        event_name=event_name,
                        owner_id=owner_id,
                        headers=dict(request.headers) if include_headers else None,
                        request_payload=await request.body() if include_request else None,
                        response_payload=response_data if include_response else None,
                    )

                    emitted_data = transform(ctx) if transform else ctx.response_payload

                    # Get direct subscribers for this event if available
                    direct_subscribers = self.subscribers.get(event_name, [])

                    # Let the backend handle all dispatch logic
                    await self.backend.publish(
                        event_name=event_name,
                        payload=emitted_data,
                        owner_id=owner_id,
                        subscribers=direct_subscribers if direct_subscribers else None,
                    )

                # 2. Offload the emit path to BackgroundTasks when available; otherwise run inline
                if background_tasks is not None:
                    background_tasks.add_task(_emit_task)
                else:
                    await _emit_task()
                return response_data
            return wrapper
        return decorator

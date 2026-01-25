from datetime import datetime, timezone
import inspect
from functools import wraps
from typing import Any, Callable, Dict, Optional

from fastapi import BackgroundTasks, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from fasthooks.backends.base_backend import BaseBackend


class FasthooksContext(BaseModel):
    """
    The type-safe container passed to user-defined 'transform' functions.
    """

    event_name: str
    owner_id: Optional[str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    # Raw data captured from the request/response cycle
    headers: Optional[Dict[str, str]] = None
    request_payload: Optional[Any] = None
    response_payload: Optional[Any] = None

    class Config:
        arbitrary_types_allowed = True


class Fasthooks:
    def __init__(self, backend: BaseBackend, store=None, owner_id: Optional[str] = None):
        self.backend = backend
        self.store = store
        self.owner_id = owner_id

    def hook(
        self,
        event_name: str,
        include_headers: bool = False,
        include_request: bool = False,
        include_response: bool = True,
        transform: Optional[Callable[[FasthooksContext], Any]] = None,
        owner_id_resolver: Optional[Callable[[Request], Optional[str]]] = None,
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
                        raise RuntimeError("Fasthooks requires 'request: Request' when headers or request body are included.")

                    owner_id: Optional[str] = owner_id_override if owner_id_override is not None else self.owner_id
                    if owner_id_resolver is not None and request is not None:
                        resolved_owner = owner_id_resolver(request)
                        if resolved_owner is not None:
                            owner_id = resolved_owner

                    ctx = FasthooksContext(
                        event_name=event_name,
                        owner_id=owner_id,
                        headers=dict(request.headers) if include_headers else None,
                        request_payload=await request.body() if include_request else None,
                        response_payload=response_data if include_response else None,
                    )

                    emitted_data = transform(ctx) if transform else ctx.response_payload

                    await self.backend.publish(
                        event_name=event_name,
                        payload=emitted_data,
                        owner_id=owner_id,
                    )

                # 2. Offload the emit path to BackgroundTasks when available; otherwise run inline
                if background_tasks is not None:
                    background_tasks.add_task(_emit_task)
                else:
                    await _emit_task()
                return response_data
            return wrapper
        return decorator
"""Helpers for agent tools."""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable


def offload_blocking_tools(tools: list[Any]) -> list[Any]:
    """Run synchronous function tools in a worker thread instead of the event loop.

    ADK calls a plain ``def`` tool right in the event loop. While a slow tool
    waits on the network, nothing else in the process runs: not other users'
    sessions, not ``/health``. A liveness probe that does not get an answer is
    a dead container.

    Each sync function is wrapped into an ``async def`` that awaits
    ``asyncio.to_thread``. ``functools.wraps`` keeps the name, docstring,
    annotations and ``__wrapped__``, so ADK builds exactly the same tool
    declaration for the model. Async functions and tool objects are returned
    as is.
    """
    return [_offload(t) if _is_sync_function(t) else t for t in tools]


def _is_sync_function(tool: Any) -> bool:
    return inspect.isfunction(tool) and not (
        inspect.iscoroutinefunction(tool) or inspect.isasyncgenfunction(tool))


def _offload(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper

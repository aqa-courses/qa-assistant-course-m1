"""Helpers for agent tools."""

from __future__ import annotations

import asyncio  # noqa: F401
import functools  # noqa: F401
import inspect  # noqa: F401
from typing import Any


def offload_blocking_tools(tools: list[Any]) -> list[Any]:
    """Run synchronous function tools in a worker thread instead of the event loop.

    ADK calls a plain ``def`` tool right in the event loop. While a slow tool
    waits on the network, nothing else in the process runs: not other users'
    sessions, not ``/health``.

    Async functions and tool objects must be returned as is. A sync function
    must come back as an ``async def`` that the model sees exactly like the
    original: same name, docstring and parameters.
    """
    # TODO М1.4 (homework): first reproduce the hang, see modules/m01/README.md. Then fix it here.
    return list(tools)

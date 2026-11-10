"""Helpers for keeping blocking work off the asyncio event loop.

Request handlers and the sync worker share one event loop per uvicorn
process. Several third-party clients this app uses are synchronous (the
Gemini SDK call, boto3, the Notion SDK, the rsvg-convert subprocess). Called
directly from a coroutine, each of them stops that loop, and with it every
other request and the sync worker, for as long as the call takes.
"""

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def run_off_loop(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Run an ``async def`` that does blocking I/O on a worker thread.

    Use this on coroutine methods whose body calls synchronous clients. The
    coroutine runs to completion on a thread from the default executor, in
    its own short-lived event loop, so the caller's loop stays free. The
    wrapped function must not use the caller's database session or anything
    else bound to the caller's thread or loop.

    Nested calls (a wrapped method calling another wrapped method) work; each
    hop just takes another thread.
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return await asyncio.to_thread(asyncio.run, func(*args, **kwargs))

    return wrapper

"""
The agent's single long-lived asyncio event loop.

The watcher, the sync queue worker, CloudSync and its one ``httpx.AsyncClient``
all live on this loop, which runs in one dedicated background thread for the
life of the agent. Other threads (Flask request threads, the watchdog thread,
the tray's main thread) never run coroutines themselves: they hand work to the
loop with ``submit()`` or ``call_soon()``.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AgentLoopNotRunningError(RuntimeError):
    """Work was handed to the agent loop while it is not running (not started or stopped)."""


class AgentLoopTimeoutError(TimeoutError):
    """AgentLoop.run() gave up waiting; the coroutine was cancelled."""


class AgentLoop:
    """Owns one asyncio event loop running in one background thread."""

    def __init__(self, name: str = "rmirror-agent-loop"):
        self._name = name
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._accepting = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the loop thread and wait until the loop is running. Starts only once."""
        with self._lock:
            if self._thread is not None:
                raise RuntimeError("AgentLoop can only be started once")
            loop = asyncio.new_event_loop()
            started = threading.Event()
            thread = threading.Thread(
                target=self._run, args=(loop, started), name=self._name, daemon=True
            )
            self._loop = loop
            self._thread = thread
            thread.start()
        started.wait()
        with self._lock:
            self._accepting = True

    def _run(self, loop: asyncio.AbstractEventLoop, started: threading.Event) -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(started.set)
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            except Exception as e:  # pragma: no cover - best effort during shutdown
                logger.debug(f"Error while finishing the agent loop: {e}")
            finally:
                loop.close()

    def stop(self, timeout: float = 10.0) -> None:
        """Cancel remaining tasks, stop the loop and join its thread.

        Safe to call more than once. Must not be called from the loop thread.
        """
        if self.in_loop_thread():
            raise RuntimeError("AgentLoop.stop() cannot be called from the loop thread")
        with self._lock:
            loop, thread = self._loop, self._thread
            was_accepting = self._accepting
            self._accepting = False
        if loop is None or thread is None:
            return

        if was_accepting and not loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(self._cancel_tasks(), loop)
                future.result(timeout=timeout)
            except Exception as e:
                logger.warning(f"Agent loop tasks did not finish cleanly: {e}")
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass  # Already closed
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("Agent loop thread did not stop in time")

    @staticmethod
    async def _cancel_tasks() -> None:
        current = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True between start() and stop()."""
        with self._lock:
            return self._accepting

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """The underlying event loop (for code that already runs on it)."""
        return self._loop

    def in_loop_thread(self) -> bool:
        """True when called from the loop's own thread."""
        thread = self._thread
        return thread is not None and threading.current_thread() is thread

    # ------------------------------------------------------------------
    # Hand-off from other threads
    # ------------------------------------------------------------------

    def submit(self, coro: Coroutine[Any, Any, T]) -> "concurrent.futures.Future[T]":
        """Schedule a coroutine on the loop from any thread and return a concurrent Future.

        Raises AgentLoopNotRunningError if the loop is not running (the coroutine is closed).
        """
        with self._lock:
            loop = self._loop if self._accepting else None
            if loop is not None:
                try:
                    return asyncio.run_coroutine_threadsafe(coro, loop)
                except RuntimeError:
                    pass  # Loop closed in the meantime
        coro.close()
        raise AgentLoopNotRunningError("The agent's event loop is not running")

    def call_soon(self, fn: Callable[..., object], *args: object) -> None:
        """Call a plain function on the loop thread soon. Safe from any thread."""
        with self._lock:
            loop = self._loop if self._accepting else None
            if loop is not None:
                try:
                    loop.call_soon_threadsafe(fn, *args)
                    return
                except RuntimeError:
                    pass
        raise AgentLoopNotRunningError("The agent's event loop is not running")

    def run(self, coro: Coroutine[Any, Any, T], timeout: float) -> T:
        """Run a coroutine on the loop and wait for its result from another thread.

        On timeout the coroutine is cancelled and ``AgentLoopTimeoutError`` is raised.
        """
        if self.in_loop_thread():
            coro.close()
            raise RuntimeError("AgentLoop.run() would deadlock when called from the loop thread")
        future = self.submit(coro)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise AgentLoopTimeoutError(f"Timed out after {timeout:g}s") from None

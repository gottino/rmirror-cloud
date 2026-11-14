"""
Tests for AgentLoop: the agent's one long-lived event loop thread.
"""

import asyncio
import gc
import logging
import threading
import warnings

import httpx
import pytest

from app.agent_loop import AgentLoop, AgentLoopNotRunningError, AgentLoopTimeoutError


@pytest.fixture
def agent_loop():
    loop = AgentLoop()
    loop.start()
    yield loop
    loop.stop()


class TestLifecycle:
    def test_submit_runs_on_the_loop_thread(self, agent_loop):
        async def where():
            return threading.current_thread(), asyncio.get_running_loop()

        thread, loop = agent_loop.submit(where()).result(timeout=5)
        assert thread is not threading.current_thread()
        assert thread.name == "rmirror-agent-loop"
        assert loop is agent_loop.loop

    def test_every_submit_uses_the_same_loop(self, agent_loop):
        async def current():
            return asyncio.get_running_loop()

        loops = {agent_loop.submit(current()).result(timeout=5) for _ in range(5)}
        assert loops == {agent_loop.loop}

    def test_call_soon_runs_function_on_loop_thread(self, agent_loop):
        seen = []
        done = threading.Event()

        def record(value):
            seen.append((value, agent_loop.in_loop_thread()))
            done.set()

        agent_loop.call_soon(record, 42)
        assert done.wait(5)
        assert seen == [(42, True)]

    def test_stop_joins_thread_and_closes_loop(self):
        agent_loop = AgentLoop()
        agent_loop.start()
        thread = agent_loop._thread
        agent_loop.stop()
        assert not thread.is_alive()
        assert agent_loop.loop.is_closed()
        assert agent_loop.is_running is False

    def test_stop_cancels_pending_tasks(self):
        agent_loop = AgentLoop()
        agent_loop.start()
        cancelled = threading.Event()

        async def forever():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        future = agent_loop.submit(forever())
        agent_loop.stop()
        assert cancelled.is_set()
        assert future.cancelled()

    def test_stop_is_idempotent(self):
        agent_loop = AgentLoop()
        agent_loop.start()
        agent_loop.stop()
        agent_loop.stop()

    def test_stop_before_start_is_a_no_op(self):
        AgentLoop().stop()

    def test_start_twice_is_refused(self, agent_loop):
        with pytest.raises(RuntimeError):
            agent_loop.start()

    def test_submit_after_stop_raises_clear_error(self):
        agent_loop = AgentLoop()
        agent_loop.start()
        agent_loop.stop()

        async def work():
            return 1

        coro = work()
        with pytest.raises(AgentLoopNotRunningError, match="not running"):
            agent_loop.submit(coro)
        # The coroutine was closed, so no "never awaited" warning later
        assert coro.cr_frame is None

    def test_submit_before_start_raises(self):
        async def work():
            return 1

        with pytest.raises(AgentLoopNotRunningError):
            AgentLoop().submit(work())

    def test_call_soon_after_stop_raises(self):
        agent_loop = AgentLoop()
        agent_loop.start()
        agent_loop.stop()
        with pytest.raises(AgentLoopNotRunningError):
            agent_loop.call_soon(print, "x")


class TestRun:
    def test_run_returns_result(self, agent_loop):
        async def add(a, b):
            await asyncio.sleep(0)
            return a + b

        assert agent_loop.run(add(2, 3), timeout=5) == 5

    def test_run_propagates_exceptions(self, agent_loop):
        async def boom():
            raise ValueError("bad")

        with pytest.raises(ValueError, match="bad"):
            agent_loop.run(boom(), timeout=5)

    def test_run_timeout_cancels_the_coroutine(self, agent_loop):
        cancelled = threading.Event()

        async def slow():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        with pytest.raises(AgentLoopTimeoutError):
            agent_loop.run(slow(), timeout=0.05)
        assert cancelled.wait(5)
        # The loop is still usable afterwards
        assert agent_loop.run(asyncio.sleep(0, result="ok"), timeout=5) == "ok"

    def test_run_from_loop_thread_is_refused(self, agent_loop):
        async def nested():
            inner = asyncio.sleep(0)
            with pytest.raises(RuntimeError, match="deadlock"):
                agent_loop.run(inner, timeout=1)
            return True

        assert agent_loop.run(nested(), timeout=5) is True


class TestSharedHttpClient:
    def test_client_used_from_many_threads_then_closed_cleanly(self, caplog):
        """One AsyncClient on the loop serves concurrent callers; shutdown leaves no loop errors."""
        agent_loop = AgentLoop()
        agent_loop.start()

        async def handler(request):
            await asyncio.sleep(0.01)
            return httpx.Response(200, json={"path": request.url.path})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        results = []
        errors = []

        def worker(i):
            try:
                response = agent_loop.run(client.get(f"http://backend.test/item/{i}"), timeout=5)
                results.append(response.json()["path"])
            except Exception as e:  # pragma: no cover - reported below
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)

        assert errors == []
        assert sorted(results) == sorted(f"/item/{i}" for i in range(16))

        with caplog.at_level(logging.DEBUG), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent_loop.run(client.aclose(), timeout=5)
            agent_loop.stop()
            gc.collect()

        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not [r for r in caplog.records if "Event loop is closed" in r.getMessage()]
        assert not [w for w in caught if "Event loop is closed" in str(w.message)]

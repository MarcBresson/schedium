from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime
from functools import partial

import pytest

from schedium import CancelJob, Job, Tick
from schedium import asyncio as asyncio_utils
from schedium.asyncio import AsyncScheduler
from schedium.scheduler import JobDidNotRunType


@pytest.mark.parametrize("kind", ["callable", "partial", "wrapper"])
@pytest.mark.parametrize("wait", [True, False])
def test_async_scheduler_awaits_callable_results(kind, wait):
    async def scenario():
        loop = asyncio.get_running_loop()
        calls = 0

        async def work():
            nonlocal calls
            assert asyncio.get_running_loop() is loop
            await asyncio.sleep(0)
            calls += 1
            return "done"

        class AsyncCallable:
            async def __call__(self):
                return await work()

        if kind == "callable":
            func = AsyncCallable()
        elif kind == "partial":
            func = partial(AsyncCallable())
        else:

            def func():
                return work()

        async_sched = AsyncScheduler(await_awaitable_results=kind == "wrapper")
        async_sched.append(Job(func, Tick("second")))
        now = datetime(2026, 2, 12, 12, 0, 0)
        results = await async_sched.run_pending(now=now, wait=wait)
        result = results[0] if wait else await results[0]
        if inspect.iscoroutine(result):
            result.close()

        assert result == "done"
        assert calls == 1
        repeated = await async_sched.run_pending(now=now, wait=wait)
        assert isinstance(repeated[0], JobDidNotRunType)

    asyncio.run(scenario())


@pytest.mark.parametrize("wait", [True, False])
def test_async_scheduler_removes_wrapped_async_cancelled_job(wait):
    async def scenario():
        async def cancel_me():
            return CancelJob("done")

        async_sched = AsyncScheduler(await_awaitable_results=True)
        async_sched.append(Job(lambda: cancel_me(), Tick("second")))
        results = await async_sched.run_pending(
            now=datetime(2026, 2, 12, 12, 0, 0), wait=wait
        )
        result = results[0] if wait else await results[0]
        if inspect.iscoroutine(result):
            result.close()

        assert isinstance(result, CancelJob)
        assert result.reason == "done"
        await asyncio.sleep(0)
        assert async_sched.jobs == []

    asyncio.run(scenario())


@pytest.mark.parametrize("wait", [True, False])
def test_async_scheduler_retries_wrapped_async_failure(wait):
    async def scenario():
        calls = 0

        async def work():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("job failed")
            return "recovered"

        async_sched = AsyncScheduler(
            revert_last_event_on_failure=True, await_awaitable_results=True
        )
        job = Job(lambda: work(), Tick("second"))
        async_sched.append(job)
        now = datetime(2026, 2, 12, 12, 0, 0)

        with pytest.raises(ValueError, match="job failed"):
            results = await async_sched.run_pending(now=now, wait=wait)
            result = results[0] if wait else await results[0]
            if inspect.iscoroutine(result):
                result.close()

        await asyncio.sleep(0)
        assert job.last_event is None
        results = await async_sched.run_pending(now=now, wait=wait)
        assert (results[0] if wait else await results[0]) == "recovered"
        assert calls == 2

    asyncio.run(scenario())


def test_async_callable_detection():
    async def async_func():
        return "done"

    class AsyncCallable:
        async def __call__(self):
            return "done"

    def sync_func():
        return async_func()

    class SyncCallable:
        def __call__(self):
            return "done"

    for func in (
        async_func,
        partial(async_func),
        AsyncCallable(),
        partial(AsyncCallable()),
    ):
        assert asyncio_utils._is_async_callable(func)
    for func in (
        sync_func,
        partial(sync_func),
        SyncCallable(),
        partial(SyncCallable()),
    ):
        assert not asyncio_utils._is_async_callable(func)
    assert not asyncio_utils._is_async_callable(object())


@pytest.mark.parametrize("kind", ["coroutine", "future", "custom"])
@pytest.mark.parametrize("wait", [True, False])
@pytest.mark.parametrize("opt_in", [True, False])
def test_async_scheduler_sync_awaitable_results_require_opt_in(kind, wait, opt_in):
    async def scenario():
        calls = 0

        async def work():
            nonlocal calls
            calls += 1
            return "done"

        class CustomAwaitable:
            def __await__(self):
                return work().__await__()

        if kind == "coroutine":
            returned = work()
        elif kind == "future":
            returned = asyncio.get_running_loop().create_future()
            returned.set_result("done")
        else:
            returned = CustomAwaitable()

        async_sched = (
            AsyncScheduler(await_awaitable_results=True) if opt_in else AsyncScheduler()
        )
        async_sched.append(Job(lambda: returned, Tick("second")))
        try:
            results = await async_sched.run_pending(
                now=datetime(2026, 2, 12, 12, 0, 0), wait=wait
            )
            result = results[0] if wait else await results[0]
            if opt_in:
                assert result == "done"
                assert calls == (0 if kind == "future" else 1)
            else:
                assert result is returned
                assert calls == 0
        finally:
            if inspect.iscoroutine(returned):
                returned.close()

    asyncio.run(scenario())


def test_async_scheduler_runs_due_jobs_concurrently():
    async def scenario():
        async_sched = AsyncScheduler()

        release = asyncio.Event()
        started_a = asyncio.Event()
        started_b = asyncio.Event()

        async def job_a():
            started_a.set()
            await asyncio.wait_for(release.wait(), timeout=2)
            return "a"

        async def job_b():
            started_b.set()
            await asyncio.wait_for(release.wait(), timeout=2)
            return "b"

        async_sched.append(Job(job_a, Tick("second"), name="a"))
        async_sched.append(Job(job_b, Tick("second"), name="b"))

        run = asyncio.ensure_future(
            async_sched.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))
        )

        await asyncio.wait_for(started_a.wait(), timeout=1)
        await asyncio.wait_for(started_b.wait(), timeout=1)

        release.set()
        results = await run

        assert results == ["a", "b"]

    asyncio.run(scenario())


def test_async_scheduler_runs_sync_jobs_without_blocking_the_loop():
    async def scenario():
        async_sched = AsyncScheduler()

        started = asyncio.Event()

        def blocking_job():
            time.sleep(0.2)
            return "blocked"

        progressed = False

        async def other_job():
            nonlocal progressed
            started.set()
            await asyncio.sleep(0.01)
            progressed = True
            return "other"

        async_sched.append(Job(blocking_job, Tick("second"), name="blocking"))
        async_sched.append(Job(other_job, Tick("second"), name="other"))

        results = await async_sched.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))

        assert results == ["blocked", "other"]
        assert progressed

    asyncio.run(scenario())


def test_async_scheduler_removes_cancelled_job_when_waiting():
    async def scenario():
        async_sched = AsyncScheduler()

        async def cancel_me():
            return CancelJob("done")

        async_sched.append(Job(cancel_me, Tick("second"), name="cancel"))

        results = await async_sched.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))

        assert isinstance(results[0], CancelJob)
        assert results[0].reason == "done"
        assert async_sched.jobs == []

    asyncio.run(scenario())


def test_async_scheduler_removes_cancelled_job_without_waiting():
    async def scenario():
        async_sched = AsyncScheduler()

        async def cancel_me():
            return CancelJob("done")

        async_sched.append(Job(cancel_me, Tick("second"), name="cancel"))

        results = await async_sched.run_pending(
            now=datetime(2026, 2, 12, 12, 0, 0), wait=False
        )

        task = results[0]
        assert not isinstance(task, JobDidNotRunType)
        result = await task
        assert isinstance(result, CancelJob)

        deadline = time.monotonic() + 1
        while async_sched.jobs and time.monotonic() < deadline:
            await asyncio.sleep(0.01)

        assert async_sched.jobs == []

    asyncio.run(scenario())


def test_async_scheduler_max_concurrency_serializes_jobs():
    async def scenario():
        active = 0
        max_active = 0

        async def job():
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1
            return "ok"

        async_sched = AsyncScheduler(max_concurrency=1)
        async_sched.append(Job(job, Tick("second"), name="a"))
        async_sched.append(Job(job, Tick("second"), name="b"))
        async_sched.append(Job(job, Tick("second"), name="c"))

        results = await async_sched.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))

        assert results == ["ok", "ok", "ok"]
        assert max_active == 1

    asyncio.run(scenario())


def test_async_scheduler_supports_direct_use_like_scheduler():
    async_sched = AsyncScheduler()
    job = Job(lambda: None, Tick("second"), name="only")
    async_sched.append(job)

    assert async_sched[0] is job
    assert async_sched.jobs == [job]

    next_run = async_sched.time_of_next_run(after=datetime(2026, 2, 12, 12, 0, 0))
    assert next_run is not None


def test_background_loop_task_cancels_cleanly():
    async def scenario():
        async_sched = AsyncScheduler()
        async_sched.append(Job(lambda: None, Tick("second"), name="job"))

        async def loop():
            while True:
                await async_sched.run_pending(wait=False)
                await asyncio.sleep(0.01)

        task = asyncio.create_task(loop())
        await asyncio.sleep(0.03)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_background_loop_task_surfaces_unexpected_errors():
    async def scenario():
        calls = 0

        async def loop():
            nonlocal calls
            while True:
                calls += 1
                if calls == 2:
                    raise RuntimeError("boom")
                await asyncio.sleep(0.01)

        task = asyncio.create_task(loop())

        with pytest.raises(RuntimeError, match="boom"):
            await task

    asyncio.run(scenario())


def test_background_loop_task_survives_a_failing_job_when_not_waiting():
    async def scenario():
        async_sched = AsyncScheduler()

        calls = 0

        async def flaky_job():
            nonlocal calls
            calls += 1
            raise RuntimeError("job bug")

        async_sched.append(Job(flaky_job, Tick("second"), name="flaky"))

        async def loop():
            while True:
                await async_sched.run_pending(wait=False)
                await asyncio.sleep(0.01)

        task = asyncio.create_task(loop())
        await asyncio.sleep(0.03)

        assert not task.done()
        assert calls >= 1

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

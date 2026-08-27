from __future__ import annotations

import asyncio
import time
from datetime import datetime

import pytest

from schedium import CancelJob, Job, Tick
from schedium.asyncio import AsyncScheduler
from schedium.scheduler import JobDidNotRunType


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

from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from datetime import datetime, timedelta

from schedium import CancelJob, Job, JobDidNotRun, Scheduler, Tick
from schedium.scheduler import JobDidNotRunType
from schedium.threading import (
    QueuedJobsScheduler,
    SchedulerThread,
    ThreadedJobsScheduler,
)


def test_threaded_scheduler_runs_due_jobs_concurrently():
    sched = Scheduler()

    release = threading.Event()
    started_a = threading.Event()
    started_b = threading.Event()

    def job_a():
        started_a.set()
        assert release.wait(2)
        return "a"

    def job_b():
        started_b.set()
        assert release.wait(2)
        return "b"

    sched.append(Job(job_a, Tick("second"), name="a"))
    sched.append(Job(job_b, Tick("second"), name="b"))

    threaded = ThreadedJobsScheduler(sched, max_workers=2)
    try:
        results = threaded.run_pending(now=datetime(2026, 2, 12, 12, 0, 0), wait=False)
        assert len(results) == 2
        assert results[0] is not JobDidNotRun
        assert results[1] is not JobDidNotRun

        fut_a = results[0]
        fut_b = results[1]

        assert not isinstance(fut_a, JobDidNotRunType)
        assert not isinstance(fut_b, JobDidNotRunType)
        assert started_a.wait(0.5)
        assert started_b.wait(0.5)

        release.set()
        assert fut_a.result(timeout=1) == "a"
        assert fut_b.result(timeout=1) == "b"
    finally:
        threaded.shutdown(wait=True)


def test_threaded_scheduler_async_removes_cancelled_job():
    sched = Scheduler()

    def cancel_me():
        return CancelJob("done")

    sched.append(Job(cancel_me, Tick("second"), name="cancel"))

    threaded = ThreadedJobsScheduler(sched, max_workers=1)
    try:
        results = threaded.run_pending(now=datetime(2026, 2, 12, 12, 0, 0), wait=False)
        fut = results[0]
        assert isinstance(fut, Future)
        res = fut.result(timeout=1)
        assert isinstance(res, CancelJob)
        assert res.reason == "done"

        # Callback runs at completion; give it a tiny slice.
        deadline = time.time() + 1
        while sched.jobs and time.time() < deadline:
            time.sleep(0.01)

        assert sched.jobs == []
    finally:
        threaded.shutdown(wait=True)


def test_scheduler_thread_runs_scheduler_in_background_thread():
    sched = Scheduler()
    threaded = ThreadedJobsScheduler(sched, max_workers=1)

    calls: list[int] = []
    done = threading.Event()

    def job():
        calls.append(1)
        if len(calls) >= 3:
            done.set()
        return None

    sched.append(Job(job, Tick("second"), name="job"))

    base = datetime(2026, 2, 12, 12, 0, 0)
    tick = 0
    tick_lock = threading.Lock()

    def now_func() -> datetime:
        nonlocal tick
        with tick_lock:
            dt = base + timedelta(seconds=tick)
            tick += 1
        return dt

    runner = SchedulerThread(threaded, interval=0.001, now_func=now_func)
    try:
        runner.start()
        assert done.wait(1.0)
    finally:
        runner.stop()
        runner.join(timeout=1.0)
        threaded.shutdown(wait=True)

    assert runner.exception is None
    assert len(calls) >= 3


def test_queued_jobs_scheduler_enqueues_and_workers_execute():
    sched = Scheduler()

    release = threading.Event()
    started_a = threading.Event()
    started_b = threading.Event()

    def job_a():
        started_a.set()
        assert release.wait(2)
        return "a"

    def job_b():
        started_b.set()
        assert release.wait(2)
        return "b"

    sched.append(Job(job_a, Tick("second"), name="a"))
    sched.append(Job(job_b, Tick("second"), name="b"))

    queued = QueuedJobsScheduler(sched, worker_count=2)
    try:
        results = queued.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))

        assert len(results) == 2
        fut_a = results[0]
        fut_b = results[1]

        assert not isinstance(fut_a, JobDidNotRunType)
        assert not isinstance(fut_b, JobDidNotRunType)
        assert started_a.wait(0.5)
        assert started_b.wait(0.5)

        release.set()
        assert fut_a.result(timeout=1) == "a"
        assert fut_b.result(timeout=1) == "b"
    finally:
        queued.stop_workers(join=True, timeout=1.0)


def test_queued_jobs_scheduler_removes_cancelled_job():
    sched = Scheduler()

    def cancel_me():
        return CancelJob("done")

    sched.append(Job(cancel_me, Tick("second"), name="cancel"))

    queued = QueuedJobsScheduler(sched, worker_count=1)
    try:
        results = queued.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))
        fut = results[0]
        assert isinstance(fut, Future)
        res = fut.result(timeout=1)
        assert isinstance(res, CancelJob)
        assert res.reason == "done"

        deadline = time.time() + 1
        while sched.jobs and time.time() < deadline:
            time.sleep(0.01)
        assert sched.jobs == []
    finally:
        queued.stop_workers(join=True, timeout=1.0)


def test_threaded_jobs_property_returns_copy():
    sched = Scheduler()
    threaded = ThreadedJobsScheduler(sched, max_workers=1)
    threaded.append(Job(lambda: None, Tick("second")))

    snapshot = threaded.jobs
    snapshot.clear()  # mutate the returned list

    # Before the fix .jobs returned the raw scheduler list; clear() would have
    # emptied it.  After the fix it returns a copy, so the scheduler is intact.
    assert len(threaded.jobs) == 1
    threaded.shutdown(wait=True)


def test_queued_jobs_property_returns_copy():
    sched = Scheduler()
    queued = QueuedJobsScheduler(sched, worker_count=1)
    queued.append(Job(lambda: None, Tick("second")))

    snapshot = queued.jobs
    snapshot.clear()

    assert len(queued.jobs) == 1
    queued.stop_workers(join=True)


def test_scheduler_thread_has_run_loop_method():
    sched = Scheduler()
    runner = SchedulerThread(sched)

    # Before the fix _run_loop was a local closure inside start() and did not
    # exist as an attribute.  After the fix it is a proper method.
    assert callable(getattr(runner, "_run_loop", None))

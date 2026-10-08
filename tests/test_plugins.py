from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from datetime import datetime
from typing import Any

import pytest

from schedium import (
    AsyncScheduler,
    CancelJob,
    Job,
    Plugin,
    QueuedJobsScheduler,
    RunContext,
    RunStatus,
    Scheduler,
    ThreadedJobsScheduler,
    Tick,
)
from schedium.plugins import get_current_run

NOW = datetime(2026, 2, 12, 12, 0, 0)


class Recorder(Plugin):
    """Records every hook call, and a snapshot of the run at that time."""

    def __init__(self, name: str = "rec", log: list | None = None) -> None:
        self.name = name
        self.log: list = log if log is not None else []
        self.runs: list[RunContext] = []
        self._lock = threading.Lock()

    def _add(self, *item) -> None:
        with self._lock:
            self.log.append(item)

    def on_scheduler_start(self, scheduler):
        self._add(self.name, "scheduler_start")

    def on_scheduler_stop(self, scheduler):
        self._add(self.name, "scheduler_stop")

    def on_job_added(self, scheduler, job):
        self._add(self.name, "added", job.identifier)

    def on_job_removed(self, scheduler, job, reason):
        self._add(self.name, "removed", reason)

    def on_job_start(self, run):
        self.runs.append(run)
        self._add(self.name, "start", run.status)

    def on_job_success(self, run):
        self._add(self.name, "success", run.result)

    def on_job_failure(self, run):
        self._add(self.name, "failure", type(run.exception).__name__)

    def on_job_cancelled(self, run):
        self._add(self.name, "cancelled", run.cancel_reason)

    def on_job_end(self, run):
        self._add(self.name, "end", run.status)

    def hooks(self, name: str | None = None) -> list[str]:
        return [i[1] for i in self.log if name is None or i[0] == name]


def make_job(func=lambda: "ok", **kwargs) -> Job:
    return Job(func, Tick("second"), **kwargs)


# --- Job -------------------------------------------------------------------


def test_job_identifier_fallbacks():
    def my_func():
        pass

    assert make_job(my_func, id="a", name="b").identifier == "a"
    assert make_job(my_func, name="b").identifier == "b"
    assert make_job(my_func).identifier.endswith(
        "test_job_identifier_fallbacks.<locals>.my_func"
    )
    from functools import partial

    assert make_job(partial(my_func)).identifier.endswith("my_func")


# --- hooks & ordering --------------------------------------------------------


def test_hooks_success_and_run_context():
    rec = Recorder()
    sched = Scheduler(plugins=[rec])
    sched.append(make_job(name="j"))
    assert sched.run_pending(NOW) == ["ok"]

    assert rec.hooks() == ["added", "start", "success", "end"]
    run = rec.runs[0]
    assert run.status is RunStatus.SUCCESS
    assert run.result == "ok"
    assert run.scheduler is sched
    assert run.scheduler_kind == "Scheduler"
    assert run.event is not None
    assert run.ended_at is not None and run.duration is not None and run.duration >= 0
    assert run.started_at.tzinfo is not None
    assert len(run.run_id) == 32


def test_hooks_failure_reraises_and_records():
    rec = Recorder()

    def boom():
        raise ValueError("nope")

    sched = Scheduler(plugins=[rec])
    sched.append(make_job(boom))
    with pytest.raises(ValueError, match="nope"):
        sched.run_pending(NOW)

    assert rec.hooks() == ["added", "start", "failure", "end"]
    assert rec.runs[0].status is RunStatus.FAILED
    assert isinstance(rec.runs[0].exception, ValueError)


def test_hooks_cancel_job():
    rec = Recorder()
    sched = Scheduler(plugins=[rec])
    sched.append(make_job(lambda: CancelJob("done")))
    sched.run_pending(NOW)

    assert rec.hooks() == ["added", "start", "cancelled", "end", "removed"]
    assert ("rec", "cancelled", "done") in rec.log
    assert ("rec", "removed", "done") in rec.log
    assert rec.runs[0].status is RunStatus.CANCELLED
    assert rec.runs[0].cancel_reason == "done"
    assert sched.jobs == []


# --- isolation ---------------------------------------------------------------


def test_observer_hook_crash_is_isolated(caplog):
    class Broken(Plugin):
        def on_job_start(self, run):
            raise RuntimeError("plugin bug")

        def on_job_end(self, run):
            raise RuntimeError("plugin bug 2")

    rec = Recorder()
    sched = Scheduler(plugins=[Broken(), rec])
    sched.append(make_job())
    with caplog.at_level("ERROR", logger="schedium.plugins"):
        assert sched.run_pending(NOW) == ["ok"]

    assert rec.hooks() == ["added", "start", "success", "end"]
    assert sum("failed in on_job_" in r.getMessage() for r in caplog.records) == 2


# --- wrap hooks ----------------------------------------------------------------


def test_wrap_run_retry():
    attempts = 0

    class Retry(Plugin):
        def wrap_run(self, run, call_next):
            for i in range(3):
                try:
                    return call_next()
                except RuntimeError:
                    if i == 2:
                        raise

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("flaky")
        return "finally"

    rec = Recorder()
    sched = Scheduler(plugins=[rec, Retry()])
    sched.append(make_job(flaky))
    assert sched.run_pending(NOW) == ["finally"]
    assert attempts == 3
    assert rec.runs[0].status is RunStatus.SUCCESS


def test_wrap_run_skip():
    class Skip(Plugin):
        def wrap_run(self, run, call_next):
            return "skipped-value"

    called = []
    rec = Recorder()
    sched = Scheduler(plugins=[rec, Skip()])
    sched.append(make_job(lambda: called.append(1)))
    assert sched.run_pending(NOW) == ["skipped-value"]
    assert called == []
    assert rec.runs[0].status is RunStatus.SKIPPED
    # SKIPPED has no dedicated hook, but on_job_end still fires exactly once
    assert rec.hooks() == ["added", "start", "end"]


# --- same behaviour on every scheduler -----------------------------------------


def run_on(kind: str, plugin: Plugin, job: Job) -> tuple[Any, list[Any]]:
    """Run ``job`` once on the requested scheduler kind and return results."""
    if kind == "sync":
        sync = Scheduler(plugins=[plugin])
        sync.append(job)
        return sync, sync.run_pending(NOW)
    if kind == "threaded":
        threaded = ThreadedJobsScheduler(plugins=[plugin])
        threaded.append(job)
        try:
            return threaded, threaded.run_pending(NOW, wait=True)
        finally:
            threaded.shutdown()
    if kind == "queued":
        queued = QueuedJobsScheduler(plugins=[plugin])
        queued.append(job)
        try:
            futures = queued.run_pending(NOW)
            return queued, [
                f.result(timeout=2) for f in futures if isinstance(f, Future)
            ]
        finally:
            queued.stop_workers()
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["sync", "threaded", "queued"])
def test_same_hooks_on_sync_and_threaded_schedulers(kind):
    rec = Recorder()
    sched, results = run_on(kind, rec, make_job(lambda: "ok", name="j"))
    assert results == ["ok"]
    assert [h for h in rec.hooks() if h in {"start", "success", "end"}] == [
        "start",
        "success",
        "end",
    ]
    run = rec.runs[0]
    assert run.status is RunStatus.SUCCESS
    assert run.scheduler is sched
    assert run.scheduler_kind == type(sched).__name__


async def test_same_hooks_on_async_scheduler():
    rec = Recorder()

    async def job():
        return "ok"

    sched = AsyncScheduler(plugins=[rec])
    sched.append(make_job(job))
    assert await sched.run_pending(NOW) == ["ok"]
    assert rec.hooks() == ["added", "start", "success", "end"]
    assert rec.runs[0].scheduler_kind == "AsyncScheduler"


@pytest.mark.parametrize("kind", ["threaded", "queued"])
def test_run_func_override_is_honoured_by_threaded_schedulers(kind):
    class Custom(Job):
        def run_func(self):
            return "custom"

    _, results = run_on(kind, Plugin(), Custom(lambda: "plain", Tick("second")))
    assert results == ["custom"]


# --- async wrap hook ---------------------------------------------------------


async def test_async_wrap_run_async():
    class Wrap(Plugin):
        async def wrap_run_async(self, run, call_next):
            return f"<{await call_next()}>"

    async def job():
        return "x"

    sched = AsyncScheduler(plugins=[Wrap()])
    sched.append(make_job(job))
    assert await sched.run_pending(NOW) == ["<x>"]


# --- lifecycle ------------------------------------------------------------------


async def test_async_scheduler_lifecycle_hooks():
    rec = Recorder()
    sched = AsyncScheduler(plugins=[rec])
    async with sched:
        await asyncio.sleep(0.01)
    assert rec.hooks() == ["scheduler_start", "scheduler_stop"]


# --- current run / contextvar -----------------------------------------------------


async def test_current_run_is_per_task_and_reaches_executor_threads():
    seen: dict[str, str | None] = {}
    barrier = threading.Barrier(2, timeout=2)

    def make(name):
        def job():
            # both jobs overlap in time, each must still see its own run
            barrier.wait()
            run = get_current_run()
            seen[name] = run.job.identifier if run else None

        return job

    sched = AsyncScheduler(plugins=[Plugin()])
    sched.append(Job(make("a"), Tick("second"), name="a"))
    sched.append(Job(make("b"), Tick("second"), name="b"))
    await sched.run_pending(NOW)
    assert seen == {"a": "a", "b": "b"}


# --- discovery -----------------------------------------------------------------


class _EP:
    def __init__(self, name, obj):
        self.name, self.value, self._obj = name, f"fake:{name}", obj

    def load(self):
        if isinstance(self._obj, Exception):
            raise self._obj
        return self._obj


def test_load_entry_point_plugins(monkeypatch, caplog):
    from schedium.plugins import discovery

    class A(Plugin): ...

    instance = Plugin()
    eps = [
        _EP("b-instance", instance),
        _EP("a-class", A),
        _EP("c-factory", lambda: A()),
        _EP("d-broken", ImportError("missing dep")),
        _EP("e-not-plugin", lambda: 42),
    ]
    monkeypatch.setattr(discovery, "entry_points", lambda group: eps)

    with caplog.at_level(logging.INFO, logger="schedium.plugins"):
        plugins = discovery.load_entry_point_plugins()

    assert [type(p) for p in plugins] == [A, Plugin, A]
    assert plugins[1] is instance
    assert sum(r.levelno == logging.ERROR for r in caplog.records) == 2

    only = discovery.load_entry_point_plugins(names=["b-instance"])
    assert only == [instance]

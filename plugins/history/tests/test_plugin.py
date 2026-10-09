import asyncio
import logging
import threading
from datetime import datetime, timedelta

import pytest
from schedium import (
    AsyncScheduler,
    CancelJob,
    Job,
    QueuedJobsScheduler,
    Scheduler,
    ThreadedJobsScheduler,
    Tick,
)
from schedium.plugins import RunStatus

from schedium_history import MemoryStore, Retention, HistoryPlugin

NOW = datetime(2026, 2, 12, 12, 0, 0)


def make_job(func=lambda: "ok", **kwargs) -> Job:
    return Job(func, Tick("second"), **kwargs)


def tick(i: int) -> datetime:
    return datetime(2026, 2, 12, 12, 0, i)


def test_success_is_recorded(store):
    scheduler = Scheduler(plugins=[HistoryPlugin(store)])
    job = make_job(name="greet", id="greet-v1")
    scheduler.append(job)
    scheduler.run_pending(NOW)

    [run] = store.get_runs()
    assert run.status is RunStatus.SUCCESS
    assert run.job_id == "greet-v1"
    assert run.job_name == "greet"
    assert run.scheduler == "Scheduler"
    assert run.started_at.tzinfo is not None
    assert run.ended_at is not None and run.ended_at >= run.started_at
    assert run.duration is not None and run.duration >= 0
    assert run.trigger == repr(job.trigger)
    assert run.event and "bucket" in run.event
    assert run.error is None and run.logs == []


def test_failure_records_error_with_traceback_and_still_raises(store):
    def boom():
        raise ValueError("kaput")

    scheduler = Scheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(boom))
    with pytest.raises(ValueError, match="kaput"):
        scheduler.run_pending(NOW)

    [run] = store.get_runs()
    assert run.status is RunStatus.FAILED
    assert run.error.type == "ValueError"
    assert run.error.message == "kaput"
    assert "Traceback" in run.error.traceback and "kaput" in run.error.traceback


def test_custom_exception_type_is_qualified():
    class MyError(Exception): ...

    def boom():
        raise MyError("x")

    store = MemoryStore()
    scheduler = Scheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(boom))
    with pytest.raises(MyError):
        scheduler.run_pending(NOW)
    assert store.get_runs()[0].error.type.endswith("MyError")


def test_cancel_job_reason_is_recorded(store):
    scheduler = Scheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(lambda: CancelJob("all done")))
    scheduler.run_pending(NOW)

    [run] = store.get_runs()
    assert run.status is RunStatus.CANCELLED
    assert run.cancel_reason == "all done"


def test_job_without_name_is_identified_by_function(store):
    def nightly_cleanup():
        pass

    scheduler = Scheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(nightly_cleanup))
    scheduler.run_pending(NOW)
    assert store.get_runs()[0].job_id.endswith("nightly_cleanup")
    assert store.get_runs()[0].job_name is None


def test_job_level_plugin_only_records_that_job():
    store = MemoryStore()
    scheduler = Scheduler()
    scheduler.append(make_job(name="traced", plugins=[HistoryPlugin(store)]))
    scheduler.append(make_job(name="untraced"))
    scheduler.run_pending(NOW)
    assert [r.job_id for r in store.get_runs()] == ["traced"]


def test_manual_job_run_is_recorded():
    store = MemoryStore()
    make_job(name="manual", plugins=[HistoryPlugin(store)]).run(NOW)
    assert store.get_runs()[0].scheduler == "manual"


def test_threaded_scheduler(store):
    threaded = ThreadedJobsScheduler(plugins=[HistoryPlugin(store)])
    threaded.append(make_job(name="j"))
    try:
        threaded.run_pending(NOW, wait=True)
    finally:
        threaded.shutdown()
    [run] = store.get_runs()
    assert (run.status, run.scheduler) == (RunStatus.SUCCESS, "ThreadedJobsScheduler")


def test_queued_scheduler(store):
    queued = QueuedJobsScheduler(plugins=[HistoryPlugin(store)])
    queued.append(make_job(name="j"))
    try:
        [future] = queued.run_pending(NOW)
        future.result(timeout=2)
    finally:
        queued.stop_workers()
    [run] = store.get_runs()
    assert (run.status, run.scheduler) == (RunStatus.SUCCESS, "QueuedJobsScheduler")


async def test_async_scheduler(store):
    async def job():
        return "ok"

    scheduler = AsyncScheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(job, name="j"))
    await scheduler.run_pending(NOW)
    [run] = store.get_runs()
    assert (run.status, run.scheduler) == (RunStatus.SUCCESS, "AsyncScheduler")


async def test_async_failure_and_sync_job_in_executor(store):
    def sync_boom():
        raise RuntimeError("in thread")

    scheduler = AsyncScheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(sync_boom, name="j"))
    with pytest.raises(RuntimeError):
        await scheduler.run_pending(NOW)
    [run] = store.get_runs()
    assert run.status is RunStatus.FAILED
    assert run.error.message == "in thread"


async def test_async_interrupted_run_is_recorded():
    store = MemoryStore()
    started = asyncio.Event()

    async def slow():
        started.set()
        await asyncio.sleep(10)

    scheduler = AsyncScheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(slow, name="slow"))
    [task] = await scheduler.run_pending(NOW, wait=False)
    await started.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert store.get_runs()[0].status is RunStatus.INTERRUPTED


def test_running_record_is_visible_while_job_runs(store):
    seen = []
    scheduler = Scheduler(plugins=[HistoryPlugin(store)])

    def job():
        seen.append([(r.status, r.ended_at) for r in store.get_runs()])

    scheduler.append(make_job(job))
    scheduler.run_pending(NOW)

    assert seen == [[(RunStatus.RUNNING, None)]]
    assert store.get_runs()[0].status is RunStatus.SUCCESS


def test_write_at_start_can_be_disabled():
    store = MemoryStore()
    seen = []
    scheduler = Scheduler(plugins=[HistoryPlugin(store, write_at_start=False)])
    scheduler.append(make_job(lambda: seen.append(len(store))))
    scheduler.run_pending(NOW)
    assert seen == [0]
    assert len(store) == 1


def test_store_failure_never_fails_the_job(caplog):
    class DownStore:
        def save(self, record):
            raise ConnectionError("db is down")

    scheduler = Scheduler(plugins=[HistoryPlugin(DownStore())])
    scheduler.append(make_job(lambda: "still ok"))
    with caplog.at_level("ERROR", logger="schedium.plugins"):
        assert scheduler.run_pending(NOW) == ["still ok"]
    assert "db is down" in caplog.text


def test_minimal_custom_store_is_enough():
    saved = []

    class Minimal:
        def save(self, record):
            saved.append((record.run_id, record.status))

    scheduler = Scheduler(plugins=[HistoryPlugin(Minimal())])
    scheduler.append(make_job())
    scheduler.run_pending(NOW)
    assert [s for _, s in saved] == [RunStatus.RUNNING, RunStatus.SUCCESS]
    assert len({run_id for run_id, _ in saved}) == 1


def test_retention_on_a_store_that_cannot_prune_warns(caplog):
    class Minimal:
        def save(self, record): ...

    with caplog.at_level("WARNING", logger="schedium_history.plugin"):
        HistoryPlugin(Minimal(), retention=Retention(max_runs_per_job=1))
    assert "no prune()" in caplog.text


def test_invalid_prune_every():
    with pytest.raises(ValueError):
        HistoryPlugin(MemoryStore(), prune_every=0)


def test_retention_is_applied_every_n_runs():
    store = MemoryStore()
    plugin = HistoryPlugin(
        store, retention=Retention(max_runs_per_job=2), prune_every=3
    )
    scheduler = Scheduler(plugins=[plugin])
    scheduler.append(make_job(name="j"))

    for i in range(2):
        scheduler.run_pending(tick(i))
    assert len(store) == 2
    scheduler.run_pending(tick(2))  # 3rd finished run triggers the pruning
    assert len(store) == 2
    for i in range(3, 5):
        scheduler.run_pending(tick(i))
    assert len(store) == 4  # 2 kept + 2 new: nothing is pruned until the 6th run
    scheduler.run_pending(tick(5))
    assert len(store) == 2


async def test_retention_is_applied_when_the_scheduler_stops():
    store = MemoryStore()
    plugin = HistoryPlugin(store, retention=Retention(max_runs_per_job=1))
    scheduler = AsyncScheduler(plugins=[plugin])

    async def job():
        pass

    scheduler.append(make_job(job, name="j"))
    for i in range(3):
        await scheduler.run_pending(tick(i))
    assert len(store) == 3
    await scheduler.stop()
    assert len(store) == 1


def test_max_age_retention_through_plugin():
    store = MemoryStore()
    plugin = HistoryPlugin(
        store, retention=Retention(max_age=timedelta(days=1)), prune_every=1
    )
    scheduler = Scheduler(plugins=[plugin])
    scheduler.append(make_job(name="j"))
    scheduler.run_pending(NOW)
    assert len(store) == 1  # just started: nothing is a day old


@pytest.fixture
def info_logging():
    root = logging.getLogger()
    previous = root.level
    root.setLevel(logging.DEBUG)
    yield
    root.setLevel(previous)


def logs_of(run):
    return [(e.level, e.logger, e.message) for e in run.logs]


def test_logs_are_not_captured_by_default(info_logging):
    store = MemoryStore()
    scheduler = Scheduler(plugins=[HistoryPlugin(store)])
    scheduler.append(make_job(lambda: logging.getLogger("app").info("hello")))
    scheduler.run_pending(NOW)
    assert store.get_runs()[0].logs == []


def test_stdlib_logs_are_captured_during_the_run_only(info_logging):
    store = MemoryStore()
    plugin = HistoryPlugin(store, capture_logging=True)
    log = logging.getLogger("app.worker")

    def job():
        log.info("processed %d rows", 12)
        log.debug("too chatty")  # below capture_level (INFO)
        log.warning("careful")
        try:
            raise KeyError("k")
        except KeyError:
            log.exception("it broke")

    scheduler = Scheduler(plugins=[plugin])
    scheduler.append(make_job(job))
    log.info("before the job")
    scheduler.run_pending(NOW)
    log.info("after the job")

    [run] = store.get_runs()
    levels = [(lvl, name, msg.splitlines()[0]) for lvl, name, msg in logs_of(run)]
    assert levels == [
        ("INFO", "app.worker", "processed 12 rows"),
        ("WARNING", "app.worker", "careful"),
        ("ERROR", "app.worker", "it broke"),
    ]
    assert "KeyError" in run.logs[-1].message  # exception info is kept
    plugin.close()


def test_capture_level_and_logger_names(info_logging):
    store = MemoryStore()
    plugin = HistoryPlugin(
        store,
        capture_logging=True,
        capture_level=logging.WARNING,
        capture_loggers=["only.this"],
    )

    def job():
        logging.getLogger("only.this").info("too low")
        logging.getLogger("only.this").warning("kept")
        logging.getLogger("other").warning("other logger")

    scheduler = Scheduler(plugins=[plugin])
    scheduler.append(make_job(job))
    scheduler.run_pending(NOW)
    assert [m for _, _, m in logs_of(store.get_runs()[0])] == ["kept"]
    plugin.close()


def test_handler_is_removed_when_the_scheduler_stops(info_logging):
    root = logging.getLogger()
    before = list(root.handlers)
    store = MemoryStore()
    plugin = HistoryPlugin(store, capture_logging=True)
    queued = QueuedJobsScheduler(plugins=[plugin])
    queued.append(make_job())
    [future] = queued.run_pending(NOW)
    future.result(timeout=2)
    assert len(root.handlers) == len(before) + 1
    queued.stop_workers()
    assert root.handlers == before
    plugin.close()  # idempotent


async def test_concurrent_async_jobs_get_only_their_own_logs(info_logging):
    store = MemoryStore()
    plugin = HistoryPlugin(store, capture_logging=True)
    gate = asyncio.Event()
    both_started = asyncio.Semaphore(0)

    def make(name):
        async def job():
            logging.getLogger("app").info("%s: start", name)
            both_started.release()
            await gate.wait()  # make sure the two runs overlap
            logging.getLogger("app").info("%s: end", name)

        return job

    scheduler = AsyncScheduler(plugins=[plugin])
    scheduler.append(make_job(make("a"), name="a"))
    scheduler.append(make_job(make("b"), name="b"))
    tasks = await scheduler.run_pending(NOW, wait=False)
    await both_started.acquire()
    await both_started.acquire()
    gate.set()
    await asyncio.gather(*tasks)

    by_job = {r.job_id: [m for _, _, m in logs_of(r)] for r in store.get_runs()}
    assert by_job == {"a": ["a: start", "a: end"], "b": ["b: start", "b: end"]}
    plugin.close()


async def test_sync_job_in_executor_has_its_logs_captured(info_logging):
    store = MemoryStore()
    plugin = HistoryPlugin(store, capture_logging=True)

    def job():
        logging.getLogger("app").info("from a worker thread")

    scheduler = AsyncScheduler(plugins=[plugin])
    scheduler.append(make_job(job, name="j"))
    await scheduler.run_pending(NOW)
    assert [m for _, _, m in logs_of(store.get_runs()[0])] == ["from a worker thread"]
    plugin.close()


def test_threaded_jobs_get_only_their_own_logs(info_logging):
    store = MemoryStore()
    plugin = HistoryPlugin(store, capture_logging=True)
    barrier = threading.Barrier(2, timeout=2)

    def make(name):
        def job():
            barrier.wait()  # both jobs are running at the same time
            logging.getLogger("app").info("hello from %s", name)

        return job

    threaded = ThreadedJobsScheduler(plugins=[plugin], max_workers=2)
    threaded.append(make_job(make("a"), name="a"))
    threaded.append(make_job(make("b"), name="b"))
    try:
        threaded.run_pending(NOW, wait=True)
    finally:
        threaded.shutdown()

    by_job = {r.job_id: [m for _, _, m in logs_of(r)] for r in store.get_runs()}
    assert by_job == {"a": ["hello from a"], "b": ["hello from b"]}
    plugin.close()


def test_two_history_plugins_capture_independently(info_logging):
    first, second = MemoryStore(), MemoryStore()
    p1 = HistoryPlugin(first, capture_logging=True)
    p2 = HistoryPlugin(second, capture_logging=True, capture_level=logging.ERROR)
    scheduler = Scheduler(plugins=[p1, p2])
    scheduler.append(
        make_job(
            lambda: [
                logging.getLogger("x").info("i"),
                logging.getLogger("x").error("e"),
            ]
        )
    )
    scheduler.run_pending(NOW)
    assert [m for _, _, m in logs_of(first.get_runs()[0])] == ["i", "e"]
    assert [m for _, _, m in logs_of(second.get_runs()[0])] == ["e"]
    p1.close()
    p2.close()

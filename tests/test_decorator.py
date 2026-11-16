from schedium import Every, Scheduler, default_scheduler
from schedium.plugins.base import Plugin


class _TagPlugin(Plugin):
    pass


def test_scheduler_add_job_decorator_registers_job() -> None:
    sched = Scheduler()

    @sched.add_job(Every(unit="second", interval=5))
    def cleanup() -> None:
        ...  # pragma: no cover

    assert len(sched.jobs) == 1
    assert sched.jobs[0].func is cleanup
    assert cleanup() is None  # decorator returns the function unchanged


def test_decorator_defaults_name_and_id_to_function_name() -> None:
    sched = Scheduler()

    @sched.add_job(Every(unit="second", interval=5))
    def my_task() -> None:
        ...  # pragma: no cover

    job = sched.jobs[0]
    assert job.name is None  # left to Job.identifier fallback
    assert job.identifier.endswith(".my_task")


def test_decorator_accepts_name_job_id_and_plugins() -> None:
    sched = Scheduler()
    plugin = _TagPlugin()

    @sched.add_job(
        Every(unit="second", interval=5),
        "cleanup",
        job_id="cleanup-id",
        plugins=[plugin],
    )
    def cleanup() -> None:
        ...  # pragma: no cover

    job = sched.jobs[0]
    assert job.name == "cleanup"
    assert job.id == "cleanup-id"
    assert job.plugins == [plugin]


def test_default_scheduler_add_job_decorator() -> None:
    @default_scheduler.add_job(Every(unit="second", interval=60), name="once-a-minute")
    def tick() -> None:
        ...  # pragma: no cover

    assert any(
        getattr(j.func, "__name__", None) == "tick" for j in default_scheduler.jobs
    )


def test_decorator_on_threading_schedulers() -> None:
    from schedium.threading import QueuedJobsScheduler, ThreadedJobsScheduler

    for make in (
        lambda: ThreadedJobsScheduler(Scheduler()),
        lambda: QueuedJobsScheduler(Scheduler()),
    ):
        sched = make()

        @sched.add_job(Every(unit="second", interval=5), name="tagged")
        def work() -> None:
            ...  # pragma: no cover

        jobs = sched.jobs
        assert len(jobs) == 1
        assert jobs[0].name == "tagged"
        assert work is not None


def test_decorator_on_async_scheduler() -> None:
    from schedium.asyncio import AsyncScheduler

    sched = AsyncScheduler()

    @sched.add_job(Every(unit="second", interval=5), job_id="a-1")
    def work() -> None:
        ...  # pragma: no cover

    assert len(sched.jobs) == 1
    assert sched.jobs[0].id == "a-1"

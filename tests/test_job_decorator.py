from __future__ import annotations

from datetime import datetime

from schedium import Every, Scheduler


def test_add_job_decorator_registers_the_function():
    sched = Scheduler()

    calls: list[int] = []

    @sched.add_job(Every(unit="minute", interval=1))
    def my_job():
        calls.append(1)
        return "done"

    assert len(sched.jobs) == 1
    assert sched.jobs[0].func is my_job

    # The registered job actually runs.
    results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    assert results == ["done"]
    assert calls == [1]


def test_add_job_defaults_name_and_id_to_function_name():
    sched = Scheduler()

    @sched.add_job(Every(unit="minute", interval=1))
    def my_task():
        pass

    assert sched.jobs[0].name == "my_task"
    assert sched.jobs[0].id == "my_task"
    assert sched.jobs[0].identifier == "my_task"


def test_add_job_accepts_explicit_name_and_id():
    sched = Scheduler()

    @sched.add_job(
        Every(unit="minute", interval=1),
        "Pretty label",
        id="stable-id",
    )
    def my_task():
        pass

    assert sched.jobs[0].name == "Pretty label"
    assert sched.jobs[0].id == "stable-id"


def test_add_job_plugins_default_to_empty_and_can_be_given():
    sched = Scheduler()

    @sched.add_job(Every(unit="minute", interval=1))
    def my_task():
        pass

    assert sched.jobs[0].plugins == []


def test_decorated_function_stays_callable_and_stackable():
    sched = Scheduler()

    def tag(func):
        func.tagged = True
        return func

    @sched.add_job(Every(unit="minute", interval=1))
    @tag
    def my_task():
        return 42

    # The decorator returns the function unchanged, so other decorators still work.
    assert my_task.tagged
    assert my_task() == 42


def test_add_job_can_decorate_several_functions():
    sched = Scheduler()

    @sched.add_job(Every(unit="minute", interval=1), "first")
    def first():
        return 1

    @sched.add_job(Every(unit="minute", interval=1), "second")
    def second():
        return 2

    assert [job.name for job in sched.jobs] == ["first", "second"]
    assert [job.func.__name__ for job in sched.jobs] == ["first", "second"]
    assert first() == 1
    assert second() == 2

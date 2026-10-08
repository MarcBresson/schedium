"""
Shared execution core used by every scheduler.

All schedulers (sync, async, threaded, queued) and :meth:`Job.run
<schedium.job.Job.run>` execute a job through :func:`run_sync` or
:func:`run_async`. That is the single place where plugin hooks fire, so plugins
behave the same whatever scheduler runs the job.

This module is internal: its API may change without notice.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from schedium.plugins.base import Plugin
from schedium.plugins.context import RunContext, RunStatus, _current_run
from schedium.types.cancel_job import CancelJob

if TYPE_CHECKING:
    from schedium.job import Job
    from schedium.triggers.base import TriggerEvent

logger = logging.getLogger("schedium.plugins")


class PluginHost:
    """
    Mixin giving a scheduler a list of plugins.

    The list is available as ``plugins`` once ``_init_plugins`` has been called
    by the scheduler's ``__init__``.
    """

    plugins: list[Plugin]

    def _init_plugins(self, plugins: Sequence[Plugin] | None) -> None:
        self.plugins = list(plugins) if plugins else []

    def add_plugin(self, plugin: Plugin) -> None:
        """
        Attach a plugin to this scheduler.

        It applies to every job of the scheduler, including jobs already
        registered. Scheduler plugins run before job plugins.

        Parameters
        ----------
        plugin : Plugin
            The plugin to attach.
        """
        self.plugins.append(plugin)

    def remove_plugin(self, plugin: Plugin) -> None:
        """
        Detach a plugin from this scheduler.

        Parameters
        ----------
        plugin : Plugin
            The plugin to detach.

        Raises
        ------
        ValueError
            If the plugin is not attached.
        """
        self.plugins.remove(plugin)

    def _effective_plugins(self) -> list[Plugin]:
        """Snapshot of the plugins that apply to jobs run by this scheduler."""
        return list(self.plugins)


def _notify(plugins: Sequence[Plugin], hook: str, *args: Any) -> None:
    for plugin in plugins:
        try:
            getattr(plugin, hook)(*args)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Plugin %r failed in %s", plugin, hook)


async def _notify_async(plugins: Sequence[Plugin], hook: str, *args: Any) -> None:
    for plugin in plugins:
        try:
            fn = getattr(plugin, hook)
            if plugin.blocking:
                await asyncio.to_thread(fn, *args)
            else:
                fn(*args)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Plugin %r failed in %s", plugin, hook)


def notify(plugins: Sequence[Plugin], hook: str, *args: Any) -> None:
    """
    Call an observer hook on plugins, isolating failures.

    Parameters
    ----------
    plugins : Sequence[Plugin]
        Plugins to notify, in order.
    hook : str
        Name of the hook method.
    *args : Any
        Arguments for the hook.
    """
    _notify(plugins, hook, *args)


async def notify_async(plugins: Sequence[Plugin], hook: str, *args: Any) -> None:
    """
    Call an observer hook on plugins from a coroutine, isolating failures.

    Plugins marked ``blocking`` run in a worker thread.

    Parameters
    ----------
    plugins : Sequence[Plugin]
        Plugins to notify, in order.
    hook : str
        Name of the hook method.
    *args : Any
        Arguments for the hook.
    """
    await _notify_async(plugins, hook, *args)


def all_plugins(scheduler_plugins: Sequence[Plugin], job: Job) -> list[Plugin]:
    # scheduler plugins (outermost) followed by the job's own plugins
    job_plugins = getattr(job, "plugins", ())
    return [*scheduler_plugins, *job_plugins]


def overrides_run_func(job: Job) -> bool:
    # whether the job's class customises ``run_func``
    from schedium.job import Job as _Job

    return getattr(type(job), "run_func", None) is not _Job.run_func


def _kind(scheduler: object | None) -> str:
    return "manual" if scheduler is None else type(scheduler).__name__


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _finish_ok(run: RunContext, result: object, called: bool) -> None:
    run.result = result
    if isinstance(result, CancelJob):
        run.status = RunStatus.CANCELLED
        run.cancel_reason = result.reason
    elif not called:
        run.status = RunStatus.SKIPPED
    else:
        run.status = RunStatus.SUCCESS


def _finish_error(run: RunContext, exc: BaseException) -> None:
    run.exception = exc
    run.status = (
        RunStatus.FAILED if isinstance(exc, Exception) else RunStatus.INTERRUPTED
    )


_OUTCOME_HOOKS = {
    RunStatus.SUCCESS: "on_job_success",
    RunStatus.FAILED: "on_job_failure",
    RunStatus.CANCELLED: "on_job_cancelled",
}


def _wrapping(plugins: Sequence[Plugin], method: str) -> list[Plugin]:
    base = getattr(Plugin, method)
    return [p for p in plugins if getattr(type(p), method, base) is not base]


def run_sync(
    job: Job,
    *,
    scheduler: object | None = None,
    plugins: Sequence[Plugin] = (),
    event: TriggerEvent | None = None,
) -> object:
    """
    Execute a job synchronously, firing plugin hooks around it.

    Parameters
    ----------
    job : Job
        The job to run.
    scheduler : object, optional
        The scheduler running the job (None for a manual run).
    plugins : Sequence[Plugin]
        Plugins of the scheduler; the job's own plugins are appended.
    event : TriggerEvent, optional
        The trigger event that made the job due.

    Returns
    -------
    object
        The job's return value (possibly altered by ``wrap_run`` hooks).

    Raises
    ------
    BaseException
        Whatever the job (or a wrap hook) raised, unchanged.
    """
    chain = all_plugins(plugins, job)
    if not chain:
        return job.run_func()

    run = RunContext(
        job=job, scheduler=scheduler, scheduler_kind=_kind(scheduler), event=event
    )
    token = _current_run.set(run)
    called = False

    def innermost() -> object:
        nonlocal called
        called = True
        return job.run_func()

    call: Callable[[], object] = innermost
    for plugin in reversed(_wrapping(chain, "wrap_run")):
        call = _bind_sync(plugin, run, call)

    try:
        _notify(chain, "on_job_start", run)
        try:
            result = call()
        except BaseException as exc:
            run.ended_at = _utcnow()
            _finish_error(run, exc)
            hook = _OUTCOME_HOOKS.get(run.status)
            if hook:
                _notify(chain[::-1], hook, run)
            raise
        else:
            run.ended_at = _utcnow()
            _finish_ok(run, result, called)
            hook = _OUTCOME_HOOKS.get(run.status)
            if hook:
                _notify(chain[::-1], hook, run)
            return result
        finally:
            _notify(chain[::-1], "on_job_end", run)
    finally:
        _current_run.reset(token)


def _bind_sync(
    plugin: Plugin, run: RunContext, nxt: Callable[[], object]
) -> Callable[[], object]:
    def call() -> object:
        return plugin.wrap_run(run, nxt)

    return call


def _bind_async(
    plugin: Plugin, run: RunContext, nxt: Callable[[], Awaitable[object]]
) -> Callable[[], Awaitable[object]]:
    async def call() -> object:
        return await plugin.wrap_run_async(run, nxt)

    return call


async def run_async(
    job: Job,
    call_job: Callable[[], Awaitable[object]],
    *,
    scheduler: object | None = None,
    plugins: Sequence[Plugin] = (),
    event: TriggerEvent | None = None,
) -> object:
    """
    Execute a job on the event loop, firing plugin hooks around it.

    Parameters
    ----------
    job : Job
        The job to run.
    call_job : Callable[[], Awaitable[object]]
        Coroutine function that actually runs the job (awaiting it, or running
        it in an executor).
    scheduler : object, optional
        The scheduler running the job.
    plugins : Sequence[Plugin]
        Plugins of the scheduler; the job's own plugins are appended.
    event : TriggerEvent, optional
        The trigger event that made the job due.

    Returns
    -------
    object
        The job's return value (possibly altered by ``wrap_run_async`` hooks).

    Raises
    ------
    BaseException
        Whatever the job (or a wrap hook) raised, unchanged. This includes
        :class:`asyncio.CancelledError`.
    """
    chain = all_plugins(plugins, job)
    if not chain:
        return await call_job()

    run = RunContext(
        job=job, scheduler=scheduler, scheduler_kind=_kind(scheduler), event=event
    )
    token = _current_run.set(run)
    called = False

    async def innermost() -> object:
        nonlocal called
        called = True
        return await call_job()

    call: Callable[[], Awaitable[object]] = innermost
    for plugin in reversed(_wrapping(chain, "wrap_run_async")):
        call = _bind_async(plugin, run, call)

    try:
        await _notify_async(chain, "on_job_start", run)
        try:
            result = await call()
        except BaseException as exc:
            run.ended_at = _utcnow()
            _finish_error(run, exc)
            hook = _OUTCOME_HOOKS.get(run.status)
            if hook:
                await _notify_async(chain[::-1], hook, run)
            raise
        else:
            run.ended_at = _utcnow()
            _finish_ok(run, result, called)
            hook = _OUTCOME_HOOKS.get(run.status)
            if hook:
                await _notify_async(chain[::-1], hook, run)
            return result
        finally:
            await _notify_async(chain[::-1], "on_job_end", run)
    finally:
        _current_run.reset(token)

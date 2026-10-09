"""The schedium plugin that records run traces."""

import logging
import threading
import traceback
from collections.abc import Iterable

from schedium.plugins import Plugin, RunContext

from schedium_history.logcapture import LogCaptureHandler
from schedium_history.models import ErrorInfo, Retention, RunRecord
from schedium_history.protocols import PrunableStore, TraceStore

logger = logging.getLogger(__name__)


def _qualified_name(exc: BaseException) -> str:
    cls = type(exc)
    if cls.__module__ == "builtins":
        return cls.__qualname__
    return f"{cls.__module__}.{cls.__qualname__}"


class HistoryPlugin(Plugin):
    """
    Remember what happened to every job run.

    For each run it records when it started and stopped, its status, the error
    (with traceback) if it failed, the reason if the job cancelled itself, the
    trigger that made it due and, optionally, the logs emitted while it ran. Traces
    go to the ``store`` you choose: :class:`~schedium_history.MemoryStore`,
    :class:`~schedium_history.JSONLStore`, :class:`~schedium_history.SQLAlchemyStore`
    or your own.

    Parameters
    ----------
    store : TraceStore
        Where to save traces. Any object with a ``save(record)`` method works.
        If it also has ``prune``, ``retention`` can be applied.
    capture_logging : bool, default False
        Attach to each run the log records emitted while it runs, through the
        standard :mod:`logging` module, without changing your jobs.
    capture_level : int, default logging.INFO
        Minimum level of the captured records.
    capture_loggers : Iterable[str], optional
        Names of the loggers to capture. By default the root logger, which sees
        everything that propagates to it.
    write_at_start : bool, default True
        Save a ``running`` record as soon as the job starts. A process that dies
        mid-run then leaves a record that never finishes, which makes crashes
        visible. Costs one extra write per run.
    retention : Retention, optional
        Limits on the history kept. Applied every ``prune_every`` finished runs
        and when the scheduler stops.
    prune_every : int, default 100
        Number of finished runs between two prunings.

    Attributes
    ----------
    store : TraceStore
        The backend traces are saved to.

    Notes
    -----
    Log capture and levels
        A record is only captured if it reaches the handler, so it must pass the
        level of the logger that emitted it. The root logger defaults to
        ``WARNING``: call ``logging.basicConfig(level=logging.INFO)`` (or set the
        level of your own loggers) to see ``INFO`` records. Threads that a job
        starts itself do not inherit the run and are not captured; tasks created
        with :func:`asyncio.create_task` are.

    Failures
        An error while saving a trace (database down, disk full) is logged on the
        ``schedium.plugins`` logger and never fails the job.

    Examples
    --------
    >>> from schedium import Every, Job, Scheduler
    >>> from schedium_history import MemoryStore, HistoryPlugin
    >>> store = MemoryStore()
    >>> scheduler = Scheduler(plugins=[HistoryPlugin(store)])
    >>> scheduler.append(Job(lambda: "hi", Every(unit="second", interval=1), name="greet"))
    >>> _ = scheduler.run_pending()
    >>> [(run.job_id, run.status.value) for run in store.get_runs()]
    [('greet', 'success')]
    """

    blocking = True

    def __init__(
        self,
        store: TraceStore,
        *,
        capture_logging: bool = False,
        capture_level: int = logging.INFO,
        capture_loggers: Iterable[str] | None = None,
        write_at_start: bool = True,
        retention: Retention | None = None,
        prune_every: int = 100,
    ) -> None:
        if prune_every < 1:
            raise ValueError("prune_every must be >= 1")
        if retention is not None and not isinstance(store, PrunableStore):
            logger.warning(
                "%s has no prune() method: the retention policy will not be applied",
                type(store).__name__,
            )

        self.store = store
        self.capture_logging = capture_logging
        self.capture_level = capture_level
        self.capture_loggers: list[str | None] = (
            list(capture_loggers) if capture_loggers else [None]
        )
        self.write_at_start = write_at_start
        self.retention = retention
        self.prune_every = prune_every

        self._key = f"schedium_history:{id(self)}"
        self._lock = threading.Lock()
        self._finished = 0
        self._handler: LogCaptureHandler | None = None

    def _install_handler(self) -> None:
        with self._lock:
            if self._handler is not None:
                return
            handler = LogCaptureHandler(self._key, self.capture_level)
            for name in self.capture_loggers:
                target = logging.getLogger(name)
                target.addHandler(handler)
            self._handler = handler

    def close(self) -> None:
        """
        Stop capturing logs.

        Called automatically when a scheduler stops. Capturing resumes by itself
        the next time a job starts. Safe to call several times.
        """
        with self._lock:
            handler, self._handler = self._handler, None
        if handler is not None:
            for name in self.capture_loggers:
                logging.getLogger(name).removeHandler(handler)

    def on_job_start(self, run: RunContext) -> None:
        """
        Create the run's record and, by default, save it as ``running``.

        Parameters
        ----------
        run : RunContext
            The run that is starting.
        """
        job = run.job
        record = RunRecord(
            run_id=run.run_id,
            job_id=job.identifier,
            job_name=job.name,
            scheduler=run.scheduler_kind,
            status=run.status,
            started_at=run.started_at,
            trigger=repr(job.trigger),
            event=None if run.event is None else repr(run.event.token),
        )
        run.extras[self._key] = record

        if self.capture_logging:
            self._install_handler()
        if self.write_at_start:
            self.store.save(record)

    def on_job_end(self, run: RunContext) -> None:
        """
        Complete the run's record and save it.

        Parameters
        ----------
        run : RunContext
            The finished run.
        """
        record = run.extras.pop(self._key, None)
        if not isinstance(record, RunRecord):
            return

        record.status = run.status
        record.ended_at = run.ended_at
        record.cancel_reason = run.cancel_reason
        if run.exception is not None:
            exc = run.exception
            record.error = ErrorInfo(
                type=_qualified_name(exc),
                message=str(exc),
                traceback="".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ),
            )

        try:
            self.store.save(record)
        finally:
            self._after_run()

    def on_scheduler_stop(self, scheduler: object) -> None:
        """
        Apply the retention policy and stop capturing logs.

        Parameters
        ----------
        scheduler : object
            The scheduler that stopped.
        """
        self.close()
        self._prune()

    def _after_run(self) -> None:
        if self.retention is None:
            return
        with self._lock:
            self._finished += 1
            due = self._finished % self.prune_every == 0
        if due:
            self._prune()

    def _prune(self) -> None:
        if self.retention is None or self.retention.is_empty:
            return
        if isinstance(self.store, PrunableStore):
            deleted = self.store.prune(self.retention)
            if deleted:
                logger.debug("Pruned %d old run(s)", deleted)

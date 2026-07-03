from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Literal, overload

from schedium.job import Job
from schedium.scheduler import JobDidNotRun, JobDidNotRunType, Scheduler
from schedium.triggers.base import TriggerEvent
from schedium.types.cancel_job import CancelJob
from schedium.utils.evaluate import evaluate

logger = logging.getLogger(__name__)


def _done_callback(
    fut: Future[object],
    *,
    _scheduler: ThreadedJobsScheduler,
    _job: Job,
    _event: TriggerEvent,
    _prev: TriggerEvent | None,
) -> None:
    try:
        result = fut.result()
    except BaseException:
        logger.exception("Threaded job %r raised", _job)
        _scheduler._maybe_revert_last_event(
            _job,
            claimed_event=_event,
            previous_event=_prev,
        )
        return

    if isinstance(result, CancelJob):
        _scheduler._remove_job_if_present(_job)


class ThreadedJobsScheduler:
    """
    Run due jobs concurrently using a thread pool.

    in other words, each job will be executed in a separate thread.

    This is an helper that wraps a regular :class:`~schedium.scheduler.Scheduler`.

    Key difference vs. :meth:`schedium.scheduler.Scheduler.run_pending`:

    - When a job is due, this wrapper *claims* the trigger token immediately (by
      updating ``job.last_event``) before dispatching ``job.func`` to a worker thread.
      This prevents duplicate submissions when the scheduler loop runs again while a
      job is still executing.

    Parameters
    ----------
    scheduler : schedium.scheduler.Scheduler, optional
        An optional scheduler to wrap. If omitted, a new empty scheduler is used.
    max_workers : int | None, default None
        Passed to :class:`concurrent.futures.ThreadPoolExecutor`.
    thread_name_prefix : str, default "schedium-job"
        Prefix used for worker thread names.
    revert_last_event_on_failure : bool, default False
        If True, and a job raises an exception, ``job.last_event`` is reverted to its
        previous value so the job may be retried within the same token on a subsequent
        call.

    Notes
    -----
    Thread safety
        This wrapper guards access to ``scheduler.jobs`` and ``job.last_event``.
        You should register/remove jobs either before starting threads, or by using
        the same instance and avoiding concurrent mutation from user threads.

    CancelJob handling
        If a job returns :class:`~schedium.types.cancel_job.CancelJob`, the job is
        removed from the underlying scheduler.

    Examples
    --------
    Run due jobs in a worker pool while you keep control of the main loop

    >>> import time
    >>> from datetime import datetime
    >>> from schedium import Every, Job, JobDidNotRun, Scheduler
    >>> from schedium.threading import ThreadedJobsScheduler
    >>> sched = Scheduler()
    >>> sched.append(Job(lambda: "ok", Every(unit="second", interval=1)))
    >>> threaded = ThreadedJobsScheduler(sched, max_workers=4)
    >>> futures = threaded.run_pending(now=datetime(2026, 2, 12, 12, 0, 0), wait=False)
    >>> [f.result(timeout=1) for f in futures if f is not JobDidNotRun]
    ['ok']
    >>> threaded.shutdown()
    """

    def __init__(
        self,
        scheduler: Scheduler | None = None,
        *,
        max_workers: int | None = None,
        thread_name_prefix: str = "schedium-job",
        revert_last_event_on_failure: bool = False,
    ) -> None:
        self.scheduler = scheduler or Scheduler()

        self.max_workers = max_workers
        self.thread_name_prefix = thread_name_prefix
        self.revert_last_event_on_failure = revert_last_event_on_failure

        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix=self.thread_name_prefix,
        )

    def append(self, job: Job) -> None:
        with self._lock:
            self.scheduler.append(job)

    @property
    def jobs(self) -> list[Job]:
        """Access the underlying job list."""
        with self._lock:
            return list(self.scheduler.jobs)

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        """
        Shut down the worker pool.

        Parameters
        ----------
        wait : bool, default True
            If True, block until all running jobs complete. If False, return immediately
            and let running jobs complete in the background.
        cancel_futures : bool, default False
            If True, attempt to cancel pending jobs that have not yet started. This does
            not affect already running jobs.
        """

        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def _remove_job_if_present(self, job: Job) -> None:
        with self._lock:
            try:
                self.scheduler.jobs.remove(job)
            except ValueError:
                return

    def _maybe_revert_last_event(
        self,
        job: Job,
        *,
        claimed_event: TriggerEvent,
        previous_event: TriggerEvent | None,
    ) -> None:
        if not self.revert_last_event_on_failure:
            return
        with self._lock:
            if job.last_event == claimed_event:
                job.last_event = previous_event

    def _claim_due_event(
        self,
        job: Job,
        now: datetime,
    ) -> tuple[bool, TriggerEvent | None, TriggerEvent | None]:
        event = evaluate(job.trigger, now)
        if event is None:
            return False, None, None
        with self._lock:
            previous_event = job.last_event
            if event == previous_event:
                return False, event, previous_event
            job.last_event = event
        return True, event, previous_event

    @overload
    def run_pending(
        self,
        now: datetime | None = None,
        *,
        wait: Literal[False],
        timeout: float | None = None,
    ) -> list[JobDidNotRunType | Future[object]]: ...

    @overload
    def run_pending(
        self,
        now: datetime | None = None,
        *,
        wait: Literal[True],
        timeout: float | None = None,
    ) -> list[object]: ...

    def run_pending(
        self,
        now: datetime | None = None,
        *,
        wait: bool = False,
        timeout: float | None = None,
    ) -> list[JobDidNotRunType | Future[object]] | list[object]:
        """
        Run due jobs in worker threads.

        Parameters
        ----------
        now : datetime | None, optional
            Timestamp used to evaluate triggers. Defaults to ``datetime.now()``.
        wait : bool, default False
            If True, block and return concrete results (like ``Scheduler.run_pending``).
            If False, return :class:`~concurrent.futures.Future` for due jobs.
        timeout : float | None, default None
            Timeout (seconds) used when waiting for each job future.

        Returns
        -------
        list[JobDidNotRunType | Future[object]]
            A list aligned with the scheduler's job snapshot.

            - Not due -> :obj:`schedium.scheduler.JobDidNotRun`
            - Due + wait=False -> :class:`concurrent.futures.Future`
            - Due + wait=True -> the job's return value
        """

        now_dt = now if now is not None else datetime.now()

        with self._lock:
            jobs_snapshot = list(self.scheduler.jobs)

        pending: list[JobDidNotRunType | Future[object]] = []
        futures_to_job: dict[
            Future[object],
            tuple[Job, TriggerEvent, TriggerEvent | None],
        ] = {}

        for job in jobs_snapshot:
            claimed, event, prev_event = self._claim_due_event(job, now_dt)
            if not claimed or event is None:
                pending.append(JobDidNotRun)
                continue

            future: Future[object] = self._executor.submit(job.func)
            futures_to_job[future] = (job, event, prev_event)

            if not wait:
                _done_callback_partial = partial(
                    _done_callback,
                    _scheduler=self,
                    _job=job,
                    _event=event,
                    _prev=prev_event,
                )
                future.add_done_callback(_done_callback_partial)

            pending.append(future)

        if not wait:
            return pending

        results: list[object] = []
        for item in pending:
            if item is JobDidNotRun:
                results.append(JobDidNotRun)
                continue

            # make type checkers happy. This is not completely equivalent to
            # item is JobDidNotRun because of the possibility of multiple
            # JobDidNotRun instances.
            assert not isinstance(item, JobDidNotRunType)

            future = item
            job, event, prev_event = futures_to_job[future]
            try:
                result = future.result(timeout=timeout)
            except BaseException:
                self._maybe_revert_last_event(
                    job,
                    claimed_event=event,
                    previous_event=prev_event,
                )
                raise

            results.append(result)
            if isinstance(result, CancelJob):
                self._remove_job_if_present(job)

        return results


_STOP = object()


@dataclass(frozen=True)
class _QueueWorkItem:
    job: Job
    future: Future[object]
    claimed_event: TriggerEvent
    previous_event: TriggerEvent | None


class QueuedJobsScheduler:
    """
    Run the scheduler in the main thread, dispatch due jobs via a queue to workers.

    This helper is useful when you want the *scheduler loop* to remain in the main
    thread (or any single thread you control), while job execution is handled by one
    or more worker threads consuming a queue.

    Compared to :class:`~schedium.threading.ThreadedJobsScheduler`, this does not
    use :class:`concurrent.futures.ThreadPoolExecutor`. Instead, it maintains:

    - a producer step (your call to :meth:`run_pending`) that enqueues due jobs, and
    - worker threads that consume and execute the queued jobs.

    Parameters
    ----------
    scheduler : schedium.scheduler.Scheduler, optional
        Scheduler holding the jobs.
    worker_count : int, default 1
        Number of worker threads consuming the job queue.
    queue_ : queue.Queue | None, default None
        Queue to use for job queue. If None, a new ``queue.Queue`` is created.
    thread_name_prefix : str, default "schedium-worker"
        Prefix for worker thread names.
    revert_last_event_on_failure : bool, default False
        If True and a job raises, reverts ``job.last_event`` to the previous value
        so it may be retried for the same token.

    Examples
    --------
    Keep scheduling decisions in your thread, but execute jobs on worker threads

    >>> import queue
    >>> from datetime import datetime
    >>> from schedium import Every, Job, JobDidNotRun, Scheduler
    >>> from schedium.threading import QueuedJobsScheduler
    >>> sched = Scheduler()
    >>> sched.append(Job(lambda: "ok", Every(unit="second", interval=1)))
    >>> q = queue.Queue(maxsize=100)
    >>> queued = QueuedJobsScheduler(sched, worker_count=2, queue_=q)
    >>> futures = queued.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))
    >>> [f.result(timeout=1) for f in futures if f is not JobDidNotRun]
    ['ok']
    >>> queued.stop_workers(join=True)
    """

    def __init__(
        self,
        scheduler: Scheduler | None = None,
        *,
        worker_count: int = 1,
        queue_: queue.Queue | None = None,
        thread_name_prefix: str = "schedium-worker",
        revert_last_event_on_failure: bool = False,
    ) -> None:
        if worker_count < 1:
            raise ValueError("worker_count must be >= 1")

        self.scheduler = scheduler or Scheduler()
        self.worker_count = worker_count
        self.thread_name_prefix = thread_name_prefix
        self.revert_last_event_on_failure = revert_last_event_on_failure

        self._lock = threading.RLock()
        self._queue: queue.Queue = queue_ if queue_ is not None else queue.Queue()
        self._workers: list[threading.Thread] = []
        self._started = False

    def append(self, job: Job) -> None:
        with self._lock:
            self.scheduler.append(job)

    @property
    def jobs(self) -> list[Job]:
        with self._lock:
            return list(self.scheduler.jobs)

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return

            assert isinstance(item, _QueueWorkItem)
            work = item
            try:
                if not work.future.set_running_or_notify_cancel():
                    # If cancelled before starting, revert the claim so it can
                    # be scheduled again.
                    self._maybe_revert_last_event(
                        work.job,
                        claimed_event=work.claimed_event,
                        previous_event=work.previous_event,
                    )
                    continue

                try:
                    result = work.job.func()
                except BaseException as exc:
                    logger.exception("Queued job %r raised", work.job)
                    self._maybe_revert_last_event(
                        work.job,
                        claimed_event=work.claimed_event,
                        previous_event=work.previous_event,
                    )
                    work.future.set_exception(exc)
                    continue

                work.future.set_result(result)

                if isinstance(result, CancelJob):
                    self._remove_job_if_present(work.job)
            finally:
                self._queue.task_done()

    def start_workers(self) -> None:
        if self._started:
            return
        self._started = True

        for i in range(self.worker_count):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"{self.thread_name_prefix}-{i}",
                daemon=True,
            )
            self._workers.append(thread)
            thread.start()

    def stop_workers(self, *, join: bool = True, timeout: float | None = None) -> None:
        if not self._started:
            return

        for _ in range(len(self._workers)):
            self._queue.put(_STOP)

        if join:
            for t in self._workers:
                t.join(timeout=timeout)

        self._workers.clear()
        self._started = False

    def _remove_job_if_present(self, job: Job) -> None:
        with self._lock:
            try:
                self.scheduler.jobs.remove(job)
            except ValueError:
                return

    def _maybe_revert_last_event(
        self,
        job: Job,
        *,
        claimed_event: TriggerEvent,
        previous_event: TriggerEvent | None,
    ) -> None:
        if not self.revert_last_event_on_failure:
            return
        with self._lock:
            if job.last_event == claimed_event:
                job.last_event = previous_event

    def _claim_due_event(
        self,
        job: Job,
        now: datetime,
    ) -> tuple[bool, TriggerEvent | None, TriggerEvent | None]:
        event = evaluate(job.trigger, now)
        if event is None:
            return False, None, None
        with self._lock:
            previous_event = job.last_event
            if event == previous_event:
                return False, event, previous_event
            job.last_event = event
        return True, event, previous_event

    def run_pending(
        self,
        now: datetime | None = None,
        *,
        block: bool = True,
        queue_timeout: float | None = None,
    ) -> list[JobDidNotRunType | Future[object]]:
        """
        Enqueue due jobs and return Futures aligned with the job snapshot.

        Parameters
        ----------
        now : datetime | None, optional
            Timestamp used to evaluate triggers. Defaults to ``datetime.now()``.
        block : bool, default True
            If True, block if the queue is full until a free slot is available. If False, raise ``queue.Full`` if the queue is full.
        queue_timeout : float | None, default None
            Timeout (seconds) used when blocking to enqueue. If None, block indefinitely.
        """

        if not self._started:
            self.start_workers()

        now_dt = now if now is not None else datetime.now()

        with self._lock:
            jobs_snapshot = list(self.scheduler.jobs)

        results: list[JobDidNotRunType | Future[object]] = []
        for job in jobs_snapshot:
            claimed, event, prev_event = self._claim_due_event(job, now_dt)
            if not claimed or event is None:
                results.append(JobDidNotRun)
                continue

            future: Future[object] = Future()
            work = _QueueWorkItem(
                job=job,
                future=future,
                claimed_event=event,
                previous_event=prev_event,
            )

            try:
                self._queue.put(work, block=block, timeout=queue_timeout)
            except queue.Full:
                # Couldn't enqueue; revert token claim so it can be scheduled later.
                self._maybe_revert_last_event(
                    job,
                    claimed_event=event,
                    previous_event=prev_event,
                )
                raise

            results.append(future)

        return results


class SchedulerThread:
    """
    Run a already-initialized scheduler loop in a dedicated thread.

    Parameters
    ----------
    scheduler : schedium.scheduler.Scheduler | schedium.utils.threading.ThreadedJobsScheduler
        Scheduler-like object providing ``run_pending``.
    interval : float, default 1.0
        Sleep interval between calls to ``run_pending``.
    name : str, default "schedium-scheduler"
        Background thread name.
    daemon : bool, default True
        Whether the scheduler thread is a daemon.
    now_func : Callable[[], datetime] | None, default None
        If provided, used as the ``now=...`` argument passed to ``run_pending``.
        Useful for deterministic testing.

    Notes
    -----
    If ``scheduler`` is a :class:`~schedium.utils.threading.ThreadedJobsScheduler`, the
    loop calls ``run_pending(wait=False)`` so jobs run on the worker pool while the
    scheduler thread keeps ticking.

    Examples
    --------
    Run the scheduler loop in a background thread

    >>> import time
    >>> from schedium import Every, Job, Scheduler
    >>> from schedium.threading import SchedulerThread, ThreadedJobsScheduler
    >>> sched = Scheduler()
    >>> sched.append(Job(lambda: None, Every(unit="second", interval=1)))
    >>> threaded = ThreadedJobsScheduler(sched, max_workers=2)
    >>> runner = SchedulerThread(threaded, interval=0.1)
    >>> runner.start()
    >>> time.sleep(0.2)
    >>> runner.stop(); runner.join()
    >>> threaded.shutdown()
    """

    def __init__(
        self,
        scheduler: Scheduler | ThreadedJobsScheduler,
        *,
        interval: float = 1.0,
        name: str = "schedium-scheduler",
        daemon: bool = True,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.interval = max(interval, 0)
        self.name = name
        self.daemon = daemon
        self.now_func = now_func

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.exception: BaseException | None = None

    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                now = self.now_func() if self.now_func is not None else None
                if isinstance(self.scheduler, ThreadedJobsScheduler):
                    self.scheduler.run_pending(now=now, wait=False)
                else:
                    self.scheduler.run_pending(now=now)

                time.sleep(self.interval)
        except BaseException as exc:
            self.exception = exc
            raise

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self.exception = None

        self._thread = threading.Thread(
            target=self._run_loop, name=self.name, daemon=self.daemon
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is None:
            return
        self._thread.join(timeout=timeout)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

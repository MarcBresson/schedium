from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from functools import wraps
from typing import ParamSpec

from schedium.types.cancel_job import CancelJob


def _normalize_catch(
    catch: type[BaseException] | Iterable[type[BaseException]],
) -> tuple[type[BaseException], ...]:
    """
    Make sure the catch argument is always a tuple of exception types.

    Parameters
    ----------
    catch : type[BaseException] | Iterable[type[BaseException]]
        Either a single exception type or an iterable of exception types.

    Returns
    -------
    tuple[type[BaseException], ...]
        A tuple of exception types to catch.
    """
    if isinstance(catch, type) and issubclass(catch, BaseException):
        return (catch,)
    return tuple(catch)


P = ParamSpec("P")


def cancel_job_on_failure(
    *,
    cancel: bool = True,
    catch: type[BaseException] | Iterable[type[BaseException]] = Exception,
    logger: logging.Logger | None = None,
    log_message: str = "job failed",
    cancel_reason: str | None = None,
) -> Callable[[Callable[P, object]], Callable[P, object]]:
    """
    Decorator that logs specified exceptions and optionally cancels the job.

    - If the wrapped callable raises an exception that matches ``catch``:
      - the exception is logged (with traceback),
      - the exception is suppressed,
      - if ``cancel=True`` the wrapper returns :class:`~schedium.types.cancel_job.CancelJob`
        so :meth:`schedium.scheduler.Scheduler.run_pending` removes the job.
    - If an exception does not match ``catch``, it propagates.

    Parameters
    ----------
    cancel : bool, default True
        If True, a caught exception results in returning :class:`~schedium.types.cancel_job.CancelJob`.
        The scheduler will remove the job. If False, the exception is logged and
        suppressed but the wrapper returns None (job remains scheduled).
    catch : type[BaseException] | Iterable[type[BaseException]], default Exception
        Exception type (or tuple/iterable of types) to catch and handle.
        Exceptions not matching ``catch`` are not intercepted.
    logger : logging.Logger | None, default None
        Logger to use. If None, uses ``logging.getLogger(func.__module__)``.
    log_message : str, default "job failed"
        Message passed to ``logger.exception`` when a caught exception occurs.
    cancel_reason : str | None, default None
        Optional cancellation reason stored in the returned ``CancelJob(reason=...)``.
        If omitted, the reason is derived from the exception as
        ``"<ExceptionType>: <message>"``.

    Returns
    -------
    Callable[[Callable[P, object]], Callable[P, object]]
        A decorator that wraps ``func``.

        - On success: returns ``func(*args, **kwargs)``.
        - On caught exception: logs, suppresses, and returns either ``None`` or
          ``CancelJob(...)`` depending on ``cancel``.

    Notes
    -----
    - This decorator is most useful for jobs executed via
      :meth:`schedium.scheduler.Scheduler.run_pending`.
    - If you suppress exceptions (either by setting ``cancel=False`` or by
      returning ``CancelJob``), the job is treated as having completed for that
      trigger token, so it will not be retried within the same bucket.

    Examples
    --------
    Cancel the job after a known fatal error

    >>> import logging
    >>> from schedium import Every, Job, Scheduler
    >>> from schedium.utils import cancel_job_on_failure
    >>> logger = logging.getLogger(__name__)
    >>> @cancel_job_on_failure(catch=(ValueError,), cancel=True, logger=logger)
    ... def task():
    ...     raise ValueError("boom")
    >>> sched = Scheduler()
    >>> sched.append(Job(task, Every(unit="minute", interval=1)))
    """

    catch_tuple = _normalize_catch(catch)
    if not catch_tuple:
        raise ValueError("catch must include at least one exception type")

    def decorator(func: Callable[P, object]) -> Callable[P, object]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
            try:
                return func(*args, **kwargs)
            except catch_tuple as exc:
                log = logger or logging.getLogger(func.__module__)
                log.exception(log_message)

                if not cancel:
                    return None

                if cancel_reason is None:
                    reason = f"{type(exc).__name__}: {exc}"
                else:
                    reason = cancel_reason

                return CancelJob(reason=reason)

        return wrapper

    return decorator

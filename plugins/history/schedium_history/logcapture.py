"""Attach the log records emitted during a run to that run's trace."""

import logging
from datetime import datetime, timezone

from schedium.plugins import get_current_run

from schedium_history.models import LogEntry, RunRecord

_formatter = logging.Formatter()


class LogCaptureHandler(logging.Handler):
    """
    Logging handler that files each record under the run it was emitted in.

    The run is found with :func:`schedium.plugins.get_current_run`, which is
    tracked per thread and per asyncio task, so jobs that overlap in time never
    receive each other's logs. Records emitted outside any job are ignored.

    Parameters
    ----------
    key : str
        The key under which the plugin stores its :class:`RunRecord` in
        ``RunContext.extras``.
    level : int, default logging.INFO
        Minimum level of the records to keep.
    """

    def __init__(self, key: str, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self.key = key

    def emit(self, record: logging.LogRecord) -> None:
        run = get_current_run()
        if run is None:
            return
        trace = run.extras.get(self.key)
        if not isinstance(trace, RunRecord):
            return

        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{_formatter.formatException(record.exc_info)}"
            trace.logs.append(
                LogEntry(
                    timestamp=datetime.fromtimestamp(record.created, timezone.utc),
                    level=record.levelname,
                    logger=record.name,
                    message=message,
                )
            )
        except Exception:  # pylint: disable=broad-except
            self.handleError(record)

"""Records describing one job run, and the retention policy for old ones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from schedium.plugins import RunStatus


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass
class LogEntry:
    """
    One log record emitted while a job was running.

    Attributes
    ----------
    timestamp : datetime
        When the record was emitted, timezone-aware UTC.
    level : str
        Level name, such as ``"INFO"``.
    logger : str
        Name of the logger that emitted it.
    message : str
        The formatted message, followed by the traceback when the record had
        exception information.
    """

    timestamp: datetime
    level: str
    logger: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": _as_utc(self.timestamp).isoformat(),
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogEntry:
        return cls(
            timestamp=_as_utc(datetime.fromisoformat(data["timestamp"])),
            level=data["level"],
            logger=data["logger"],
            message=data["message"],
        )


@dataclass
class ErrorInfo:
    """
    The exception that made a run fail.

    Attributes
    ----------
    type : str
        Qualified exception class name (``"ValueError"``, ``"my_pkg.MyError"``).
    message : str
        ``str(exception)``.
    traceback : str, optional
        The formatted traceback.
    """

    type: str
    message: str
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "message": self.message, "traceback": self.traceback}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorInfo:
        return cls(
            type=data["type"], message=data["message"], traceback=data.get("traceback")
        )


@dataclass
class RunRecord:
    """
    The trace of one execution of a job.

    A record is first saved when the run starts (with status
    :attr:`~schedium.plugins.RunStatus.RUNNING`, unless ``write_at_start`` is
    disabled) and saved again, under the same :attr:`run_id`, when it ends.
    A record that stays ``RUNNING`` forever belongs to a process that died
    mid-run.

    Attributes
    ----------
    run_id : str
        Unique identifier of the run.
    job_id : str
        :attr:`schedium.job.Job.identifier` of the job.
    job_name : str, optional
        The job's ``name``, if any.
    scheduler : str
        Class name of the scheduler that ran it (``"manual"`` for ``Job.run``).
    status : RunStatus
        Outcome of the run.
    started_at : datetime
        When the run started, timezone-aware UTC.
    ended_at : datetime, optional
        When it ended, timezone-aware UTC. None while running.
    trigger : str, optional
        ``repr`` of the job's trigger.
    event : str, optional
        ``repr`` of the trigger event token (for instance the minute bucket)
        that made the job due.
    error : ErrorInfo, optional
        The exception, for failed runs.
    cancel_reason : str, optional
        The reason given to ``CancelJob``, for cancelled runs.
    logs : list[LogEntry]
        Log records captured during the run (empty unless ``capture_logging``
        is enabled).
    """

    run_id: str
    job_id: str
    scheduler: str
    status: RunStatus
    started_at: datetime
    job_name: str | None = None
    ended_at: datetime | None = None
    trigger: str | None = None
    event: str | None = None
    error: ErrorInfo | None = None
    cancel_reason: str | None = None
    logs: list[LogEntry] = field(default_factory=list)

    @property
    def duration(self) -> float | None:
        """Run duration in seconds, or None while the run is going."""
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "job_name": self.job_name,
            "scheduler": self.scheduler,
            "status": self.status.value,
            "started_at": _as_utc(self.started_at).isoformat(),
            "ended_at": None
            if self.ended_at is None
            else _as_utc(self.ended_at).isoformat(),
            "trigger": self.trigger,
            "event": self.event,
            "error": None if self.error is None else self.error.to_dict(),
            "cancel_reason": self.cancel_reason,
            "logs": [entry.to_dict() for entry in self.logs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        error = data.get("error")
        ended_at = data.get("ended_at")
        return cls(
            run_id=data["run_id"],
            job_id=data["job_id"],
            job_name=data.get("job_name"),
            scheduler=data["scheduler"],
            status=RunStatus(data["status"]),
            started_at=_as_utc(datetime.fromisoformat(data["started_at"])),
            ended_at=None
            if ended_at is None
            else _as_utc(datetime.fromisoformat(ended_at)),
            trigger=data.get("trigger"),
            event=data.get("event"),
            error=None if error is None else ErrorInfo.from_dict(error),
            cancel_reason=data.get("cancel_reason"),
            logs=[LogEntry.from_dict(e) for e in data.get("logs") or []],
        )


@dataclass(frozen=True)
class Retention:
    """
    How much history to keep. Runs matching *either* limit are pruned.

    Attributes
    ----------
    max_runs_per_job : int, optional
        Keep at most this many runs for each job (the most recent ones).
    max_age : timedelta, optional
        Delete runs that started longer ago than this.
    """

    max_runs_per_job: int | None = None
    max_age: timedelta | None = None

    def __post_init__(self) -> None:
        if self.max_runs_per_job is not None and self.max_runs_per_job < 0:
            raise ValueError("max_runs_per_job must be >= 0")
        if self.max_age is not None and self.max_age < timedelta(0):
            raise ValueError("max_age must not be negative")

    @property
    def is_empty(self) -> bool:
        """True when no limit is set, so pruning would never delete anything."""
        return self.max_runs_per_job is None and self.max_age is None

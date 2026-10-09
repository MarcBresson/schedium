from datetime import datetime, timedelta, timezone

import pytest
from schedium.plugins import RunStatus

from schedium_history import ErrorInfo, LogEntry, Retention, RunRecord

T0 = datetime(2026, 2, 12, 12, 0, tzinfo=timezone.utc)


def test_record_round_trips_through_dict():
    record = RunRecord(
        run_id="a" * 32,
        job_id="job",
        job_name="Job",
        scheduler="Scheduler",
        status=RunStatus.FAILED,
        started_at=T0,
        ended_at=T0 + timedelta(seconds=2),
        trigger="Tick('second')",
        event="('bucket', 'second', 1)",
        error=ErrorInfo("ValueError", "bad", "Traceback..."),
        cancel_reason=None,
        logs=[LogEntry(T0, "INFO", "app", "hello")],
    )
    assert record.duration == 2
    assert RunRecord.from_dict(record.to_dict()) == record


def test_naive_datetimes_are_read_as_utc():
    data = RunRecord("r", "j", "S", RunStatus.RUNNING, T0).to_dict()
    data["started_at"] = "2026-02-12T12:00:00"
    assert RunRecord.from_dict(data).started_at == T0


def test_running_record_has_no_duration():
    assert RunRecord("r", "j", "S", RunStatus.RUNNING, T0).duration is None


def test_retention_validation():
    assert Retention().is_empty
    assert not Retention(max_runs_per_job=1).is_empty
    with pytest.raises(ValueError):
        Retention(max_runs_per_job=-1)
    with pytest.raises(ValueError):
        Retention(max_age=timedelta(seconds=-1))

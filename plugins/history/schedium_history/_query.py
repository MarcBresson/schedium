"""Filtering and retention logic shared by the in-memory and file backends."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone

from schedium.plugins import RunStatus

from schedium_history.models import Retention, RunRecord, _as_utc


def normalize_statuses(
    status: RunStatus | Iterable[RunStatus] | None,
) -> frozenset[RunStatus] | None:
    if status is None:
        return None
    if isinstance(status, RunStatus):
        return frozenset([status])
    return frozenset(status)


def query(
    records: Iterable[RunRecord],
    *,
    job_id: str | None = None,
    status: RunStatus | Iterable[RunStatus] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int | None = None,
    newest_first: bool = True,
) -> list[RunRecord]:
    statuses = normalize_statuses(status)
    since_utc = None if since is None else _as_utc(since)
    until_utc = None if until is None else _as_utc(until)

    selected = [
        r
        for r in records
        if (job_id is None or r.job_id == job_id)
        and (statuses is None or r.status in statuses)
        and (since_utc is None or r.started_at >= since_utc)
        and (until_utc is None or r.started_at < until_utc)
    ]
    selected.sort(key=lambda r: r.started_at, reverse=newest_first)
    return selected if limit is None else selected[:limit]


def runs_to_prune(
    records: Iterable[RunRecord], retention: Retention, now: datetime | None
) -> set[str]:
    doomed: set[str] = set()
    records = list(records)

    if retention.max_age is not None:
        cutoff = _as_utc(now or datetime.now(timezone.utc)) - retention.max_age
        doomed.update(r.run_id for r in records if r.started_at < cutoff)

    if retention.max_runs_per_job is not None:
        by_job: dict[str, list[RunRecord]] = defaultdict(list)
        for record in records:
            by_job[record.job_id].append(record)
        for runs in by_job.values():
            runs.sort(key=lambda r: r.started_at, reverse=True)
            doomed.update(r.run_id for r in runs[retention.max_runs_per_job :])

    return doomed

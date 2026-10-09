"""SQL backend built on SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import exc as sa_exc

from schedium.plugins import RunStatus

from schedium_history._query import normalize_statuses
from schedium_history.models import (
    ErrorInfo,
    LogEntry,
    Retention,
    RunRecord,
    _as_utc,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine, Row


def _is_memory_sqlite(url: sa.URL) -> bool:
    return url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:")


class SQLAlchemyStore:
    """
    Store run records in a SQL table, through SQLAlchemy.

    Works with any database SQLAlchemy supports. It implements
    :class:`~schedium_history.QueryableStore` and
    :class:`~schedium_history.PrunableStore`. Records are written with plain
    synchronous SQLAlchemy; on :class:`~schedium.asyncio.AsyncScheduler` the
    plugin runs its hooks in a worker thread, so the event loop is never
    blocked. Async engines are not supported.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine or str
        An engine, or a database URL (``"sqlite:///runs.db"``,
        ``"postgresql+psycopg://..."``). In-memory SQLite URLs get a single shared
        connection, because every worker thread would otherwise see its own empty
        database.
    table_name : str, default "schedium_runs"
        Name of the table.
    create_tables : bool, default True
        Create the table (and its indexes) if it does not exist. Disable it if
        you manage your schema with migrations; :attr:`table` describes the
        expected columns.

    Attributes
    ----------
    engine : sqlalchemy.engine.Engine
        The engine in use.
    table : sqlalchemy.Table
        The table holding the records. Its ``metadata`` contains this table only,
        so you can add it to your own migration tooling.

    Examples
    --------
    >>> from schedium_history import SQLAlchemyStore
    >>> store = SQLAlchemyStore("sqlite://")
    >>> store.get_runs()
    []
    """

    def __init__(
        self,
        engine: Engine | str,
        *,
        table_name: str = "schedium_runs",
        create_tables: bool = True,
    ) -> None:
        if isinstance(engine, str):
            url = sa.make_url(engine)
            if _is_memory_sqlite(url):
                from sqlalchemy.pool import StaticPool

                engine = sa.create_engine(
                    url,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                )
            else:
                engine = sa.create_engine(url)
        self.engine: Engine = engine

        metadata = sa.MetaData()
        self.table = sa.Table(
            table_name,
            metadata,
            sa.Column("run_id", sa.String(32), primary_key=True),
            sa.Column("job_id", sa.String(512), nullable=False, index=True),
            sa.Column("job_name", sa.String(512)),
            sa.Column("scheduler", sa.String(128), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, index=True),
            sa.Column(
                "started_at", sa.DateTime(timezone=True), nullable=False, index=True
            ),
            sa.Column("ended_at", sa.DateTime(timezone=True)),
            sa.Column("trigger", sa.Text),
            sa.Column("event", sa.Text),
            sa.Column("error", sa.JSON(none_as_null=True)),
            sa.Column("cancel_reason", sa.Text),
            sa.Column("logs", sa.JSON(none_as_null=True)),
        )
        if create_tables:
            metadata.create_all(self.engine)

    @staticmethod
    def _values(record: RunRecord) -> dict[str, Any]:
        data = record.to_dict()
        return {
            "job_id": record.job_id,
            "job_name": record.job_name,
            "scheduler": record.scheduler,
            "status": record.status.value,
            "started_at": _as_utc(record.started_at),
            "ended_at": None if record.ended_at is None else _as_utc(record.ended_at),
            "trigger": record.trigger,
            "event": record.event,
            "error": data["error"],
            "cancel_reason": record.cancel_reason,
            "logs": data["logs"],
        }

    @staticmethod
    def _record(row: Row[Any]) -> RunRecord:
        started_at = _as_utc(row.started_at)
        return RunRecord(
            run_id=row.run_id,
            job_id=row.job_id,
            job_name=row.job_name,
            scheduler=row.scheduler,
            status=RunStatus(row.status),
            started_at=started_at,
            ended_at=None if row.ended_at is None else _as_utc(row.ended_at),
            trigger=row.trigger,
            event=row.event,
            error=None if row.error is None else ErrorInfo.from_dict(row.error),
            cancel_reason=row.cancel_reason,
            logs=[LogEntry.from_dict(e) for e in row.logs or []],
        )

    def save(self, record: RunRecord) -> None:
        """
        Insert the record, or update the existing row of the same run.

        Parameters
        ----------
        record : RunRecord
            The record to store.
        """
        t = self.table
        values = self._values(record)
        with self.engine.begin() as conn:
            updated = conn.execute(
                sa.update(t).where(t.c.run_id == record.run_id).values(**values)
            )
            if updated.rowcount == 0:
                try:
                    with conn.begin_nested():
                        conn.execute(
                            sa.insert(t).values(run_id=record.run_id, **values)
                        )
                except sa_exc.IntegrityError:
                    # inserted concurrently by another connection: update instead
                    conn.execute(
                        sa.update(t).where(t.c.run_id == record.run_id).values(**values)
                    )

    def get_run(self, run_id: str) -> RunRecord | None:
        """
        Fetch one record.

        Parameters
        ----------
        run_id : str
            The run to look for.

        Returns
        -------
        RunRecord or None
            The record, or None if unknown.
        """
        t = self.table
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(t).where(t.c.run_id == run_id)).first()
        return None if row is None else self._record(row)

    def get_runs(
        self,
        *,
        job_id: str | None = None,
        status: RunStatus | Iterable[RunStatus] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[RunRecord]:
        """
        Fetch records matching all given filters, ordered by start time.

        Parameters
        ----------
        job_id : str, optional
            Only runs of this job.
        status : RunStatus or Iterable[RunStatus], optional
            Only runs with one of these statuses.
        since : datetime, optional
            Only runs that started at or after this time.
        until : datetime, optional
            Only runs that started strictly before this time.
        limit : int, optional
            Return at most this many records.
        newest_first : bool, default True
            Sort by descending start time (oldest first when False).

        Returns
        -------
        list[RunRecord]
            The matching records.
        """
        t = self.table
        stmt = sa.select(t)
        if job_id is not None:
            stmt = stmt.where(t.c.job_id == job_id)
        statuses = normalize_statuses(status)
        if statuses is not None:
            stmt = stmt.where(t.c.status.in_([s.value for s in statuses]))
        if since is not None:
            stmt = stmt.where(t.c.started_at >= _as_utc(since))
        if until is not None:
            stmt = stmt.where(t.c.started_at < _as_utc(until))
        stmt = stmt.order_by(
            t.c.started_at.desc() if newest_first else t.c.started_at.asc()
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        with self.engine.connect() as conn:
            return [self._record(row) for row in conn.execute(stmt)]

    def prune(self, retention: Retention, *, now: datetime | None = None) -> int:
        """
        Delete the rows that exceed ``retention``.

        Parameters
        ----------
        retention : Retention
            The limits to enforce.
        now : datetime, optional
            Reference time for ``max_age`` (defaults to the current time).

        Returns
        -------
        int
            Number of deleted records.
        """
        t = self.table
        deleted = 0
        with self.engine.begin() as conn:
            if retention.max_age is not None:
                cutoff = _as_utc(now or datetime.now(timezone.utc)) - retention.max_age
                result = conn.execute(sa.delete(t).where(t.c.started_at < cutoff))
                deleted += result.rowcount

            if retention.max_runs_per_job is not None:
                keep = retention.max_runs_per_job
                crowded: list[str] = list(
                    conn.execute(
                        sa.select(t.c.job_id)
                        .group_by(t.c.job_id)
                        .having(sa.func.count() > keep)
                    ).scalars()
                )
                for job in crowded:
                    doomed: list[str] = list(
                        conn.execute(
                            sa.select(t.c.run_id)
                            .where(t.c.job_id == job)
                            .order_by(t.c.started_at.desc())
                            .offset(keep)
                        ).scalars()
                    )
                    if doomed:
                        result = conn.execute(
                            sa.delete(t).where(t.c.run_id.in_(doomed))
                        )
                        deleted += result.rowcount
        return deleted

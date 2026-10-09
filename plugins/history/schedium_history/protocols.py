"""
The interfaces a storage backend implements.

They are :class:`typing.Protocol` classes: a backend does not need to inherit
from anything, it only needs the right methods. The interfaces are layered so a
custom backend stays tiny:

- :class:`TraceStore` is the only one required: a single ``save`` method.
- :class:`QueryableStore` adds reading, for history and dashboards.
- :class:`PrunableStore` adds deletion, so the plugin can apply a
  :class:`~schedium_history.Retention` policy.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from schedium.plugins import RunStatus

from schedium_history.models import Retention, RunRecord


@runtime_checkable
class TraceStore(Protocol):
    """Minimal backend: remember run records."""

    def save(self, record: RunRecord) -> None:
        """
        Insert or update (upsert) a record, keyed by ``record.run_id``.

        It is called when a run starts and again when it ends, from whichever
        thread runs the job, so it must be thread-safe. The record object is
        reused and mutated between calls: store a snapshot, not the object.

        Parameters
        ----------
        record : RunRecord
            The record to store.
        """
        ...


@runtime_checkable
class QueryableStore(TraceStore, Protocol):
    """A backend whose records can be read back."""

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
        ...

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
            Only runs of this job (:attr:`RunRecord.job_id`).
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
        ...


@runtime_checkable
class PrunableStore(TraceStore, Protocol):
    """A backend that can delete old records."""

    def prune(self, retention: Retention, *, now: datetime | None = None) -> int:
        """
        Delete the records that exceed ``retention``.

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
        ...

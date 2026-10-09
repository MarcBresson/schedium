"""In-memory backend."""

import copy
import threading
from collections import OrderedDict
from collections.abc import Iterable
from datetime import datetime

from schedium.plugins import RunStatus

from schedium_history._query import query, runs_to_prune
from schedium_history.models import Retention, RunRecord


class MemoryStore:
    """
    Keep run records in memory, for the lifetime of the process.

    Handy for tests, short-lived processes, and as a "last N runs" view next to
    a persistent backend. Implements :class:`~schedium_history.QueryableStore`
    and :class:`~schedium_history.PrunableStore`. Thread-safe.

    Parameters
    ----------
    max_runs : int, optional
        Keep at most this many runs overall; the oldest ones are dropped first.
        Unbounded when None, which grows forever in a long-running process.

    Examples
    --------
    >>> from schedium_history import MemoryStore
    >>> store = MemoryStore(max_runs=1000)
    >>> store.get_runs()
    []
    """

    def __init__(self, max_runs: int | None = None) -> None:
        if max_runs is not None and max_runs < 1:
            raise ValueError("max_runs must be >= 1")
        self.max_runs = max_runs
        self._records: OrderedDict[str, RunRecord] = OrderedDict()
        self._lock = threading.Lock()

    def save(self, record: RunRecord) -> None:
        """
        Insert or update a snapshot of ``record``.

        Parameters
        ----------
        record : RunRecord
            The record to store.
        """
        snapshot = copy.deepcopy(record)
        with self._lock:
            self._records[record.run_id] = snapshot
            if self.max_runs is not None:
                while len(self._records) > self.max_runs:
                    self._records.popitem(last=False)

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
            A copy of the record, or None if unknown.
        """
        with self._lock:
            record = self._records.get(run_id)
            return copy.deepcopy(record) if record is not None else None

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
            Copies of the matching records.
        """
        with self._lock:
            snapshot = [copy.deepcopy(r) for r in self._records.values()]
        return query(
            snapshot,
            job_id=job_id,
            status=status,
            since=since,
            until=until,
            limit=limit,
            newest_first=newest_first,
        )

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
        with self._lock:
            doomed = runs_to_prune(self._records.values(), retention, now)
            for run_id in doomed:
                del self._records[run_id]
        return len(doomed)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

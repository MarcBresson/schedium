"""JSON Lines file backend."""

import json
import logging
import os
import tempfile
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from schedium.plugins import RunStatus

from schedium_history._query import query, runs_to_prune
from schedium_history.models import Retention, RunRecord

logger = logging.getLogger(__name__)


class JSONLStore:
    """
    Append run records to a `JSON Lines <https://jsonlines.org>`_ file.

    Every :meth:`save` appends one full JSON object on its own line, so a run
    usually appears twice (when it starts and when it ends). When reading, the
    *last* line of a run wins. The file is human-readable and easy to ship to
    other tools (``jq``, pandas, log collectors). Pruning rewrites the file
    without the old runs and without superseded lines.

    The file is safe to use from several threads of one process. It is **not**
    safe to share between several processes writing at the same time.

    Implements :class:`~schedium_history.QueryableStore` and
    :class:`~schedium_history.PrunableStore`. Reading parses the whole file, which
    is fine for history sized in thousands of runs; combine it with a
    :class:`~schedium_history.Retention` policy.

    Parameters
    ----------
    path : str or os.PathLike
        The file to write. It and its parent directories are created if needed.

    Examples
    --------
    >>> import tempfile, os
    >>> from schedium_history import JSONLStore
    >>> store = JSONLStore(os.path.join(tempfile.mkdtemp(), "runs.jsonl"))
    >>> store.get_runs()
    []
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def save(self, record: RunRecord) -> None:
        """
        Append the record as one line.

        Parameters
        ----------
        record : RunRecord
            The record to store.
        """
        line = json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)

    def _read(self) -> dict[str, RunRecord]:
        records: dict[str, RunRecord] = {}
        try:
            fh = open(self.path, encoding="utf-8")
        except FileNotFoundError:
            return records

        with fh:
            for number, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = RunRecord.from_dict(json.loads(line))
                except (ValueError, KeyError, TypeError):
                    # for example a line truncated by a crash
                    logger.warning("Ignoring invalid line %d in %s", number, self.path)
                    continue
                records[record.run_id] = record
        return records

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
        with self._lock:
            return self._read().get(run_id)

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
        with self._lock:
            records = self._read()
        return query(
            records.values(),
            job_id=job_id,
            status=status,
            since=since,
            until=until,
            limit=limit,
            newest_first=newest_first,
        )

    def prune(self, retention: Retention, *, now: datetime | None = None) -> int:
        """
        Rewrite the file without the records that exceed ``retention``.

        The rewrite goes to a temporary file that atomically replaces the
        original, so a crash cannot leave a half-written file behind.

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
            records = self._read()
            doomed = runs_to_prune(records.values(), retention, now)
            if not doomed:
                return 0

            fd, tmp_name = tempfile.mkstemp(
                dir=self.path.parent, prefix=self.path.name, suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    for run_id, record in records.items():
                        if run_id not in doomed:
                            tmp.write(
                                json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
                            )
                os.replace(tmp_name, self.path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
                raise
        return len(doomed)

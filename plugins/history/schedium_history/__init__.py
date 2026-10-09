"""
Run traces for schedium.

A plugin that remembers when each job started and stopped, its status, its
errors and, optionally, its logs, in the backend of your choice.

>>> from schedium import Scheduler
>>> from schedium_history import MemoryStore, HistoryPlugin
>>> scheduler = Scheduler(plugins=[HistoryPlugin(MemoryStore())])
"""

from typing import TYPE_CHECKING, Any

from schedium_history.jsonl import JSONLStore
from schedium_history.memory import MemoryStore
from schedium_history.models import ErrorInfo, LogEntry, Retention, RunRecord
from schedium_history.plugin import HistoryPlugin
from schedium_history.protocols import PrunableStore, QueryableStore, TraceStore

if TYPE_CHECKING:
    from schedium_history.sqlalchemy import SQLAlchemyStore

__version__ = "0.1.0"

__all__ = [
    "ErrorInfo",
    "JSONLStore",
    "LogEntry",
    "MemoryStore",
    "PrunableStore",
    "QueryableStore",
    "Retention",
    "RunRecord",
    "SQLAlchemyStore",
    "HistoryPlugin",
    "TraceStore",
]


def __getattr__(name: str) -> Any:
    # SQLAlchemy is an optional dependency: only import it when it is asked for.
    if name == "SQLAlchemyStore":
        from schedium_history.sqlalchemy import SQLAlchemyStore

        return SQLAlchemyStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

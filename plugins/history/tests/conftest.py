import pytest

from schedium_history import JSONLStore, MemoryStore

BACKENDS = ["memory", "jsonl", "sqlalchemy"]


def make_store(kind: str, tmp_path):
    if kind == "memory":
        return MemoryStore()
    if kind == "jsonl":
        return JSONLStore(tmp_path / "runs.jsonl")
    if kind == "sqlalchemy":
        pytest.importorskip("sqlalchemy")
        from schedium_history import SQLAlchemyStore

        return SQLAlchemyStore(f"sqlite:///{tmp_path / 'runs.db'}")
    raise AssertionError(kind)


@pytest.fixture(params=BACKENDS)
def store(request, tmp_path):
    """Every built-in backend, all of which are queryable and prunable."""
    return make_store(request.param, tmp_path)

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from schedium.plugins import RunStatus

from conftest import make_store
from schedium_history import (
    ErrorInfo,
    JSONLStore,
    LogEntry,
    MemoryStore,
    PrunableStore,
    QueryableStore,
    Retention,
    RunRecord,
    TraceStore,
)

T0 = datetime(2026, 2, 12, 12, 0, tzinfo=timezone.utc)


def rec(
    run_id: str, job: str = "job", minutes: int = 0, status=RunStatus.SUCCESS, **kw
):
    started = T0 + timedelta(minutes=minutes)
    return RunRecord(
        run_id=run_id,
        job_id=job,
        scheduler="Scheduler",
        status=status,
        started_at=started,
        ended_at=started + timedelta(seconds=1),
        **kw,
    )


def test_protocol_layering(store):
    assert isinstance(store, TraceStore)
    assert isinstance(store, QueryableStore)
    assert isinstance(store, PrunableStore)

    class Minimal:
        def save(self, record):  # a custom backend only needs this
            pass

    assert isinstance(Minimal(), TraceStore)
    assert not isinstance(Minimal(), QueryableStore)
    assert not isinstance(Minimal(), PrunableStore)


def test_save_is_an_upsert_and_round_trips(store):
    record = rec(
        "r1",
        status=RunStatus.RUNNING,
        trigger="Tick",
        event="tok",
    )
    record.ended_at = None
    store.save(record)
    assert store.get_run("r1").status is RunStatus.RUNNING
    assert store.get_run("r1").ended_at is None

    record.status = RunStatus.FAILED
    record.ended_at = T0 + timedelta(seconds=3)
    record.error = ErrorInfo("ValueError", "bad", "tb")
    record.logs.append(LogEntry(T0, "INFO", "app", "hello"))
    store.save(record)

    assert len(store.get_runs()) == 1
    assert store.get_run("r1") == record
    assert store.get_run("missing") is None


def test_get_runs_filters_order_and_limit(store):
    store.save(rec("a1", "a", 0))
    store.save(rec("a2", "a", 10, RunStatus.FAILED))
    store.save(rec("b1", "b", 5))
    store.save(rec("b2", "b", 20, RunStatus.CANCELLED))

    ids = lambda runs: [r.run_id for r in runs]  # noqa: E731

    assert ids(store.get_runs()) == ["b2", "a2", "b1", "a1"]
    assert ids(store.get_runs(newest_first=False)) == ["a1", "b1", "a2", "b2"]
    assert ids(store.get_runs(job_id="a")) == ["a2", "a1"]
    assert ids(store.get_runs(status=RunStatus.FAILED)) == ["a2"]
    assert ids(store.get_runs(status=[RunStatus.FAILED, RunStatus.CANCELLED])) == [
        "b2",
        "a2",
    ]
    assert ids(store.get_runs(since=T0 + timedelta(minutes=5))) == ["b2", "a2", "b1"]
    assert ids(store.get_runs(until=T0 + timedelta(minutes=10))) == ["b1", "a1"]
    assert ids(store.get_runs(limit=2)) == ["b2", "a2"]
    assert ids(store.get_runs(job_id="a", status=RunStatus.SUCCESS)) == ["a1"]


def test_datetime_filters_accept_other_timezones(store):
    store.save(rec("r", minutes=0))
    paris = timezone(timedelta(hours=2))
    # 13:30 in UTC+2 is 11:30 UTC: the run (12:00 UTC) is after it
    assert len(store.get_runs(since=datetime(2026, 2, 12, 13, 30, tzinfo=paris))) == 1
    assert len(store.get_runs(since=datetime(2026, 2, 12, 14, 30, tzinfo=paris))) == 0


def test_prune_max_runs_per_job(store):
    for i in range(5):
        store.save(rec(f"a{i}", "a", i))
    store.save(rec("b0", "b", 0))

    assert store.prune(Retention(max_runs_per_job=2)) == 3
    assert sorted(r.run_id for r in store.get_runs()) == ["a3", "a4", "b0"]
    assert store.prune(Retention(max_runs_per_job=2)) == 0


def test_prune_max_age(store):
    store.save(rec("old", minutes=0))
    store.save(rec("new", minutes=100))
    now = T0 + timedelta(minutes=120)

    assert store.prune(Retention(max_age=timedelta(minutes=60)), now=now) == 1
    assert [r.run_id for r in store.get_runs()] == ["new"]


def test_prune_combines_both_limits(store):
    store.save(rec("a-old", "a", 0))
    store.save(rec("a-new", "a", 100))
    for i, minutes in enumerate([50, 60, 70]):
        store.save(rec(f"b{i}", "b", minutes))

    deleted = store.prune(
        Retention(max_runs_per_job=2, max_age=timedelta(minutes=60)),
        now=T0 + timedelta(minutes=100),  # max_age cutoff: minute 40
    )
    # max_age removes a-old, max_runs_per_job removes the oldest run of b
    assert deleted == 2
    assert sorted(r.run_id for r in store.get_runs()) == ["a-new", "b1", "b2"]


def test_saving_from_many_threads(store):
    def work(i):
        r = rec(f"r{i}", "j", i)
        store.save(r)
        r.status = RunStatus.FAILED
        store.save(r)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    runs = store.get_runs()
    assert len(runs) == 20
    assert {r.status for r in runs} == {RunStatus.FAILED}


def test_memory_store_stores_snapshots_not_references():
    store = MemoryStore()
    record = rec("r")
    store.save(record)
    record.status = RunStatus.FAILED
    assert store.get_run("r").status is RunStatus.SUCCESS
    store.get_run("r").status = RunStatus.FAILED  # mutating a copy changes nothing
    assert store.get_run("r").status is RunStatus.SUCCESS


def test_memory_store_max_runs_drops_oldest():
    store = MemoryStore(max_runs=2)
    for i in range(3):
        store.save(rec(f"r{i}", minutes=i))
    assert sorted(r.run_id for r in store.get_runs()) == ["r1", "r2"]
    assert len(store) == 2
    with pytest.raises(ValueError):
        MemoryStore(max_runs=0)


def test_jsonl_appends_one_line_per_save_and_last_one_wins(tmp_path):
    path = tmp_path / "nested" / "runs.jsonl"
    store = JSONLStore(path)
    record = rec("r", status=RunStatus.RUNNING)
    store.save(record)
    record.status = RunStatus.SUCCESS
    store.save(record)

    lines = path.read_text().splitlines()
    assert [json.loads(line)["status"] for line in lines] == ["running", "success"]
    assert store.get_run("r").status is RunStatus.SUCCESS
    assert len(store.get_runs()) == 1


def test_jsonl_ignores_truncated_lines_and_missing_file(tmp_path, caplog):
    store = JSONLStore(tmp_path / "runs.jsonl")
    assert store.get_runs() == []

    store.save(rec("ok"))
    with open(store.path, "a") as fh:
        fh.write('{"run_id": "cut", "job_')  # a write interrupted by a crash
    with caplog.at_level("WARNING"):
        assert [r.run_id for r in store.get_runs()] == ["ok"]
    assert "invalid line" in caplog.text


def test_jsonl_prune_compacts_file_and_leaves_no_temp_files(tmp_path):
    store = JSONLStore(tmp_path / "runs.jsonl")
    for i in range(3):
        record = rec(f"r{i}", minutes=i, status=RunStatus.RUNNING)
        store.save(record)
        record.status = RunStatus.SUCCESS
        store.save(record)

    assert store.prune(Retention(max_runs_per_job=1)) == 2
    assert len(store.path.read_text().splitlines()) == 1
    assert [p.name for p in tmp_path.iterdir()] == ["runs.jsonl"]


def test_sqlalchemy_store_specifics(tmp_path):
    store = make_store("sqlalchemy", tmp_path)
    import sqlalchemy as sa

    assert store.table.name == "schedium_runs"
    assert sa.inspect(store.engine).has_table("schedium_runs")

    custom = store.__class__(store.engine, table_name="my_runs")
    assert sa.inspect(store.engine).has_table("my_runs")
    custom.save(rec("r"))
    assert store.get_run("r") is None  # different table

    no_create = store.__class__(
        store.engine, table_name="never_created", create_tables=False
    )
    assert not sa.inspect(store.engine).has_table("never_created")
    assert no_create.table.name == "never_created"


def test_sqlalchemy_in_memory_sqlite_is_shared_across_threads():
    pytest.importorskip("sqlalchemy")
    from schedium_history import SQLAlchemyStore

    store = SQLAlchemyStore("sqlite://")
    t = threading.Thread(target=lambda: store.save(rec("from-thread")))
    t.start()
    t.join()
    assert store.get_run("from-thread") is not None

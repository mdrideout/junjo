"""Verify the derived index across services, row groups and semantic conventions."""

import json
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.db_sqlite.metadata import db
from app.db_sqlite.metadata.indexer import index_parquet_file
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata


@pytest.fixture
def metadata_connection(tmp_path):
    old_path = db._db_path
    db.close_connection()
    db.init_metadata_db(str(tmp_path / "metadata.db"))
    try:
        yield db.get_connection()
    finally:
        db.close_connection()
        db._db_path = old_path


def write_spans(path, rows):
    schema = pa.schema(
        [
            ("trace_id", pa.string()),
            ("service_name", pa.string()),
            ("start_time", pa.timestamp("ns", tz="UTC")),
            ("end_time", pa.timestamp("ns", tz="UTC")),
            ("attributes", pa.string()),
        ]
    )
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, row_group_size=2)


def span(trace, service, start, end, attrs):
    return {
        "trace_id": trace,
        "service_name": service,
        "start_time": start,
        "end_time": end,
        "attributes": json.dumps(attrs) if isinstance(attrs, dict) else attrs,
    }


def test_index_preserves_all_selection_metadata(tmp_path, metadata_connection):
    path = tmp_path / "spans.parquet"
    rows = [
        span("shared", "alpha", 2_999, 7_999, {"junjo.span_type": "workflow"}),
        span("shared", "beta", 9_999, 13_999, {"openinference.span.kind": "LLM"}),
        span("shared", "alpha", -1_001, 8_001, {"gen_ai.provider.name": "xai"}),
        span("agent", "beta", 8_001, 19_999, {"junjo.span_type": "agent"}),
        span("operation", "beta", 7_001, 12_999, {"gen_ai.operation.name": "chat"}),
        span("ordinary", "alpha", 5_001, 6_999, {"gen_ai.provider.name": ""}),
        span("broken-json", "alpha", 4_001, 8_999, "{invalid"),
        span("no-attrs", "alpha", 4_001, 8_999, None),
        span("empty", "", 0, 999, {}),
    ]
    write_spans(path, rows)
    data = read_parquet_metadata(str(path), path.stat().st_size)
    assert data.row_count == index_parquet_file(data) == len(rows)
    assert data.service_name == "alpha"
    assert data.min_time == datetime(1969, 12, 31, 23, 59, 59, 999998, tzinfo=UTC)
    assert data.max_time == datetime(1970, 1, 1, 0, 0, 0, 19, tzinfo=UTC)
    conn = metadata_connection
    assert conn.execute("SELECT trace_id FROM trace_files ORDER BY trace_id").fetchall() == [
        (t,) for t in sorted({r["trace_id"] for r in rows})
    ]
    assert conn.execute(
        "SELECT service_name, trace_id FROM llm_traces ORDER BY service_name, trace_id"
    ).fetchall() == [("alpha", "shared"), ("beta", "operation"), ("beta", "shared")]
    assert conn.execute("SELECT service_name FROM workflow_files").fetchall() == [("alpha",)]
    assert conn.execute("SELECT service_name FROM agent_files").fetchall() == [("beta",)]
    assert conn.execute(
        "SELECT service_name, span_count, min_time, max_time FROM file_services ORDER BY service_name"
    ).fetchall() == [
        ("", 1, "1970-01-01T00:00:00+00:00", "1970-01-01T00:00:00+00:00"),
        ("alpha", 5, "1969-12-31T23:59:59.999998+00:00", "1970-01-01T00:00:00.000008+00:00"),
        ("beta", 3, "1970-01-01T00:00:00.000007+00:00", "1970-01-01T00:00:00.000019+00:00"),
    ]


def test_metadata_transaction_rolls_back_on_failure(tmp_path, metadata_connection, monkeypatch):
    from app.db_sqlite.metadata import indexer

    path = tmp_path / "spans.parquet"
    write_spans(path, [span("trace", "service", 0, 1_000, {"junjo.span_type": "agent"})])
    data = read_parquet_metadata(str(path), path.stat().st_size)

    def fail(*args):
        raise RuntimeError("injected index write failure")

    monkeypatch.setattr(indexer, "add_agent_file", fail)
    with pytest.raises(RuntimeError, match="injected index write failure"):
        index_parquet_file(data)
    for table in ["parquet_files", "trace_files", "file_services", "agent_files"]:
        assert metadata_connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.parquet"
    write_spans(path, [])
    with pytest.raises(ValueError, match="Empty Parquet file"):
        read_parquet_metadata(str(path), path.stat().st_size)

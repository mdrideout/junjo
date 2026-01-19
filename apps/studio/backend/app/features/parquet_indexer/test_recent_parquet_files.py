from unittest.mock import patch

import pytest

from app.features.parquet_indexer import recent_parquet_files


@pytest.fixture(autouse=True)
def _clear_recent_files():
    recent_parquet_files._recent_files.clear()  # noqa: SLF001 - test cleanup
    yield
    recent_parquet_files._recent_files.clear()  # noqa: SLF001 - test cleanup


@pytest.mark.unit
def test_recent_parquet_files_orders_by_recency():
    with patch(
        "app.features.parquet_indexer.recent_parquet_files.time.monotonic",
        side_effect=[1.0, 2.0, 3.0],
    ):
        recent_parquet_files.record_new_parquet_file("/tmp/a.parquet")
        recent_parquet_files.record_new_parquet_file("/tmp/b.parquet")
        recent_parquet_files.record_new_parquet_file("/tmp/c.parquet")

    assert recent_parquet_files.get_recent_parquet_files(limit=2) == [
        "/tmp/c.parquet",
        "/tmp/b.parquet",
    ]


@pytest.mark.unit
def test_recent_parquet_files_prunes_expired():
    with patch(
        "app.features.parquet_indexer.recent_parquet_files.time.monotonic",
        side_effect=[0.0, 200.0],
    ):
        recent_parquet_files.record_new_parquet_file("/tmp/a.parquet")
        paths = recent_parquet_files.get_recent_parquet_files(max_age_seconds=120.0)

    assert paths == []


@pytest.mark.unit
def test_mark_parquet_file_indexed_removes_entry():
    recent_parquet_files.record_new_parquet_file("/tmp/a.parquet")
    recent_parquet_files.mark_parquet_file_indexed("/tmp/a.parquet")

    assert recent_parquet_files.get_recent_parquet_files() == []

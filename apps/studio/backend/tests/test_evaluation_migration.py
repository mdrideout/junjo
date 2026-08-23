"""Greenfield upgrade, downgrade, and schema-drift proof for the initial migration."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APPLICATION_TABLES = {
    "api_keys",
    "users",
    "eval_datasets",
    "eval_cases",
    "eval_runs",
    "eval_case_attempts",
    "evaluation_tokens",
}


def _alembic(database_path: Path, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["JUNJO_SQLITE_PATH"] = str(database_path)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def test_generated_initial_migration_round_trips_without_schema_drift(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junjo.db"

    _alembic(database_path, "upgrade", "head")
    _alembic(database_path, "check")

    with sqlite3.connect(database_path) as connection:
        tables = _tables(connection)
        subject_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('eval_case_attempts')")
        }
        source_indexes = {row[1] for row in connection.execute("PRAGMA index_list('eval_cases')")}
        token_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('evaluation_tokens')")
        }
        eval_cases_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'eval_cases'"
        ).fetchone()

    assert APPLICATION_TABLES.issubset(tables)
    assert "uq_eval_case_attempts_subject_junjo_execution" in subject_indexes
    assert "uq_eval_case_attempts_subject_otel_span" in subject_indexes
    assert "ix_eval_cases_source_junjo_execution" in source_indexes
    assert "ix_eval_cases_source_otel_span" in source_indexes
    assert "ix_evaluation_tokens_token" in token_indexes
    assert eval_cases_sql is not None
    assert "target_kind IN ('node', 'workflow', 'agent')" in eval_cases_sql[0]
    assert "target_name" in eval_cases_sql[0]

    _alembic(database_path, "downgrade", "base")
    with sqlite3.connect(database_path) as connection:
        assert APPLICATION_TABLES.isdisjoint(_tables(connection))

    _alembic(database_path, "upgrade", "head")
    _alembic(database_path, "check")
    with sqlite3.connect(database_path) as connection:
        assert APPLICATION_TABLES.issubset(_tables(connection))

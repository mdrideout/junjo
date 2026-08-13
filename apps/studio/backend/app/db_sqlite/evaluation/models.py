"""SQLAlchemy models for the Studio evaluation control plane."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.datetime_utils import UTCDateTime, utcnow
from app.common.utils import generate_id
from app.db_sqlite.base import Base

MAX_KEY_BYTES = 128
MAX_NAME_BYTES = 256
MAX_DESCRIPTION_BYTES = 2_048
MAX_JSON_BYTES = 16_384
MAX_REASON_BYTES = 4_096
MAX_EXECUTION_IDENTITY_BYTES = 256
MAX_SOURCE_REVISION_BYTES = 64
MAX_DURATION_MS = 86_400_000
MAX_VERSION = 2_147_483_647


class EvaluationDatasetTable(Base):
    """One application-owned draft or immutable evaluation dataset."""

    __tablename__ = "eval_datasets"
    __table_args__ = (
        UniqueConstraint(
            "application_key",
            "key",
            name="uq_eval_datasets_application_key_key",
        ),
        CheckConstraint(
            "status IN ('draft', 'locked')",
            name="eval_datasets_status",
        ),
        CheckConstraint(
            "(status = 'draft' AND locked_at IS NULL) OR "
            "(status = 'locked' AND locked_at IS NOT NULL)",
            name="eval_datasets_lock_timestamp",
        ),
        CheckConstraint(
            f"length(CAST(application_key AS BLOB)) BETWEEN 1 AND {MAX_KEY_BYTES}",
            name="eval_datasets_application_key_bytes",
        ),
        CheckConstraint(
            f"length(CAST(key AS BLOB)) BETWEEN 1 AND {MAX_KEY_BYTES}",
            name="eval_datasets_key_bytes",
        ),
        CheckConstraint(
            f"length(CAST(name AS BLOB)) BETWEEN 1 AND {MAX_NAME_BYTES}",
            name="eval_datasets_name_bytes",
        ),
        CheckConstraint(
            f"description IS NULL OR length(CAST(description AS BLOB)) <= {MAX_DESCRIPTION_BYTES}",
            name="eval_datasets_description_bytes",
        ),
        Index(
            "ix_eval_datasets_application_created_id",
            "application_key",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(22),
        primary_key=True,
        default=lambda: generate_id(size=22),
    )
    application_key: Mapped[str] = mapped_column(String(MAX_KEY_BYTES), nullable=False)
    key: Mapped[str] = mapped_column(String(MAX_KEY_BYTES), nullable=False)
    name: Mapped[str] = mapped_column(String(MAX_NAME_BYTES), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(6), nullable=False, default="draft")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(22),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utcnow,
    )
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class EvaluationCaseTable(Base):
    """One ordered application-owned case in an evaluation dataset."""

    __tablename__ = "eval_cases"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "case_key",
            name="uq_eval_cases_dataset_case_key",
        ),
        UniqueConstraint(
            "dataset_id",
            "ordinal",
            name="uq_eval_cases_dataset_ordinal",
        ),
        CheckConstraint(
            "origin IN ('authored', 'generated')",
            name="eval_cases_origin",
        ),
        CheckConstraint(
            "target_kind IN ('node', 'workflow', 'agent')",
            name="eval_cases_target_kind",
        ),
        CheckConstraint(
            f"input_version BETWEEN 1 AND {MAX_VERSION}",
            name="eval_cases_input_version",
        ),
        CheckConstraint(
            f"evaluator_version BETWEEN 1 AND {MAX_VERSION}",
            name="eval_cases_evaluator_version",
        ),
        CheckConstraint(
            "ordinal >= 1",
            name="eval_cases_ordinal",
        ),
        CheckConstraint(
            f"length(CAST(case_key AS BLOB)) BETWEEN 1 AND {MAX_KEY_BYTES}",
            name="eval_cases_case_key_bytes",
        ),
        CheckConstraint(
            f"length(CAST(evaluation_name AS BLOB)) BETWEEN 1 AND {MAX_NAME_BYTES}",
            name="eval_cases_evaluation_name_bytes",
        ),
        CheckConstraint(
            f"length(CAST(target_key AS BLOB)) BETWEEN 1 AND {MAX_KEY_BYTES}",
            name="eval_cases_target_key_bytes",
        ),
        CheckConstraint(
            f"length(CAST(target_name AS BLOB)) BETWEEN 1 AND {MAX_NAME_BYTES}",
            name="eval_cases_target_name_bytes",
        ),
        CheckConstraint(
            f"length(CAST(evaluator_key AS BLOB)) BETWEEN 1 AND {MAX_KEY_BYTES}",
            name="eval_cases_evaluator_key_bytes",
        ),
        CheckConstraint(
            f"json_valid(input_json) AND length(CAST(input_json AS BLOB)) <= {MAX_JSON_BYTES}",
            name="eval_cases_input_json",
        ),
        CheckConstraint(
            "expectation_json IS NULL OR "
            f"(json_valid(expectation_json) AND "
            f"length(CAST(expectation_json AS BLOB)) <= {MAX_JSON_BYTES})",
            name="eval_cases_expectation_json",
        ),
        CheckConstraint(
            "(origin = 'authored' "
            "AND source_service_namespace IS NULL "
            "AND source_service_name IS NULL "
            "AND source_executable_type IS NULL "
            "AND source_runtime_id IS NULL "
            "AND source_revision IS NULL) "
            "OR "
            "(origin = 'generated' "
            "AND source_service_namespace IS NOT NULL "
            "AND source_service_name IS NOT NULL "
            "AND source_executable_type IS NOT NULL "
            "AND source_runtime_id IS NOT NULL "
            "AND source_revision IS NOT NULL)",
            name="eval_cases_source_provenance",
        ),
        CheckConstraint(
            "source_executable_type IS NULL "
            "OR source_executable_type IN ('workflow', 'subflow', 'agent')",
            name="eval_cases_source_executable_type",
        ),
        CheckConstraint(
            "source_service_namespace IS NULL OR "
            f"length(CAST(source_service_namespace AS BLOB)) "
            f"<= {MAX_EXECUTION_IDENTITY_BYTES}",
            name="eval_cases_source_namespace_bytes",
        ),
        CheckConstraint(
            "source_service_name IS NULL OR "
            f"length(CAST(source_service_name AS BLOB)) BETWEEN 1 "
            f"AND {MAX_EXECUTION_IDENTITY_BYTES}",
            name="eval_cases_source_service_name_bytes",
        ),
        CheckConstraint(
            "source_runtime_id IS NULL OR "
            f"length(CAST(source_runtime_id AS BLOB)) BETWEEN 1 "
            f"AND {MAX_EXECUTION_IDENTITY_BYTES}",
            name="eval_cases_source_runtime_id_bytes",
        ),
        CheckConstraint(
            "source_revision IS NULL OR length(source_revision) IN (40, 64)",
            name="eval_cases_source_revision_length",
        ),
        Index(
            "ix_eval_cases_dataset_ordinal_id",
            "dataset_id",
            "ordinal",
            "id",
        ),
        Index(
            "ix_eval_cases_source_execution",
            "source_service_namespace",
            "source_service_name",
            "source_executable_type",
            "source_runtime_id",
            sqlite_where=text("source_runtime_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(22),
        primary_key=True,
        default=lambda: generate_id(size=22),
    )
    dataset_id: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("eval_datasets.id"),
        nullable=False,
    )
    case_key: Mapped[str] = mapped_column(String(MAX_KEY_BYTES), nullable=False)
    evaluation_name: Mapped[str] = mapped_column(String(MAX_NAME_BYTES), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(9), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    target_key: Mapped[str] = mapped_column(String(MAX_KEY_BYTES), nullable=False)
    target_name: Mapped[str] = mapped_column(String(MAX_NAME_BYTES), nullable=False)
    input_version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    expectation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluator_key: Mapped[str] = mapped_column(String(MAX_KEY_BYTES), nullable=False)
    evaluator_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_service_namespace: Mapped[str | None] = mapped_column(
        String(MAX_EXECUTION_IDENTITY_BYTES),
        nullable=True,
    )
    source_service_name: Mapped[str | None] = mapped_column(
        String(MAX_EXECUTION_IDENTITY_BYTES),
        nullable=True,
    )
    source_executable_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_runtime_id: Mapped[str | None] = mapped_column(
        String(MAX_EXECUTION_IDENTITY_BYTES),
        nullable=True,
    )
    source_revision: Mapped[str | None] = mapped_column(
        String(MAX_SOURCE_REVISION_BYTES),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utcnow,
    )


class EvaluationRunTable(Base):
    """One labeled source revision evaluated against one locked dataset."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "request_key",
            name="uq_eval_runs_dataset_request_key",
        ),
        CheckConstraint(
            "status IN ('active', 'completed')",
            name="eval_runs_status",
        ),
        CheckConstraint(
            "(status = 'active' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="eval_runs_completion_timestamp",
        ),
        CheckConstraint(
            f"length(CAST(request_key AS BLOB)) BETWEEN 1 AND {MAX_KEY_BYTES}",
            name="eval_runs_request_key_bytes",
        ),
        CheckConstraint(
            f"length(CAST(run_label AS BLOB)) BETWEEN 1 AND {MAX_NAME_BYTES}",
            name="eval_runs_run_label_bytes",
        ),
        CheckConstraint(
            "length(source_revision) IN (40, 64)",
            name="eval_runs_source_revision_length",
        ),
        Index("ix_eval_runs_created_id", "created_at", "id"),
        Index(
            "ix_eval_runs_dataset_created_id",
            "dataset_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(22),
        primary_key=True,
        default=lambda: generate_id(size=22),
    )
    dataset_id: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("eval_datasets.id"),
        nullable=False,
    )
    request_key: Mapped[str] = mapped_column(String(MAX_KEY_BYTES), nullable=False)
    run_label: Mapped[str] = mapped_column(String(MAX_NAME_BYTES), nullable=False)
    source_revision: Mapped[str] = mapped_column(
        String(MAX_SOURCE_REVISION_BYTES),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(9), nullable=False, default="active")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(22),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class EvaluationCaseAttemptTable(Base):
    """One immutable run membership and terminal outcome for a case."""

    __tablename__ = "eval_case_attempts"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "case_id",
            name="uq_eval_case_attempts_run_case",
        ),
        CheckConstraint(
            "status IN ('queued', 'passed', 'failed', 'error')",
            name="eval_case_attempts_status",
        ),
        CheckConstraint(
            f"reason IS NULL OR length(CAST(reason AS BLOB)) BETWEEN 1 AND {MAX_REASON_BYTES}",
            name="eval_case_attempts_reason_bytes",
        ),
        CheckConstraint(
            f"duration_ms IS NULL OR duration_ms BETWEEN 0 AND {MAX_DURATION_MS}",
            name="eval_case_attempts_duration",
        ),
        CheckConstraint(
            "(subject_service_namespace IS NULL "
            "AND subject_service_name IS NULL "
            "AND subject_executable_type IS NULL "
            "AND subject_runtime_id IS NULL "
            "AND execution_bound_at IS NULL) "
            "OR "
            "(subject_service_namespace IS NOT NULL "
            "AND subject_service_name IS NOT NULL "
            "AND subject_executable_type IS NOT NULL "
            "AND subject_runtime_id IS NOT NULL "
            "AND execution_bound_at IS NOT NULL)",
            name="eval_case_attempts_subject_execution",
        ),
        CheckConstraint(
            "subject_executable_type IS NULL "
            "OR subject_executable_type IN ('workflow', 'subflow', 'agent')",
            name="eval_case_attempts_subject_executable_type",
        ),
        CheckConstraint(
            "subject_service_namespace IS NULL OR "
            f"length(CAST(subject_service_namespace AS BLOB)) "
            f"<= {MAX_EXECUTION_IDENTITY_BYTES}",
            name="eval_case_attempts_subject_namespace_bytes",
        ),
        CheckConstraint(
            "subject_service_name IS NULL OR "
            f"length(CAST(subject_service_name AS BLOB)) BETWEEN 1 "
            f"AND {MAX_EXECUTION_IDENTITY_BYTES}",
            name="eval_case_attempts_subject_service_name_bytes",
        ),
        CheckConstraint(
            "subject_runtime_id IS NULL OR "
            f"length(CAST(subject_runtime_id AS BLOB)) BETWEEN 1 "
            f"AND {MAX_EXECUTION_IDENTITY_BYTES}",
            name="eval_case_attempts_subject_runtime_id_bytes",
        ),
        CheckConstraint(
            "(status = 'queued' "
            "AND reason IS NULL "
            "AND duration_ms IS NULL "
            "AND recorded_at IS NULL) "
            "OR "
            "(status IN ('passed', 'failed') "
            "AND reason IS NOT NULL "
            "AND subject_runtime_id IS NOT NULL "
            "AND recorded_at IS NOT NULL) "
            "OR "
            "(status = 'error' "
            "AND reason IS NOT NULL "
            "AND recorded_at IS NOT NULL)",
            name="eval_case_attempts_terminal_fields",
        ),
        Index("ix_eval_case_attempts_run_status", "run_id", "status"),
        Index("ix_eval_case_attempts_case_run", "case_id", "run_id"),
        Index(
            "uq_eval_case_attempts_subject_execution",
            "subject_service_namespace",
            "subject_service_name",
            "subject_executable_type",
            "subject_runtime_id",
            unique=True,
            sqlite_where=text("subject_runtime_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(22),
        primary_key=True,
        default=lambda: generate_id(size=22),
    )
    run_id: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("eval_runs.id"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("eval_cases.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(6), nullable=False, default="queued")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject_service_namespace: Mapped[str | None] = mapped_column(
        String(MAX_EXECUTION_IDENTITY_BYTES),
        nullable=True,
    )
    subject_service_name: Mapped[str | None] = mapped_column(
        String(MAX_EXECUTION_IDENTITY_BYTES),
        nullable=True,
    )
    subject_executable_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    subject_runtime_id: Mapped[str | None] = mapped_column(
        String(MAX_EXECUTION_IDENTITY_BYTES),
        nullable=True,
    )
    execution_bound_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

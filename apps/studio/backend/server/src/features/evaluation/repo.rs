//! Statements and transactions for the evaluation tables.
//!
//! A write is one function that runs its whole transaction on the writer
//! connection. A read that needs several statements to agree runs them in one
//! read transaction.
//!
//! Every statement lists a table's columns in one order, the order the
//! `*_from_row` function for that table reads them in.

use std::collections::HashMap;
use std::collections::hash_map::Entry;

use rusqlite::types::{FromSql, FromSqlError, FromSqlResult, ValueRef};
use rusqlite::{Connection, OptionalExtension, Row, TransactionBehavior, params};

use super::schemas::{
    AttemptStatus, CaseOrigin, DatasetStatus, EvaluationAttemptDetail, EvaluationAttemptRead,
    EvaluationAttemptResult, EvaluationCaseCreate, EvaluationCaseRead, EvaluationDatasetCreate,
    EvaluationDatasetDetail, EvaluationDatasetRead, EvaluationDatasetSummary,
    EvaluationEvidenceMembership, EvaluationNameFacet, EvaluationOutcomeSummary, EvaluationRunCase,
    EvaluationRunDetail, EvaluationRunRead, EvaluationRunScope, EvaluationRunStart,
    EvaluationRunSummary, EvaluationTargetFacet, EvidenceMembershipRole, ExecutableType,
    ExecutionEvidenceReference, ExecutionIdentityText, JsonValue, MAX_CASES_PER_DATASET,
    OpenTelemetrySpanKind, OpenTelemetrySpanReference, RunStatus, SemanticExecutionKind,
    SemanticExecutionReference, ServiceNamespaceText, SpanId, TargetKind, TraceId,
};
use crate::ids::generate_id;
use crate::pagination::TimePosition;
use crate::timestamps::UtcSeconds;

pub const INSERT_DATASET: &str = "
    INSERT INTO eval_datasets (
        id, application_key, key, name, status, description, created_by_user_id,
        created_at, locked_at
    ) VALUES (?1, ?2, ?3, ?4, 'draft', ?5, ?6, ?7, NULL)";
pub const SELECT_DATASET: &str = "
    SELECT d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at
    FROM eval_datasets AS d
    WHERE d.id = ?1";
pub const SELECT_DATASET_BY_KEY: &str = "
    SELECT d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at
    FROM eval_datasets AS d
    WHERE d.application_key = ?1 AND d.key = ?2";
pub const SELECT_NEWEST_DATASETS: &str = "
    SELECT d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at
    FROM eval_datasets AS d
    ORDER BY d.created_at DESC, d.id DESC
    LIMIT ?1";
pub const SELECT_DATASETS_AFTER: &str = "
    SELECT d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at
    FROM eval_datasets AS d
    WHERE d.created_at < ?1 OR (d.created_at = ?1 AND d.id < ?2)
    ORDER BY d.created_at DESC, d.id DESC
    LIMIT ?3";
pub const SELECT_NEWEST_APPLICATION_DATASETS: &str = "
    SELECT d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at
    FROM eval_datasets AS d
    WHERE d.application_key = ?1
    ORDER BY d.created_at DESC, d.id DESC
    LIMIT ?2";
pub const SELECT_APPLICATION_DATASETS_AFTER: &str = "
    SELECT d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at
    FROM eval_datasets AS d
    WHERE d.application_key = ?1
      AND (d.created_at < ?2 OR (d.created_at = ?2 AND d.id < ?3))
    ORDER BY d.created_at DESC, d.id DESC
    LIMIT ?4";
pub const LOCK_DATASET: &str = "
    UPDATE eval_datasets SET status = 'locked', locked_at = ?2
    WHERE id = ?1 AND status = 'draft'";

pub const INSERT_CASE: &str = "
    INSERT INTO eval_cases (
        id, dataset_id, case_key, evaluation_name, ordinal, origin, target_kind,
        target_key, target_name, input_version, input_json, expectation_json,
        evaluator_key, evaluator_version, source_evidence_kind,
        source_service_namespace, source_service_name, source_executable_type,
        source_runtime_id, source_trace_id, source_span_id, source_revision,
        created_at
    ) VALUES (
        ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16,
        ?17, ?18, ?19, ?20, ?21, ?22, ?23
    )";
pub const SELECT_CASE_BY_KEY: &str = "
    SELECT c.id, c.dataset_id, c.case_key, c.evaluation_name, c.ordinal,
           c.origin, c.target_kind, c.target_key, c.target_name,
           c.input_version, c.input_json, c.expectation_json, c.evaluator_key,
           c.evaluator_version, c.source_evidence_kind,
           c.source_service_namespace, c.source_service_name,
           c.source_executable_type, c.source_runtime_id, c.source_trace_id,
           c.source_span_id, c.source_revision, c.created_at
    FROM eval_cases AS c
    WHERE c.dataset_id = ?1 AND c.case_key = ?2";
pub const SELECT_DATASET_CASES: &str = "
    SELECT c.id, c.dataset_id, c.case_key, c.evaluation_name, c.ordinal,
           c.origin, c.target_kind, c.target_key, c.target_name,
           c.input_version, c.input_json, c.expectation_json, c.evaluator_key,
           c.evaluator_version, c.source_evidence_kind,
           c.source_service_namespace, c.source_service_name,
           c.source_executable_type, c.source_runtime_id, c.source_trace_id,
           c.source_span_id, c.source_revision, c.created_at
    FROM eval_cases AS c
    WHERE c.dataset_id = ?1
    ORDER BY c.ordinal, c.id";
pub const COUNT_DATASET_CASES: &str = "SELECT COUNT(*) FROM eval_cases WHERE dataset_id = ?1";
pub const SELECT_DATASET_CASE_IDS: &str = "
    SELECT id FROM eval_cases WHERE dataset_id = ?1 ORDER BY ordinal, id";

pub const INSERT_RUN: &str = "
    INSERT INTO eval_runs (
        id, dataset_id, request_key, run_label, source_revision, status,
        created_by_user_id, created_at, completed_at
    ) VALUES (?1, ?2, ?3, ?4, ?5, 'active', ?6, ?7, NULL)";
pub const INSERT_ATTEMPT: &str = "
    INSERT INTO eval_case_attempts (id, run_id, case_id, status)
    VALUES (?1, ?2, ?3, 'queued')";
pub const SELECT_RUN_BY_REQUEST_KEY: &str = "
    SELECT id, run_label, source_revision
    FROM eval_runs
    WHERE dataset_id = ?1 AND request_key = ?2";
pub const SELECT_RUN: &str = "
    SELECT r.id, r.dataset_id, r.request_key, r.run_label, r.source_revision,
           r.status, r.created_by_user_id, r.created_at, r.completed_at,
           d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at
    FROM eval_runs AS r
    JOIN eval_datasets AS d ON d.id = r.dataset_id
    WHERE r.id = ?1";
pub const SELECT_RUN_CASES: &str = "
    SELECT c.id, c.dataset_id, c.case_key, c.evaluation_name, c.ordinal,
           c.origin, c.target_kind, c.target_key, c.target_name,
           c.input_version, c.input_json, c.expectation_json, c.evaluator_key,
           c.evaluator_version, c.source_evidence_kind,
           c.source_service_namespace, c.source_service_name,
           c.source_executable_type, c.source_runtime_id, c.source_trace_id,
           c.source_span_id, c.source_revision, c.created_at,
           a.id, a.run_id, a.case_id, a.status, a.reason, a.duration_ms,
           a.subject_evidence_kind, a.subject_service_namespace,
           a.subject_service_name, a.subject_executable_type,
           a.subject_runtime_id, a.subject_trace_id, a.subject_span_id,
           a.evidence_bound_at, a.recorded_at
    FROM eval_cases AS c
    JOIN eval_case_attempts AS a ON a.case_id = c.id AND a.run_id = ?1
    WHERE c.dataset_id = ?2
    ORDER BY c.ordinal, c.id";

// The four run listings share one case scope in parameters 1 to 4. A scope
// member that is null matches every case. A scope with no member set lists
// every run.
pub const SELECT_NEWEST_RUNS: &str = "
    SELECT r.id, r.dataset_id, r.request_key, r.run_label, r.source_revision,
           r.status, r.created_by_user_id, r.created_at, r.completed_at,
           d.id, d.application_key, d.key, d.name, d.status
    FROM eval_runs AS r
    JOIN eval_datasets AS d ON d.id = r.dataset_id
    WHERE (
        (?1 IS NULL AND ?2 IS NULL AND ?3 IS NULL AND ?4 IS NULL)
        OR EXISTS (
            SELECT 1 FROM eval_cases AS c
            WHERE c.dataset_id = r.dataset_id
              AND (?1 IS NULL OR c.target_kind = ?1)
              AND (?2 IS NULL OR c.target_key = ?2)
              AND (?3 IS NULL OR c.input_version = ?3)
              AND (?4 IS NULL OR c.evaluation_name = ?4)
        )
    )
    ORDER BY r.created_at DESC, r.id DESC
    LIMIT ?5";
pub const SELECT_RUNS_AFTER: &str = "
    SELECT r.id, r.dataset_id, r.request_key, r.run_label, r.source_revision,
           r.status, r.created_by_user_id, r.created_at, r.completed_at,
           d.id, d.application_key, d.key, d.name, d.status
    FROM eval_runs AS r
    JOIN eval_datasets AS d ON d.id = r.dataset_id
    WHERE (r.created_at < ?5 OR (r.created_at = ?5 AND r.id < ?6))
      AND (
        (?1 IS NULL AND ?2 IS NULL AND ?3 IS NULL AND ?4 IS NULL)
        OR EXISTS (
            SELECT 1 FROM eval_cases AS c
            WHERE c.dataset_id = r.dataset_id
              AND (?1 IS NULL OR c.target_kind = ?1)
              AND (?2 IS NULL OR c.target_key = ?2)
              AND (?3 IS NULL OR c.input_version = ?3)
              AND (?4 IS NULL OR c.evaluation_name = ?4)
        )
    )
    ORDER BY r.created_at DESC, r.id DESC
    LIMIT ?7";
pub const SELECT_NEWEST_DATASET_RUNS: &str = "
    SELECT r.id, r.dataset_id, r.request_key, r.run_label, r.source_revision,
           r.status, r.created_by_user_id, r.created_at, r.completed_at,
           d.id, d.application_key, d.key, d.name, d.status
    FROM eval_runs AS r
    JOIN eval_datasets AS d ON d.id = r.dataset_id
    WHERE r.dataset_id = ?5
      AND (
        (?1 IS NULL AND ?2 IS NULL AND ?3 IS NULL AND ?4 IS NULL)
        OR EXISTS (
            SELECT 1 FROM eval_cases AS c
            WHERE c.dataset_id = r.dataset_id
              AND (?1 IS NULL OR c.target_kind = ?1)
              AND (?2 IS NULL OR c.target_key = ?2)
              AND (?3 IS NULL OR c.input_version = ?3)
              AND (?4 IS NULL OR c.evaluation_name = ?4)
        )
    )
    ORDER BY r.created_at DESC, r.id DESC
    LIMIT ?6";
pub const SELECT_DATASET_RUNS_AFTER: &str = "
    SELECT r.id, r.dataset_id, r.request_key, r.run_label, r.source_revision,
           r.status, r.created_by_user_id, r.created_at, r.completed_at,
           d.id, d.application_key, d.key, d.name, d.status
    FROM eval_runs AS r
    JOIN eval_datasets AS d ON d.id = r.dataset_id
    WHERE r.dataset_id = ?5
      AND (r.created_at < ?6 OR (r.created_at = ?6 AND r.id < ?7))
      AND (
        (?1 IS NULL AND ?2 IS NULL AND ?3 IS NULL AND ?4 IS NULL)
        OR EXISTS (
            SELECT 1 FROM eval_cases AS c
            WHERE c.dataset_id = r.dataset_id
              AND (?1 IS NULL OR c.target_kind = ?1)
              AND (?2 IS NULL OR c.target_key = ?2)
              AND (?3 IS NULL OR c.input_version = ?3)
              AND (?4 IS NULL OR c.evaluation_name = ?4)
        )
    )
    ORDER BY r.created_at DESC, r.id DESC
    LIMIT ?8";
pub const COUNT_RUN_OUTCOMES: &str = "
    SELECT a.status, COUNT(*)
    FROM eval_case_attempts AS a
    JOIN eval_cases AS c ON c.id = a.case_id
    WHERE a.run_id = ?5
      AND (?1 IS NULL OR c.target_kind = ?1)
      AND (?2 IS NULL OR c.target_key = ?2)
      AND (?3 IS NULL OR c.input_version = ?3)
      AND (?4 IS NULL OR c.evaluation_name = ?4)
    GROUP BY a.status";
pub const SELECT_TARGET_FACETS: &str = "
    SELECT target_kind, target_key, target_name, input_version, COUNT(*)
    FROM eval_cases
    WHERE dataset_id = ?1
    GROUP BY target_kind, target_key, target_name, input_version
    ORDER BY target_kind, target_key, target_name, input_version";
pub const SELECT_EVALUATION_FACETS: &str = "
    SELECT evaluation_name, COUNT(*)
    FROM eval_cases
    WHERE dataset_id = ?1
    GROUP BY evaluation_name
    ORDER BY evaluation_name";
pub const COMPLETE_RUN: &str = "
    UPDATE eval_runs SET status = 'completed', completed_at = ?2
    WHERE id = ?1
      AND status = 'active'
      AND NOT EXISTS (
        SELECT 1 FROM eval_case_attempts WHERE run_id = ?1 AND status = 'queued'
      )";

pub const SELECT_ATTEMPT: &str = "
    SELECT a.id, a.run_id, a.case_id, a.status, a.reason, a.duration_ms,
           a.subject_evidence_kind, a.subject_service_namespace,
           a.subject_service_name, a.subject_executable_type,
           a.subject_runtime_id, a.subject_trace_id, a.subject_span_id,
           a.evidence_bound_at, a.recorded_at
    FROM eval_case_attempts AS a
    WHERE a.id = ?1";
pub const SELECT_ATTEMPT_DETAIL: &str = "
    SELECT r.id, r.dataset_id, r.request_key, r.run_label, r.source_revision,
           r.status, r.created_by_user_id, r.created_at, r.completed_at,
           d.id, d.application_key, d.key, d.name, d.status, d.description,
           d.created_by_user_id, d.created_at, d.locked_at,
           c.id, c.dataset_id, c.case_key, c.evaluation_name, c.ordinal,
           c.origin, c.target_kind, c.target_key, c.target_name,
           c.input_version, c.input_json, c.expectation_json, c.evaluator_key,
           c.evaluator_version, c.source_evidence_kind,
           c.source_service_namespace, c.source_service_name,
           c.source_executable_type, c.source_runtime_id, c.source_trace_id,
           c.source_span_id, c.source_revision, c.created_at,
           a.id, a.run_id, a.case_id, a.status, a.reason, a.duration_ms,
           a.subject_evidence_kind, a.subject_service_namespace,
           a.subject_service_name, a.subject_executable_type,
           a.subject_runtime_id, a.subject_trace_id, a.subject_span_id,
           a.evidence_bound_at, a.recorded_at
    FROM eval_case_attempts AS a
    JOIN eval_runs AS r ON r.id = a.run_id
    JOIN eval_datasets AS d ON d.id = r.dataset_id
    JOIN eval_cases AS c ON c.id = a.case_id
    WHERE a.id = ?1";
pub const BIND_ATTEMPT_EVIDENCE: &str = "
    UPDATE eval_case_attempts SET
        subject_evidence_kind = ?2,
        subject_service_namespace = ?3,
        subject_service_name = ?4,
        subject_executable_type = ?5,
        subject_runtime_id = ?6,
        subject_trace_id = ?7,
        subject_span_id = ?8,
        evidence_bound_at = ?9
    WHERE id = ?1";
pub const RECORD_ATTEMPT_RESULT: &str = "
    UPDATE eval_case_attempts SET
        status = ?2, reason = ?3, duration_ms = ?4, recorded_at = ?5
    WHERE id = ?1";

// The membership listings name the evidence kind as a literal so the partial
// indexes on that kind apply. Attempt subjects sort before case sources.
// Parameters 5 and 6 are the position to continue after, or null to start.
pub const SELECT_JUNJO_EXECUTION_MEMBERSHIP: &str = "
    SELECT role, dataset_id, case_id, run_id, attempt_id
    FROM (
        SELECT 'case_source' AS role, c.id AS record_id,
               c.dataset_id AS dataset_id, c.id AS case_id, NULL AS run_id,
               NULL AS attempt_id
        FROM eval_cases AS c
        WHERE c.source_evidence_kind = 'junjo_execution'
          AND c.source_service_namespace = ?1
          AND c.source_service_name = ?2
          AND c.source_executable_type = ?3
          AND c.source_runtime_id = ?4
        UNION ALL
        SELECT 'attempt_subject', a.id, r.dataset_id, a.case_id, a.run_id, a.id
        FROM eval_case_attempts AS a
        JOIN eval_runs AS r ON r.id = a.run_id
        WHERE a.subject_evidence_kind = 'junjo_execution'
          AND a.subject_service_namespace = ?1
          AND a.subject_service_name = ?2
          AND a.subject_executable_type = ?3
          AND a.subject_runtime_id = ?4
    )
    WHERE ?5 IS NULL OR role > ?5 OR (role = ?5 AND record_id > ?6)
    ORDER BY role, record_id
    LIMIT ?7";
pub const SELECT_OTEL_SPAN_MEMBERSHIP: &str = "
    SELECT role, dataset_id, case_id, run_id, attempt_id
    FROM (
        SELECT 'case_source' AS role, c.id AS record_id,
               c.dataset_id AS dataset_id, c.id AS case_id, NULL AS run_id,
               NULL AS attempt_id
        FROM eval_cases AS c
        WHERE c.source_evidence_kind = 'otel_span'
          AND c.source_service_namespace = ?1
          AND c.source_service_name = ?2
          AND c.source_trace_id = ?3
          AND c.source_span_id = ?4
        UNION ALL
        SELECT 'attempt_subject', a.id, r.dataset_id, a.case_id, a.run_id, a.id
        FROM eval_case_attempts AS a
        JOIN eval_runs AS r ON r.id = a.run_id
        WHERE a.subject_evidence_kind = 'otel_span'
          AND a.subject_service_namespace = ?1
          AND a.subject_service_name = ?2
          AND a.subject_trace_id = ?3
          AND a.subject_span_id = ?4
    )
    WHERE ?5 IS NULL OR role > ?5 OR (role = ?5 AND record_id > ?6)
    ORDER BY role, record_id
    LIMIT ?7";

#[cfg(test)]
pub const ALL_STATEMENTS: [&str; 32] = [
    INSERT_DATASET,
    SELECT_DATASET,
    SELECT_DATASET_BY_KEY,
    SELECT_NEWEST_DATASETS,
    SELECT_DATASETS_AFTER,
    SELECT_NEWEST_APPLICATION_DATASETS,
    SELECT_APPLICATION_DATASETS_AFTER,
    LOCK_DATASET,
    INSERT_CASE,
    SELECT_CASE_BY_KEY,
    SELECT_DATASET_CASES,
    COUNT_DATASET_CASES,
    SELECT_DATASET_CASE_IDS,
    INSERT_RUN,
    INSERT_ATTEMPT,
    SELECT_RUN_BY_REQUEST_KEY,
    SELECT_RUN,
    SELECT_RUN_CASES,
    SELECT_NEWEST_RUNS,
    SELECT_RUNS_AFTER,
    SELECT_NEWEST_DATASET_RUNS,
    SELECT_DATASET_RUNS_AFTER,
    COUNT_RUN_OUTCOMES,
    SELECT_TARGET_FACETS,
    SELECT_EVALUATION_FACETS,
    COMPLETE_RUN,
    SELECT_ATTEMPT,
    SELECT_ATTEMPT_DETAIL,
    BIND_ATTEMPT_EVIDENCE,
    RECORD_ATTEMPT_RESULT,
    SELECT_JUNJO_EXECUTION_MEMBERSHIP,
    SELECT_OTEL_SPAN_MEMBERSHIP,
];

/// How many columns each `*_from_row` function reads. A statement that
/// selects several tables lists them one after another.
const RUN_COLUMNS: usize = 9;
const DATASET_COLUMNS: usize = 9;
const CASE_COLUMNS: usize = 23;

/// Why an operation was not carried out.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Refusal {
    /// The named kind of record does not exist.
    NotFound(&'static str),
    /// The request conflicts with stored state. Callers match on the code.
    Conflict {
        code: &'static str,
        message: &'static str,
    },
}

/// What an operation the database carried out, or refused, produced.
pub type Outcome<T> = Result<T, Refusal>;

const DATASET_NOT_FOUND: Refusal = Refusal::NotFound("Dataset");
const ATTEMPT_NOT_FOUND: Refusal = Refusal::NotFound("Attempt");
const DATASET_IDENTITY_CONFLICT: Refusal = Refusal::Conflict {
    code: "dataset_identity_conflict",
    message: "Dataset key already exists with different content.",
};
const CASE_IDENTITY_CONFLICT: Refusal = Refusal::Conflict {
    code: "case_identity_conflict",
    message: "Case key already exists with different content.",
};
const DATASET_LOCKED: Refusal = Refusal::Conflict {
    code: "dataset_locked",
    message: "Locked datasets cannot accept new cases.",
};
const DATASET_CASE_LIMIT_REACHED: Refusal = Refusal::Conflict {
    code: "dataset_case_limit_reached",
    message: "A dataset may contain at most 100 cases.",
};
const RUN_IDENTITY_CONFLICT: Refusal = Refusal::Conflict {
    code: "run_identity_conflict",
    message: "Run request key already exists with different content.",
};
const DATASET_NOT_LOCKED: Refusal = Refusal::Conflict {
    code: "dataset_not_locked",
    message: "A run may start only from a locked dataset.",
};
const DATASET_EMPTY: Refusal = Refusal::Conflict {
    code: "dataset_empty",
    message: "A run requires at least one dataset case.",
};
const ATTEMPT_EVIDENCE_CONFLICT: Refusal = Refusal::Conflict {
    code: "attempt_evidence_conflict",
    message: "Attempt is already bound to different evidence.",
};
const ATTEMPT_TERMINAL: Refusal = Refusal::Conflict {
    code: "attempt_terminal",
    message: "A terminal attempt cannot acquire an evidence binding.",
};
const EVIDENCE_ALREADY_BOUND: Refusal = Refusal::Conflict {
    code: "evidence_already_bound",
    message: "Evidence is already bound to another attempt.",
};
const ATTEMPT_RESULT_CONFLICT: Refusal = Refusal::Conflict {
    code: "attempt_result_conflict",
    message: "Attempt already has a different terminal result.",
};
const ATTEMPT_EVIDENCE_REQUIRED: Refusal = Refusal::Conflict {
    code: "attempt_evidence_required",
    message: "Passed and failed attempts require bound evidence.",
};

/// A membership's place in its listing: by role, then by the identifier of
/// the attempt or the case.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MembershipPosition {
    pub role: EvidenceMembershipRole,
    pub record_id: String,
}

// An enumeration is stored as the name it serializes to.
fn unknown_stored_name(name: &str) -> FromSqlError {
    FromSqlError::Other(format!("unknown stored name {name:?}").into())
}

impl FromSql for DatasetStatus {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "draft" => Ok(Self::Draft),
            "locked" => Ok(Self::Locked),
            other => Err(unknown_stored_name(other)),
        }
    }
}

impl FromSql for CaseOrigin {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "authored" => Ok(Self::Authored),
            "generated" => Ok(Self::Generated),
            other => Err(unknown_stored_name(other)),
        }
    }
}

impl FromSql for TargetKind {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "node" => Ok(Self::Node),
            "workflow" => Ok(Self::Workflow),
            "agent" => Ok(Self::Agent),
            other => Err(unknown_stored_name(other)),
        }
    }
}

impl FromSql for ExecutableType {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "workflow" => Ok(Self::Workflow),
            "subflow" => Ok(Self::Subflow),
            "agent" => Ok(Self::Agent),
            other => Err(unknown_stored_name(other)),
        }
    }
}

impl FromSql for RunStatus {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "active" => Ok(Self::Active),
            "completed" => Ok(Self::Completed),
            other => Err(unknown_stored_name(other)),
        }
    }
}

impl FromSql for AttemptStatus {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "queued" => Ok(Self::Queued),
            "passed" => Ok(Self::Passed),
            "failed" => Ok(Self::Failed),
            "error" => Ok(Self::Error),
            other => Err(unknown_stored_name(other)),
        }
    }
}

impl FromSql for EvidenceMembershipRole {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "case_source" => Ok(Self::CaseSource),
            "attempt_subject" => Ok(Self::AttemptSubject),
            other => Err(unknown_stored_name(other)),
        }
    }
}

impl FromSql for JsonValue {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        serde_json::from_str(value.as_str()?)
            .map(Self)
            .map_err(|error| FromSqlError::Other(Box::new(error)))
    }
}

/// One evidence reference as its seven stored columns. No reference is seven
/// nulls.
#[derive(Default)]
struct EvidenceColumns<'a> {
    kind: Option<&'static str>,
    service_namespace: Option<&'a str>,
    service_name: Option<&'a str>,
    executable_type: Option<&'static str>,
    runtime_id: Option<&'a str>,
    trace_id: Option<&'a str>,
    span_id: Option<&'a str>,
}

impl<'a> EvidenceColumns<'a> {
    fn of(reference: Option<&'a ExecutionEvidenceReference>) -> Self {
        match reference {
            None => Self::default(),
            Some(ExecutionEvidenceReference::JunjoExecution(reference)) => Self {
                kind: Some("junjo_execution"),
                service_namespace: Some(&reference.service_namespace.0),
                service_name: Some(&reference.service_name.0),
                executable_type: Some(reference.executable_type.as_str()),
                runtime_id: Some(&reference.runtime_id.0),
                trace_id: None,
                span_id: None,
            },
            Some(ExecutionEvidenceReference::OtelSpan(reference)) => Self {
                kind: Some("otel_span"),
                service_namespace: Some(&reference.service_namespace.0),
                service_name: Some(&reference.service_name.0),
                executable_type: None,
                runtime_id: None,
                trace_id: Some(&reference.trace_id.0),
                span_id: Some(&reference.span_id.0),
            },
        }
    }
}

/// Read an evidence reference from its seven columns, starting at `first`.
fn evidence_from_row(
    row: &Row<'_>,
    first: usize,
) -> rusqlite::Result<Option<ExecutionEvidenceReference>> {
    Ok(match row.get_ref(first)?.as_str_or_null()? {
        None => None,
        Some("junjo_execution") => Some(ExecutionEvidenceReference::JunjoExecution(
            SemanticExecutionReference {
                kind: SemanticExecutionKind::JunjoExecution,
                service_namespace: ServiceNamespaceText(row.get(first + 1)?),
                service_name: ExecutionIdentityText(row.get(first + 2)?),
                executable_type: row.get(first + 3)?,
                runtime_id: ExecutionIdentityText(row.get(first + 4)?),
            },
        )),
        Some("otel_span") => Some(ExecutionEvidenceReference::OtelSpan(
            OpenTelemetrySpanReference {
                kind: OpenTelemetrySpanKind::OtelSpan,
                service_namespace: ServiceNamespaceText(row.get(first + 1)?),
                service_name: ExecutionIdentityText(row.get(first + 2)?),
                trace_id: TraceId(row.get(first + 5)?),
                span_id: SpanId(row.get(first + 6)?),
            },
        )),
        Some(other) => return Err(unknown_stored_name(other).into()),
    })
}

/// Read the five columns a dataset summary and a dataset share, starting at
/// `first`.
fn dataset_summary_from_row(
    row: &Row<'_>,
    first: usize,
) -> rusqlite::Result<EvaluationDatasetSummary> {
    Ok(EvaluationDatasetSummary {
        id: row.get(first)?,
        application_key: row.get(first + 1)?,
        key: row.get(first + 2)?,
        name: row.get(first + 3)?,
        status: row.get(first + 4)?,
    })
}

fn dataset_from_row(row: &Row<'_>, first: usize) -> rusqlite::Result<EvaluationDatasetRead> {
    Ok(EvaluationDatasetRead {
        id: row.get(first)?,
        application_key: row.get(first + 1)?,
        key: row.get(first + 2)?,
        name: row.get(first + 3)?,
        status: row.get(first + 4)?,
        description: row.get(first + 5)?,
        created_by_user_id: row.get(first + 6)?,
        created_at: row.get(first + 7)?,
        locked_at: row.get(first + 8)?,
    })
}

fn case_from_row(row: &Row<'_>, first: usize) -> rusqlite::Result<EvaluationCaseRead> {
    Ok(EvaluationCaseRead {
        id: row.get(first)?,
        dataset_id: row.get(first + 1)?,
        case_key: row.get(first + 2)?,
        evaluation_name: row.get(first + 3)?,
        ordinal: row.get(first + 4)?,
        origin: row.get(first + 5)?,
        target_kind: row.get(first + 6)?,
        target_key: row.get(first + 7)?,
        target_name: row.get(first + 8)?,
        input_version: row.get(first + 9)?,
        input_json: row.get(first + 10)?,
        expectation_json: row.get(first + 11)?,
        evaluator_key: row.get(first + 12)?,
        evaluator_version: row.get(first + 13)?,
        source_evidence: evidence_from_row(row, first + 14)?,
        source_revision: row.get(first + 21)?,
        created_at: row.get(first + 22)?,
    })
}

fn run_from_row(row: &Row<'_>, first: usize) -> rusqlite::Result<EvaluationRunRead> {
    Ok(EvaluationRunRead {
        id: row.get(first)?,
        dataset_id: row.get(first + 1)?,
        request_key: row.get(first + 2)?,
        run_label: row.get(first + 3)?,
        source_revision: row.get(first + 4)?,
        status: row.get(first + 5)?,
        created_by_user_id: row.get(first + 6)?,
        created_at: row.get(first + 7)?,
        completed_at: row.get(first + 8)?,
    })
}

fn attempt_from_row(row: &Row<'_>, first: usize) -> rusqlite::Result<EvaluationAttemptRead> {
    Ok(EvaluationAttemptRead {
        id: row.get(first)?,
        run_id: row.get(first + 1)?,
        case_id: row.get(first + 2)?,
        status: row.get(first + 3)?,
        reason: row.get(first + 4)?,
        duration_ms: row.get(first + 5)?,
        subject_evidence: evidence_from_row(row, first + 6)?,
        evidence_bound_at: row.get(first + 13)?,
        recorded_at: row.get(first + 14)?,
    })
}

fn membership_from_row(row: &Row<'_>) -> rusqlite::Result<EvaluationEvidenceMembership> {
    Ok(EvaluationEvidenceMembership {
        role: row.get(0)?,
        dataset_id: row.get(1)?,
        case_id: row.get(2)?,
        run_id: row.get(3)?,
        attempt_id: row.get(4)?,
    })
}

/// A record this transaction wrote, read back. Its absence is a failure.
fn stored<T>(record: Option<T>) -> rusqlite::Result<T> {
    record.ok_or(rusqlite::Error::QueryReturnedNoRows)
}

fn dataset_by_id(
    connection: &Connection,
    dataset_id: &str,
) -> rusqlite::Result<Option<EvaluationDatasetRead>> {
    connection
        .prepare_cached(SELECT_DATASET)?
        .query_row(params![dataset_id], |row| dataset_from_row(row, 0))
        .optional()
}

fn case_by_key(
    connection: &Connection,
    dataset_id: &str,
    case_key: &str,
) -> rusqlite::Result<Option<EvaluationCaseRead>> {
    connection
        .prepare_cached(SELECT_CASE_BY_KEY)?
        .query_row(params![dataset_id, case_key], |row| case_from_row(row, 0))
        .optional()
}

fn attempt_by_id(
    connection: &Connection,
    attempt_id: &str,
) -> rusqlite::Result<Option<EvaluationAttemptRead>> {
    connection
        .prepare_cached(SELECT_ATTEMPT)?
        .query_row(params![attempt_id], |row| attempt_from_row(row, 0))
        .optional()
}

/// Create a dataset. A repeated request returns the dataset it created.
pub fn create_dataset(
    connection: &mut Connection,
    request: &EvaluationDatasetCreate,
    user_id: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Outcome<EvaluationDatasetRead>> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let description = request
        .description
        .as_ref()
        .map(|description| description.0.as_str());
    let existing = transaction
        .prepare_cached(SELECT_DATASET_BY_KEY)?
        .query_row(params![request.application_key.0, request.key.0], |row| {
            dataset_from_row(row, 0)
        })
        .optional()?;
    if let Some(existing) = existing {
        let same_content =
            existing.name == request.name.0 && existing.description.as_deref() == description;
        return Ok(if same_content {
            Ok(existing)
        } else {
            Err(DATASET_IDENTITY_CONFLICT)
        });
    }

    let id = generate_id();
    transaction
        .prepare_cached(INSERT_DATASET)?
        .execute(params![
            id,
            request.application_key.0,
            request.key.0,
            request.name.0,
            description,
            user_id,
            now,
        ])?;
    let dataset = stored(dataset_by_id(&transaction, &id)?)?;
    transaction.commit()?;
    Ok(Ok(dataset))
}

/// Up to `limit` datasets, newest first, starting after `after`. An
/// application key limits the listing to that application's datasets.
pub fn list_datasets(
    connection: &Connection,
    application_key: Option<&str>,
    after: Option<&TimePosition>,
    limit: u32,
) -> rusqlite::Result<Vec<EvaluationDatasetRead>> {
    let dataset = |row: &Row<'_>| dataset_from_row(row, 0);
    match (application_key, after) {
        (None, None) => connection
            .prepare_cached(SELECT_NEWEST_DATASETS)?
            .query_map(params![limit], dataset)?
            .collect(),
        (None, Some(after)) => connection
            .prepare_cached(SELECT_DATASETS_AFTER)?
            .query_map(params![after.created_at, after.id, limit], dataset)?
            .collect(),
        (Some(application_key), None) => connection
            .prepare_cached(SELECT_NEWEST_APPLICATION_DATASETS)?
            .query_map(params![application_key, limit], dataset)?
            .collect(),
        (Some(application_key), Some(after)) => connection
            .prepare_cached(SELECT_APPLICATION_DATASETS_AFTER)?
            .query_map(
                params![application_key, after.created_at, after.id, limit],
                dataset,
            )?
            .collect(),
    }
}

/// One dataset with its cases in order.
pub fn get_dataset(
    connection: &mut Connection,
    dataset_id: &str,
) -> rusqlite::Result<Option<EvaluationDatasetDetail>> {
    // One read transaction, so the dataset and its cases are one snapshot.
    let transaction = connection.transaction()?;
    let Some(dataset) = dataset_by_id(&transaction, dataset_id)? else {
        return Ok(None);
    };
    let cases = transaction
        .prepare_cached(SELECT_DATASET_CASES)?
        .query_map(params![dataset_id], |row| case_from_row(row, 0))?
        .collect::<rusqlite::Result<_>>()?;
    Ok(Some(EvaluationDatasetDetail { dataset, cases }))
}

/// Whether a stored case has the content a request describes.
fn has_same_content(existing: &EvaluationCaseRead, request: &EvaluationCaseCreate) -> bool {
    // Stored JSON text is canonical, so serializing a stored value
    // reproduces the text it is compared by.
    let input_json = existing.input_json.0.to_string();
    let expectation_json = existing
        .expectation_json
        .as_ref()
        .map(|json| json.0.to_string());
    existing.evaluation_name == request.evaluation_name.0
        && existing.origin == request.origin
        && existing.target_kind == request.target_kind
        && existing.target_key == request.target_key.0
        && existing.target_name == request.target_name.0
        && existing.input_version == request.input_version.0
        && input_json == request.input_json.0
        && expectation_json.as_deref()
            == request
                .expectation_json
                .as_ref()
                .map(|json| json.0.as_str())
        && existing.evaluator_key == request.evaluator_key.0
        && existing.evaluator_version == request.evaluator_version.0
        && existing.source_evidence == request.source_evidence
        && existing.source_revision.as_deref()
            == request
                .source_revision
                .as_ref()
                .map(|revision| revision.0.as_str())
}

/// Add a case to a draft dataset. A repeated request returns the case it
/// added, even after the dataset is locked.
pub fn add_case(
    connection: &mut Connection,
    dataset_id: &str,
    request: &EvaluationCaseCreate,
    now: UtcSeconds,
) -> rusqlite::Result<Outcome<EvaluationCaseRead>> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let Some(dataset) = dataset_by_id(&transaction, dataset_id)? else {
        return Ok(Err(DATASET_NOT_FOUND));
    };
    if let Some(existing) = case_by_key(&transaction, dataset_id, &request.case_key.0)? {
        return Ok(if has_same_content(&existing, request) {
            Ok(existing)
        } else {
            Err(CASE_IDENTITY_CONFLICT)
        });
    }
    if dataset.status != DatasetStatus::Draft {
        return Ok(Err(DATASET_LOCKED));
    }
    let case_count: i64 = transaction
        .prepare_cached(COUNT_DATASET_CASES)?
        .query_row(params![dataset_id], |row| row.get(0))?;
    if case_count >= MAX_CASES_PER_DATASET {
        return Ok(Err(DATASET_CASE_LIMIT_REACHED));
    }

    // Cases are never removed, so the next ordinal is the count plus one.
    let ordinal = case_count + 1;
    let source = EvidenceColumns::of(request.source_evidence.as_ref());
    transaction.prepare_cached(INSERT_CASE)?.execute(params![
        generate_id(),
        dataset_id,
        request.case_key.0,
        request.evaluation_name.0,
        ordinal,
        request.origin.as_str(),
        request.target_kind.as_str(),
        request.target_key.0,
        request.target_name.0,
        request.input_version.0,
        request.input_json.0,
        request
            .expectation_json
            .as_ref()
            .map(|json| json.0.as_str()),
        request.evaluator_key.0,
        request.evaluator_version.0,
        source.kind,
        source.service_namespace,
        source.service_name,
        source.executable_type,
        source.runtime_id,
        source.trace_id,
        source.span_id,
        request
            .source_revision
            .as_ref()
            .map(|revision| revision.0.as_str()),
        now,
    ])?;
    let case = stored(case_by_key(&transaction, dataset_id, &request.case_key.0)?)?;
    transaction.commit()?;
    Ok(Ok(case))
}

/// Lock a dataset. Locking a locked dataset changes nothing.
pub fn lock_dataset(
    connection: &mut Connection,
    dataset_id: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Outcome<EvaluationDatasetRead>> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    transaction
        .prepare_cached(LOCK_DATASET)?
        .execute(params![dataset_id, now])?;
    let Some(dataset) = dataset_by_id(&transaction, dataset_id)? else {
        return Ok(Err(DATASET_NOT_FOUND));
    };
    transaction.commit()?;
    Ok(Ok(dataset))
}

/// One run with its dataset and every case's attempt, in case order.
fn run_detail(
    connection: &Connection,
    run_id: &str,
) -> rusqlite::Result<Option<EvaluationRunDetail>> {
    let found = connection
        .prepare_cached(SELECT_RUN)?
        .query_row(params![run_id], |row| {
            Ok((run_from_row(row, 0)?, dataset_from_row(row, RUN_COLUMNS)?))
        })
        .optional()?;
    let Some((run, dataset)) = found else {
        return Ok(None);
    };
    let cases = connection
        .prepare_cached(SELECT_RUN_CASES)?
        .query_map(params![run.id, run.dataset_id], |row| {
            Ok(EvaluationRunCase {
                case: case_from_row(row, 0)?,
                attempt: attempt_from_row(row, CASE_COLUMNS)?,
            })
        })?
        .collect::<rusqlite::Result<_>>()?;
    Ok(Some(EvaluationRunDetail {
        run,
        dataset,
        cases,
    }))
}

/// Start a run of a locked dataset: the run and one queued attempt per case.
/// A repeated request returns the run it started, as that run is now.
pub fn start_run(
    connection: &mut Connection,
    request: &EvaluationRunStart,
    user_id: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Outcome<EvaluationRunDetail>> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let dataset_id = request.dataset_id.0.as_str();
    let Some(dataset) = dataset_by_id(&transaction, dataset_id)? else {
        return Ok(Err(DATASET_NOT_FOUND));
    };
    let existing: Option<(String, String, String)> = transaction
        .prepare_cached(SELECT_RUN_BY_REQUEST_KEY)?
        .query_row(params![dataset_id, request.request_key.0], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?))
        })
        .optional()?;
    let run_id = match existing {
        Some((run_id, run_label, source_revision)) => {
            if run_label != request.run_label.0 || source_revision != request.source_revision.0 {
                return Ok(Err(RUN_IDENTITY_CONFLICT));
            }
            run_id
        }
        None => {
            if dataset.status != DatasetStatus::Locked {
                return Ok(Err(DATASET_NOT_LOCKED));
            }
            let case_ids: Vec<String> = transaction
                .prepare_cached(SELECT_DATASET_CASE_IDS)?
                .query_map(params![dataset_id], |row| row.get(0))?
                .collect::<rusqlite::Result<_>>()?;
            if case_ids.is_empty() {
                return Ok(Err(DATASET_EMPTY));
            }
            let run_id = generate_id();
            transaction.prepare_cached(INSERT_RUN)?.execute(params![
                run_id,
                dataset_id,
                request.request_key.0,
                request.run_label.0,
                request.source_revision.0,
                user_id,
                now,
            ])?;
            let mut insert_attempt = transaction.prepare_cached(INSERT_ATTEMPT)?;
            for case_id in &case_ids {
                insert_attempt.execute(params![generate_id(), run_id, case_id])?;
            }
            run_id
        }
    };
    let detail = stored(run_detail(&transaction, &run_id)?)?;
    transaction.commit()?;
    Ok(Ok(detail))
}

/// One run with its dataset and every case's attempt, in case order.
pub fn get_run(
    connection: &mut Connection,
    run_id: &str,
) -> rusqlite::Result<Option<EvaluationRunDetail>> {
    // One read transaction, so the run and its attempts are one snapshot.
    let transaction = connection.transaction()?;
    run_detail(&transaction, run_id)
}

/// The case filters of a run scope, as the first four parameters of the run
/// listing statements.
struct CaseFilters<'a> {
    target_kind: Option<&'static str>,
    target_key: Option<&'a str>,
    input_version: Option<i64>,
    evaluation_name: Option<&'a str>,
}

/// The outcomes of the attempts of one run whose cases match the filters.
fn outcome_summary(
    connection: &Connection,
    filters: &CaseFilters<'_>,
    run_id: &str,
) -> rusqlite::Result<EvaluationOutcomeSummary> {
    let (mut queued, mut passed, mut failed, mut error) = (0, 0, 0, 0);
    let mut statement = connection.prepare_cached(COUNT_RUN_OUTCOMES)?;
    let mut rows = statement.query(params![
        filters.target_kind,
        filters.target_key,
        filters.input_version,
        filters.evaluation_name,
        run_id,
    ])?;
    while let Some(row) = rows.next()? {
        let count: i64 = row.get(1)?;
        match row.get(0)? {
            AttemptStatus::Queued => queued = count,
            AttemptStatus::Passed => passed = count,
            AttemptStatus::Failed => failed = count,
            AttemptStatus::Error => error = count,
        }
    }
    let total = queued + passed + failed + error;
    let judged = passed + failed;
    Ok(EvaluationOutcomeSummary {
        total,
        queued,
        judged,
        passed,
        failed,
        error,
        pass_rate: (judged > 0).then(|| passed as f64 / judged as f64),
        coverage: (total > 0).then(|| judged as f64 / total as f64),
    })
}

/// The facets of every case of one dataset, in name order.
fn dataset_facets(
    connection: &Connection,
    dataset_id: &str,
) -> rusqlite::Result<(Vec<EvaluationTargetFacet>, Vec<EvaluationNameFacet>)> {
    let target_facets = connection
        .prepare_cached(SELECT_TARGET_FACETS)?
        .query_map(params![dataset_id], |row| {
            Ok(EvaluationTargetFacet {
                target_kind: row.get(0)?,
                target_key: row.get(1)?,
                target_name: row.get(2)?,
                input_version: row.get(3)?,
                case_count: row.get(4)?,
            })
        })?
        .collect::<rusqlite::Result<_>>()?;
    let evaluation_facets = connection
        .prepare_cached(SELECT_EVALUATION_FACETS)?
        .query_map(params![dataset_id], |row| {
            Ok(EvaluationNameFacet {
                evaluation_name: row.get(0)?,
                case_count: row.get(1)?,
            })
        })?
        .collect::<rusqlite::Result<_>>()?;
    Ok((target_facets, evaluation_facets))
}

/// Up to `limit` runs within a scope, newest first, starting after `after`.
pub fn list_runs(
    connection: &mut Connection,
    scope: &EvaluationRunScope,
    after: Option<&TimePosition>,
    limit: u32,
) -> rusqlite::Result<Vec<EvaluationRunSummary>> {
    // One read transaction, so the runs, their outcomes, and the facets are
    // one snapshot.
    let transaction = connection.transaction()?;
    let filters = CaseFilters {
        target_kind: scope.target_kind.map(TargetKind::as_str),
        target_key: scope.target_key.as_ref().map(|key| key.0.as_str()),
        input_version: scope.input_version.map(|version| version.0),
        evaluation_name: scope.evaluation_name.as_ref().map(|name| name.0.as_str()),
    };
    let dataset_id = scope.dataset_id.as_ref().map(|id| id.0.as_str());
    let run_and_dataset = |row: &Row<'_>| {
        Ok((
            run_from_row(row, 0)?,
            dataset_summary_from_row(row, RUN_COLUMNS)?,
        ))
    };
    let page: Vec<(EvaluationRunRead, EvaluationDatasetSummary)> = match (dataset_id, after) {
        (None, None) => transaction
            .prepare_cached(SELECT_NEWEST_RUNS)?
            .query_map(
                params![
                    filters.target_kind,
                    filters.target_key,
                    filters.input_version,
                    filters.evaluation_name,
                    limit,
                ],
                run_and_dataset,
            )?
            .collect::<rusqlite::Result<_>>()?,
        (None, Some(after)) => transaction
            .prepare_cached(SELECT_RUNS_AFTER)?
            .query_map(
                params![
                    filters.target_kind,
                    filters.target_key,
                    filters.input_version,
                    filters.evaluation_name,
                    after.created_at,
                    after.id,
                    limit,
                ],
                run_and_dataset,
            )?
            .collect::<rusqlite::Result<_>>()?,
        (Some(dataset_id), None) => transaction
            .prepare_cached(SELECT_NEWEST_DATASET_RUNS)?
            .query_map(
                params![
                    filters.target_kind,
                    filters.target_key,
                    filters.input_version,
                    filters.evaluation_name,
                    dataset_id,
                    limit,
                ],
                run_and_dataset,
            )?
            .collect::<rusqlite::Result<_>>()?,
        (Some(dataset_id), Some(after)) => transaction
            .prepare_cached(SELECT_DATASET_RUNS_AFTER)?
            .query_map(
                params![
                    filters.target_kind,
                    filters.target_key,
                    filters.input_version,
                    filters.evaluation_name,
                    dataset_id,
                    after.created_at,
                    after.id,
                    limit,
                ],
                run_and_dataset,
            )?
            .collect::<rusqlite::Result<_>>()?,
    };

    // Facets describe a whole dataset, so runs of one dataset share them.
    let mut facets_by_dataset = HashMap::new();
    let mut summaries = Vec::with_capacity(page.len());
    for (run, dataset) in page {
        let (target_facets, evaluation_facets) = match facets_by_dataset.entry(dataset.id.clone()) {
            Entry::Vacant(facets) => facets
                .insert(dataset_facets(&transaction, &dataset.id)?)
                .clone(),
            Entry::Occupied(facets) => facets.get().clone(),
        };
        let outcome_summary = outcome_summary(&transaction, &filters, &run.id)?;
        summaries.push(EvaluationRunSummary {
            run,
            dataset,
            outcome_summary,
            target_facets,
            evaluation_facets,
        });
    }
    Ok(summaries)
}

/// One attempt with its run, dataset, and case. `None` when no such attempt
/// exists.
pub fn attempt_detail(
    connection: &Connection,
    attempt_id: &str,
) -> rusqlite::Result<Option<EvaluationAttemptDetail>> {
    connection
        .prepare_cached(SELECT_ATTEMPT_DETAIL)?
        .query_row(params![attempt_id], |row| {
            let dataset_first = RUN_COLUMNS;
            let case_first = dataset_first + DATASET_COLUMNS;
            let attempt_first = case_first + CASE_COLUMNS;
            Ok(EvaluationAttemptDetail {
                run: run_from_row(row, 0)?,
                dataset: dataset_from_row(row, dataset_first)?,
                case: case_from_row(row, case_first)?,
                attempt: attempt_from_row(row, attempt_first)?,
            })
        })
        .optional()
}

/// Whether a write failed because it would repeat a value that must be
/// unique.
fn is_unique_violation(error: &rusqlite::Error) -> bool {
    error
        .sqlite_error()
        .is_some_and(|error| error.extended_code == rusqlite::ffi::SQLITE_CONSTRAINT_UNIQUE)
}

/// Bind a queued attempt to the execution it evaluated. A repeated request
/// changes nothing.
pub fn bind_attempt_evidence(
    connection: &mut Connection,
    attempt_id: &str,
    evidence: &ExecutionEvidenceReference,
    now: UtcSeconds,
) -> rusqlite::Result<Outcome<EvaluationAttemptRead>> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let Some(attempt) = attempt_by_id(&transaction, attempt_id)? else {
        return Ok(Err(ATTEMPT_NOT_FOUND));
    };
    if let Some(bound) = &attempt.subject_evidence {
        return Ok(if bound == evidence {
            Ok(attempt)
        } else {
            Err(ATTEMPT_EVIDENCE_CONFLICT)
        });
    }
    if attempt.status != AttemptStatus::Queued {
        return Ok(Err(ATTEMPT_TERMINAL));
    }

    let subject = EvidenceColumns::of(Some(evidence));
    let updated = transaction
        .prepare_cached(BIND_ATTEMPT_EVIDENCE)?
        .execute(params![
            attempt_id,
            subject.kind,
            subject.service_namespace,
            subject.service_name,
            subject.executable_type,
            subject.runtime_id,
            subject.trace_id,
            subject.span_id,
            now,
        ]);
    match updated {
        Ok(_) => {}
        // One execution is the subject of at most one attempt.
        Err(error) if is_unique_violation(&error) => return Ok(Err(EVIDENCE_ALREADY_BOUND)),
        Err(error) => return Err(error),
    }
    let attempt = stored(attempt_by_id(&transaction, attempt_id)?)?;
    transaction.commit()?;
    Ok(Ok(attempt))
}

/// Record a queued attempt's result, and complete its run when no attempt of
/// that run is still queued. A repeated request changes nothing.
pub fn record_attempt_result(
    connection: &mut Connection,
    attempt_id: &str,
    result: &EvaluationAttemptResult,
    now: UtcSeconds,
) -> rusqlite::Result<Outcome<EvaluationAttemptRead>> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let Some(attempt) = attempt_by_id(&transaction, attempt_id)? else {
        return Ok(Err(ATTEMPT_NOT_FOUND));
    };
    let status = AttemptStatus::from(result.status);
    let duration_ms = result.duration_ms.map(|duration| duration.0);
    if attempt.status != AttemptStatus::Queued {
        let same_result = attempt.status == status
            && attempt.reason.as_deref() == Some(result.reason.0.as_str())
            && attempt.duration_ms == duration_ms;
        return Ok(if same_result {
            Ok(attempt)
        } else {
            Err(ATTEMPT_RESULT_CONFLICT)
        });
    }
    let is_judgment = matches!(status, AttemptStatus::Passed | AttemptStatus::Failed);
    if is_judgment && attempt.subject_evidence.is_none() {
        return Ok(Err(ATTEMPT_EVIDENCE_REQUIRED));
    }

    transaction
        .prepare_cached(RECORD_ATTEMPT_RESULT)?
        .execute(params![
            attempt_id,
            status.as_str(),
            result.reason.0,
            duration_ms,
            now,
        ])?;
    transaction
        .prepare_cached(COMPLETE_RUN)?
        .execute(params![attempt.run_id, now])?;
    let attempt = stored(attempt_by_id(&transaction, attempt_id)?)?;
    transaction.commit()?;
    Ok(Ok(attempt))
}

/// Up to `limit` records that use an execution's evidence, starting after
/// `after`: the attempt it is the subject of, then the cases generated from
/// it.
pub fn find_evidence_membership(
    connection: &Connection,
    evidence: &ExecutionEvidenceReference,
    after: Option<&MembershipPosition>,
    limit: u32,
) -> rusqlite::Result<Vec<EvaluationEvidenceMembership>> {
    let after_role = after.map(|after| after.role.as_str());
    let after_record_id = after.map(|after| after.record_id.as_str());
    match evidence {
        ExecutionEvidenceReference::JunjoExecution(reference) => connection
            .prepare_cached(SELECT_JUNJO_EXECUTION_MEMBERSHIP)?
            .query_map(
                params![
                    reference.service_namespace.0,
                    reference.service_name.0,
                    reference.executable_type.as_str(),
                    reference.runtime_id.0,
                    after_role,
                    after_record_id,
                    limit,
                ],
                membership_from_row,
            )?
            .collect(),
        ExecutionEvidenceReference::OtelSpan(reference) => connection
            .prepare_cached(SELECT_OTEL_SPAN_MEMBERSHIP)?
            .query_map(
                params![
                    reference.service_namespace.0,
                    reference.service_name.0,
                    reference.trace_id.0,
                    reference.span_id.0,
                    after_role,
                    after_record_id,
                    limit,
                ],
                membership_from_row,
            )?
            .collect(),
    }
}

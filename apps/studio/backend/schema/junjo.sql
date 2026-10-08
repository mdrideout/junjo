-- Junjo AI Studio application database.
--
-- This file is the only source of the application schema. The backend creates
-- a missing database from it and stamps JUNJO_SCHEMA_VERSION. A database with
-- any other version is refused at startup: Studio has no upgrade path yet.
--
-- Canonical user-created product state lives here. Rebuildable telemetry
-- metadata lives in metadata.db and never here.
--
-- Timestamps are UTC text in the form YYYY-MM-DDTHH:MM:SSZ.

CREATE TABLE users (
    id TEXT NOT NULL PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE UNIQUE INDEX ix_users_email ON users (email);

-- Application Telemetry API keys. The canonical key value is `jtel_` plus a
-- 64-character generated secret. Ingestion validates keys through the
-- internal gRPC service.
--
-- Deleting a key deactivates it. The row stays, without the key value, so
-- the key's identifier and name remain on record. A deactivated key no
-- longer validates and is not listed.
CREATE TABLE api_keys (
    id TEXT NOT NULL PRIMARY KEY,
    key TEXT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK ((key IS NULL) = (deleted_at IS NOT NULL))
) STRICT;

CREATE UNIQUE INDEX ix_api_keys_key ON api_keys (key);

-- Developer access tokens: the scoped bearer credential for the CLI, the SDK,
-- and automation. The API calls them evaluation tokens. The token value is
-- `jcli_` plus a 64-character generated secret and is recoverable by design
-- (Studio ADR-010). A token whose creator is deleted stops authenticating.
CREATE TABLE evaluation_tokens (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(CAST(name AS BLOB)) BETWEEN 1 AND 256),
    token TEXT NOT NULL,
    evaluation_read INTEGER NOT NULL CHECK (evaluation_read IN (0, 1)),
    evaluation_write INTEGER NOT NULL CHECK (evaluation_write IN (0, 1)),
    evidence_read INTEGER NOT NULL CHECK (evidence_read IN (0, 1)),
    expires_at TEXT,
    created_by_user_id TEXT REFERENCES users (id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    CHECK (evaluation_read = 1 OR evaluation_write = 1 OR evidence_read = 1)
) STRICT;

CREATE UNIQUE INDEX ix_evaluation_tokens_token ON evaluation_tokens (token);

-- CLI sign-ins: the `junjo` CLI signing in through the browser, as the OAuth
-- device authorization grant does (Studio ADR-012). The CLI holds the device
-- code, `jdev_` plus a 64-character generated secret, and collects its token
-- with it. A signed-in person confirms the user code, stored without its
-- hyphen, and approves or denies the sign-in. The name and the scopes are
-- what the CLI asked for.
--
-- Approval mints a developer access token and names it here until the CLI
-- collects it, which deletes the row. Deleting that token deletes the row
-- too. A row past `expires_at` is treated as absent, and starting a sign-in
-- deletes every such row.
CREATE TABLE cli_sign_ins (
    device_code TEXT NOT NULL PRIMARY KEY,
    user_code TEXT NOT NULL
        CHECK (
            length(user_code) = 8
            AND user_code NOT GLOB '*[^BCDFGHJKLMNPQRSTVWXZ]*'
        ),
    client_name TEXT NOT NULL
        CHECK (length(CAST(client_name AS BLOB)) BETWEEN 1 AND 256),
    evaluation_read INTEGER NOT NULL CHECK (evaluation_read IN (0, 1)),
    evaluation_write INTEGER NOT NULL CHECK (evaluation_write IN (0, 1)),
    evidence_read INTEGER NOT NULL CHECK (evidence_read IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied')),
    token_id TEXT REFERENCES evaluation_tokens (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    CHECK (evaluation_read = 1 OR evaluation_write = 1 OR evidence_read = 1),
    CHECK (
        (status = 'approved' AND token_id IS NOT NULL)
        OR (status IN ('pending', 'denied') AND token_id IS NULL)
    )
) STRICT;

CREATE UNIQUE INDEX ix_cli_sign_ins_user_code ON cli_sign_ins (user_code);
CREATE INDEX ix_cli_sign_ins_expires_at ON cli_sign_ins (expires_at);

-- Browser sessions, owned by the tower-sessions store adapter. `data` is the
-- session record as JSON and `expiry_date` is Unix seconds.
CREATE TABLE sessions (
    id TEXT NOT NULL PRIMARY KEY,
    data TEXT NOT NULL,
    expiry_date INTEGER NOT NULL
) STRICT;

CREATE INDEX ix_sessions_expiry_date ON sessions (expiry_date);

-- Evaluation datasets: one application's named input corpus, unique by
-- application key and key. A draft dataset accepts cases. Locking is
-- irreversible, and a run starts only from a locked dataset (Studio ADR-010).
CREATE TABLE eval_datasets (
    id TEXT NOT NULL PRIMARY KEY,
    application_key TEXT NOT NULL
        CHECK (length(CAST(application_key AS BLOB)) BETWEEN 1 AND 128),
    key TEXT NOT NULL CHECK (length(CAST(key AS BLOB)) BETWEEN 1 AND 128),
    name TEXT NOT NULL CHECK (length(CAST(name AS BLOB)) BETWEEN 1 AND 256),
    description TEXT
        CHECK (description IS NULL OR length(CAST(description AS BLOB)) <= 2048),
    status TEXT NOT NULL CHECK (status IN ('draft', 'locked')),
    created_by_user_id TEXT REFERENCES users (id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    locked_at TEXT,
    UNIQUE (application_key, key),
    CHECK (
        (status = 'draft' AND locked_at IS NULL)
        OR (status = 'locked' AND locked_at IS NOT NULL)
    )
) STRICT;

CREATE INDEX ix_eval_datasets_application_created_id
    ON eval_datasets (application_key, created_at, id);

-- Evaluation cases: the ordered inputs of one dataset, unique by case key.
-- Each case names the application target it runs and the evaluator that
-- judges it. `input_json` and `expectation_json` are canonical JSON text:
-- object names sorted and no insignificant whitespace.
--
-- A generated case records the source revision and the execution evidence it
-- was generated from. An authored case records neither. An evidence reference
-- is stored as scalar columns, wholly present or wholly absent, so membership
-- lookups use an index.
CREATE TABLE eval_cases (
    id TEXT NOT NULL PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES eval_datasets (id),
    case_key TEXT NOT NULL
        CHECK (length(CAST(case_key AS BLOB)) BETWEEN 1 AND 128),
    evaluation_name TEXT NOT NULL
        CHECK (length(CAST(evaluation_name AS BLOB)) BETWEEN 1 AND 256),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    origin TEXT NOT NULL CHECK (origin IN ('authored', 'generated')),
    target_kind TEXT NOT NULL
        CHECK (target_kind IN ('node', 'workflow', 'agent')),
    target_key TEXT NOT NULL
        CHECK (length(CAST(target_key AS BLOB)) BETWEEN 1 AND 128),
    target_name TEXT NOT NULL
        CHECK (length(CAST(target_name AS BLOB)) BETWEEN 1 AND 256),
    input_version INTEGER NOT NULL
        CHECK (input_version BETWEEN 1 AND 2147483647),
    input_json TEXT NOT NULL
        CHECK (
            json_valid(input_json)
            AND length(CAST(input_json AS BLOB)) <= 16384
        ),
    expectation_json TEXT
        CHECK (
            expectation_json IS NULL
            OR (
                json_valid(expectation_json)
                AND length(CAST(expectation_json AS BLOB)) <= 16384
            )
        ),
    evaluator_key TEXT NOT NULL
        CHECK (length(CAST(evaluator_key AS BLOB)) BETWEEN 1 AND 128),
    evaluator_version INTEGER NOT NULL
        CHECK (evaluator_version BETWEEN 1 AND 2147483647),
    source_evidence_kind TEXT
        CHECK (
            source_evidence_kind IS NULL
            OR source_evidence_kind IN ('junjo_execution', 'otel_span')
        ),
    source_service_namespace TEXT
        CHECK (
            source_service_namespace IS NULL
            OR length(CAST(source_service_namespace AS BLOB)) <= 256
        ),
    source_service_name TEXT
        CHECK (
            source_service_name IS NULL
            OR length(CAST(source_service_name AS BLOB)) BETWEEN 1 AND 256
        ),
    source_executable_type TEXT
        CHECK (
            source_executable_type IS NULL
            OR source_executable_type IN ('workflow', 'subflow', 'agent')
        ),
    source_runtime_id TEXT
        CHECK (
            source_runtime_id IS NULL
            OR length(CAST(source_runtime_id AS BLOB)) BETWEEN 1 AND 256
        ),
    source_trace_id TEXT
        CHECK (
            source_trace_id IS NULL
            OR (
                length(source_trace_id) = 32
                AND source_trace_id NOT GLOB '*[^0-9a-f]*'
            )
        ),
    source_span_id TEXT
        CHECK (
            source_span_id IS NULL
            OR (
                length(source_span_id) = 16
                AND source_span_id NOT GLOB '*[^0-9a-f]*'
            )
        ),
    source_revision TEXT
        CHECK (source_revision IS NULL OR length(source_revision) IN (40, 64)),
    created_at TEXT NOT NULL,
    UNIQUE (dataset_id, case_key),
    UNIQUE (dataset_id, ordinal),
    CHECK (
        (
            origin = 'authored'
            AND source_evidence_kind IS NULL
            AND source_service_namespace IS NULL
            AND source_service_name IS NULL
            AND source_executable_type IS NULL
            AND source_runtime_id IS NULL
            AND source_trace_id IS NULL
            AND source_span_id IS NULL
            AND source_revision IS NULL
        )
        OR (
            origin = 'generated'
            AND source_revision IS NOT NULL
            AND (
                (
                    source_evidence_kind = 'junjo_execution'
                    AND source_service_namespace IS NOT NULL
                    AND source_service_name IS NOT NULL
                    AND source_executable_type IS NOT NULL
                    AND source_runtime_id IS NOT NULL
                    AND source_trace_id IS NULL
                    AND source_span_id IS NULL
                )
                OR (
                    source_evidence_kind = 'otel_span'
                    AND source_service_namespace IS NOT NULL
                    AND source_service_name IS NOT NULL
                    AND source_executable_type IS NULL
                    AND source_runtime_id IS NULL
                    AND source_trace_id IS NOT NULL
                    AND source_span_id IS NOT NULL
                )
            )
        )
    )
) STRICT;

CREATE INDEX ix_eval_cases_dataset_ordinal_id
    ON eval_cases (dataset_id, ordinal, id);
CREATE INDEX ix_eval_cases_source_junjo_execution
    ON eval_cases (
        source_service_namespace, source_service_name, source_executable_type,
        source_runtime_id
    )
    WHERE source_evidence_kind = 'junjo_execution';
CREATE INDEX ix_eval_cases_source_otel_span
    ON eval_cases (
        source_service_namespace, source_service_name, source_trace_id,
        source_span_id
    )
    WHERE source_evidence_kind = 'otel_span';

-- Evaluation runs: one labeled source revision evaluated against one locked
-- dataset, unique by dataset and request key. A run is active until its last
-- attempt records a result.
CREATE TABLE eval_runs (
    id TEXT NOT NULL PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES eval_datasets (id),
    request_key TEXT NOT NULL
        CHECK (length(CAST(request_key AS BLOB)) BETWEEN 1 AND 128),
    run_label TEXT NOT NULL
        CHECK (length(CAST(run_label AS BLOB)) BETWEEN 1 AND 256),
    source_revision TEXT NOT NULL CHECK (length(source_revision) IN (40, 64)),
    status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
    created_by_user_id TEXT REFERENCES users (id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (dataset_id, request_key),
    CHECK (
        (status = 'active' AND completed_at IS NULL)
        OR (status = 'completed' AND completed_at IS NOT NULL)
    )
) STRICT;

CREATE INDEX ix_eval_runs_created_id ON eval_runs (created_at, id);
CREATE INDEX ix_eval_runs_dataset_created_id
    ON eval_runs (dataset_id, created_at, id);

-- Evaluation attempts: one case's membership and outcome in one run. An
-- attempt is queued until it records a result: passed, failed, or error.
--
-- The subject evidence is the execution the run produced for the case. It is
-- stored like a case's source evidence, and one execution is the subject of
-- at most one attempt. A passed or failed attempt has subject evidence. An
-- error may have none, because setup can fail before an execution exists.
CREATE TABLE eval_case_attempts (
    id TEXT NOT NULL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES eval_runs (id),
    case_id TEXT NOT NULL REFERENCES eval_cases (id),
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'passed', 'failed', 'error')),
    reason TEXT
        CHECK (
            reason IS NULL
            OR length(CAST(reason AS BLOB)) BETWEEN 1 AND 4096
        ),
    duration_ms INTEGER
        CHECK (duration_ms IS NULL OR duration_ms BETWEEN 0 AND 86400000),
    subject_evidence_kind TEXT
        CHECK (
            subject_evidence_kind IS NULL
            OR subject_evidence_kind IN ('junjo_execution', 'otel_span')
        ),
    subject_service_namespace TEXT
        CHECK (
            subject_service_namespace IS NULL
            OR length(CAST(subject_service_namespace AS BLOB)) <= 256
        ),
    subject_service_name TEXT
        CHECK (
            subject_service_name IS NULL
            OR length(CAST(subject_service_name AS BLOB)) BETWEEN 1 AND 256
        ),
    subject_executable_type TEXT
        CHECK (
            subject_executable_type IS NULL
            OR subject_executable_type IN ('workflow', 'subflow', 'agent')
        ),
    subject_runtime_id TEXT
        CHECK (
            subject_runtime_id IS NULL
            OR length(CAST(subject_runtime_id AS BLOB)) BETWEEN 1 AND 256
        ),
    subject_trace_id TEXT
        CHECK (
            subject_trace_id IS NULL
            OR (
                length(subject_trace_id) = 32
                AND subject_trace_id NOT GLOB '*[^0-9a-f]*'
            )
        ),
    subject_span_id TEXT
        CHECK (
            subject_span_id IS NULL
            OR (
                length(subject_span_id) = 16
                AND subject_span_id NOT GLOB '*[^0-9a-f]*'
            )
        ),
    evidence_bound_at TEXT,
    recorded_at TEXT,
    UNIQUE (run_id, case_id),
    CHECK (
        (
            subject_evidence_kind IS NULL
            AND subject_service_namespace IS NULL
            AND subject_service_name IS NULL
            AND subject_executable_type IS NULL
            AND subject_runtime_id IS NULL
            AND subject_trace_id IS NULL
            AND subject_span_id IS NULL
            AND evidence_bound_at IS NULL
        )
        OR (
            subject_evidence_kind = 'junjo_execution'
            AND subject_service_namespace IS NOT NULL
            AND subject_service_name IS NOT NULL
            AND subject_executable_type IS NOT NULL
            AND subject_runtime_id IS NOT NULL
            AND subject_trace_id IS NULL
            AND subject_span_id IS NULL
            AND evidence_bound_at IS NOT NULL
        )
        OR (
            subject_evidence_kind = 'otel_span'
            AND subject_service_namespace IS NOT NULL
            AND subject_service_name IS NOT NULL
            AND subject_executable_type IS NULL
            AND subject_runtime_id IS NULL
            AND subject_trace_id IS NOT NULL
            AND subject_span_id IS NOT NULL
            AND evidence_bound_at IS NOT NULL
        )
    ),
    CHECK (
        (
            status = 'queued'
            AND reason IS NULL
            AND duration_ms IS NULL
            AND recorded_at IS NULL
        )
        OR (
            status IN ('passed', 'failed')
            AND reason IS NOT NULL
            AND subject_evidence_kind IS NOT NULL
            AND recorded_at IS NOT NULL
        )
        OR (
            status = 'error'
            AND reason IS NOT NULL
            AND recorded_at IS NOT NULL
        )
    )
) STRICT;

CREATE INDEX ix_eval_case_attempts_run_status
    ON eval_case_attempts (run_id, status);
CREATE INDEX ix_eval_case_attempts_case_run
    ON eval_case_attempts (case_id, run_id);
CREATE UNIQUE INDEX uq_eval_case_attempts_subject_junjo_execution
    ON eval_case_attempts (
        subject_service_namespace, subject_service_name,
        subject_executable_type, subject_runtime_id
    )
    WHERE subject_evidence_kind = 'junjo_execution';
CREATE UNIQUE INDEX uq_eval_case_attempts_subject_otel_span
    ON eval_case_attempts (
        subject_service_namespace, subject_service_name, subject_trace_id,
        subject_span_id
    )
    WHERE subject_evidence_kind = 'otel_span';

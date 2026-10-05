//! Metadata index statements.
//!
//! Writes run on the indexer thread's connection. Reads run on the reader
//! connection from the request path. Every statement is a named constant so a
//! test can prepare each one against the real schema.

use std::collections::{HashMap, HashSet};

use rusqlite::{Connection, TransactionBehavior, params};

/// Per-service facts about one cold Parquet file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceSummary {
    pub span_count: i64,
    pub min_time_ns: i64,
    pub max_time_ns: i64,
}

/// Everything the index records about one cold Parquet file. Full span
/// payloads stay in Parquet.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileSummary {
    pub file_path: String,
    pub size_bytes: i64,
    pub row_count: i64,
    pub min_time_ns: i64,
    pub max_time_ns: i64,
    pub trace_ids: HashSet<String>,
    pub services: HashMap<String, ServiceSummary>,
    /// Service name to the traces in which that service emitted an LLM span.
    pub llm_trace_ids: HashMap<String, HashSet<String>>,
    pub workflow_services: HashSet<String>,
    pub agent_services: HashSet<String>,
}

pub const INSERT_PARQUET_FILE: &str = "
    INSERT INTO parquet_files (file_path, min_time_ns, max_time_ns, row_count, size_bytes)
    VALUES (?1, ?2, ?3, ?4, ?5)";
pub const INSERT_TRACE_FILE: &str =
    "INSERT OR IGNORE INTO trace_files (trace_id, file_id) VALUES (?1, ?2)";
pub const INSERT_FILE_SERVICE: &str = "
    INSERT OR REPLACE INTO file_services
        (file_id, service_name, span_count, min_time_ns, max_time_ns)
    VALUES (?1, ?2, ?3, ?4, ?5)";
pub const INSERT_LLM_TRACE: &str =
    "INSERT OR IGNORE INTO llm_traces (service_name, trace_id) VALUES (?1, ?2)";
pub const INSERT_WORKFLOW_FILE: &str =
    "INSERT OR IGNORE INTO workflow_files (service_name, file_id) VALUES (?1, ?2)";
pub const INSERT_AGENT_FILE: &str =
    "INSERT OR IGNORE INTO agent_files (service_name, file_id) VALUES (?1, ?2)";
pub const UPSERT_FAILED_FILE: &str = "
    INSERT INTO failed_parquet_files (file_path, error_type, error_message, file_size)
    VALUES (?1, ?2, ?3, ?4)
    ON CONFLICT (file_path) DO UPDATE SET
        error_type = excluded.error_type,
        error_message = excluded.error_message,
        file_size = excluded.file_size,
        failed_at = datetime('now'),
        retry_count = retry_count + 1";
pub const SELECT_INDEXED_FILE_PATHS: &str = "SELECT file_path FROM parquet_files";
/// A failure of these two kinds can pass: the file could not be opened or
/// read, or the index could not be written. Every other kind means the
/// file's contents are damaged, and a cold file never changes.
pub const SELECT_DAMAGED_FILE_PATHS: &str =
    "SELECT file_path FROM failed_parquet_files WHERE error_type NOT IN ('Io', 'Sqlite')";
pub const SELECT_RETRIED_FILE_PATHS: &str =
    "SELECT file_path FROM failed_parquet_files WHERE error_type IN ('Io', 'Sqlite')";
pub const DELETE_FAILED_FILE: &str = "DELETE FROM failed_parquet_files WHERE file_path = ?1";
pub const DELETE_PARQUET_FILE: &str = "DELETE FROM parquet_files WHERE file_path = ?1";
pub const SELECT_SERVICES: &str =
    "SELECT DISTINCT service_name FROM file_services ORDER BY service_name";
pub const SELECT_FILE_PATHS_FOR_TRACE: &str = "
    SELECT pf.file_path
    FROM trace_files tf
    JOIN parquet_files pf ON tf.file_id = pf.file_id
    WHERE tf.trace_id = ?1";
pub const SELECT_FILE_PATHS_FOR_SERVICE: &str = "
    SELECT pf.file_path
    FROM file_services fs
    JOIN parquet_files pf ON fs.file_id = pf.file_id
    WHERE fs.service_name = ?1
    ORDER BY pf.max_time_ns DESC";
pub const SELECT_NEWEST_FILE_PATHS_FOR_SERVICE: &str = "
    SELECT pf.file_path
    FROM file_services fs
    JOIN parquet_files pf ON fs.file_id = pf.file_id
    WHERE fs.service_name = ?1
    ORDER BY pf.max_time_ns DESC
    LIMIT ?2";
pub const SELECT_NEWEST_WORKFLOW_FILE_PATHS: &str = "
    SELECT pf.file_path
    FROM workflow_files wf
    JOIN parquet_files pf ON wf.file_id = pf.file_id
    WHERE wf.service_name = ?1
    ORDER BY pf.max_time_ns DESC
    LIMIT ?2";
/// A service's time bounds in a file are its earliest span start and its
/// latest span end. A span starts no later than it ends, so the latest end is
/// also the latest a span of the service can start in that file.
pub const SELECT_AGENT_FILES_BETWEEN: &str = "
    SELECT pf.file_path, fs.max_time_ns
    FROM agent_files af
    JOIN file_services fs ON fs.file_id = af.file_id AND fs.service_name = af.service_name
    JOIN parquet_files pf ON pf.file_id = af.file_id
    WHERE af.service_name = ?1
      AND fs.max_time_ns >= ?2
      AND fs.min_time_ns <= ?3
    ORDER BY fs.max_time_ns DESC";
pub const SELECT_LLM_TRACE: &str =
    "SELECT 1 FROM llm_traces WHERE service_name = ?1 AND trace_id = ?2";
pub const SELECT_INDEXED_FILE: &str = "SELECT 1 FROM parquet_files WHERE file_path = ?1";

/// Every statement in this module, for the schema preparation test.
#[cfg(test)]
pub const ALL_STATEMENTS: [&str; 20] = [
    INSERT_PARQUET_FILE,
    INSERT_TRACE_FILE,
    INSERT_FILE_SERVICE,
    INSERT_LLM_TRACE,
    INSERT_WORKFLOW_FILE,
    INSERT_AGENT_FILE,
    UPSERT_FAILED_FILE,
    SELECT_INDEXED_FILE_PATHS,
    SELECT_DAMAGED_FILE_PATHS,
    SELECT_RETRIED_FILE_PATHS,
    DELETE_FAILED_FILE,
    DELETE_PARQUET_FILE,
    SELECT_SERVICES,
    SELECT_FILE_PATHS_FOR_TRACE,
    SELECT_FILE_PATHS_FOR_SERVICE,
    SELECT_NEWEST_FILE_PATHS_FOR_SERVICE,
    SELECT_NEWEST_WORKFLOW_FILE_PATHS,
    SELECT_AGENT_FILES_BETWEEN,
    SELECT_LLM_TRACE,
    SELECT_INDEXED_FILE,
];

/// Record one file's summaries in a single atomic transaction.
pub fn index_file(connection: &mut Connection, summary: &FileSummary) -> rusqlite::Result<i64> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    transaction
        .prepare_cached(INSERT_PARQUET_FILE)?
        .execute(params![
            summary.file_path,
            summary.min_time_ns,
            summary.max_time_ns,
            summary.row_count,
            summary.size_bytes,
        ])?;
    let file_id = transaction.last_insert_rowid();

    {
        let mut insert_trace = transaction.prepare_cached(INSERT_TRACE_FILE)?;
        for trace_id in &summary.trace_ids {
            insert_trace.execute(params![trace_id, file_id])?;
        }

        let mut insert_service = transaction.prepare_cached(INSERT_FILE_SERVICE)?;
        for (service_name, service) in &summary.services {
            insert_service.execute(params![
                file_id,
                service_name,
                service.span_count,
                service.min_time_ns,
                service.max_time_ns,
            ])?;
        }

        let mut insert_llm_trace = transaction.prepare_cached(INSERT_LLM_TRACE)?;
        for (service_name, trace_ids) in &summary.llm_trace_ids {
            for trace_id in trace_ids {
                insert_llm_trace.execute(params![service_name, trace_id])?;
            }
        }

        let mut insert_workflow_file = transaction.prepare_cached(INSERT_WORKFLOW_FILE)?;
        for service_name in &summary.workflow_services {
            insert_workflow_file.execute(params![service_name, file_id])?;
        }

        let mut insert_agent_file = transaction.prepare_cached(INSERT_AGENT_FILE)?;
        for service_name in &summary.agent_services {
            insert_agent_file.execute(params![service_name, file_id])?;
        }
    }

    // An earlier attempt at this file may have failed.
    transaction
        .prepare_cached(DELETE_FAILED_FILE)?
        .execute(params![summary.file_path])?;

    transaction.commit()?;
    Ok(file_id)
}

/// Record a file that could not be indexed, with the kind of failure.
pub fn record_failed_file(
    connection: &Connection,
    file_path: &str,
    error_type: &str,
    error_message: &str,
    file_size: i64,
) -> rusqlite::Result<()> {
    connection
        .prepare_cached(UPSERT_FAILED_FILE)?
        .execute(params![file_path, error_type, error_message, file_size])?;
    Ok(())
}

fn path_set(connection: &Connection, sql: &str) -> rusqlite::Result<HashSet<String>> {
    connection
        .prepare_cached(sql)?
        .query_map([], |row| row.get(0))?
        .collect()
}

pub fn indexed_file_paths(connection: &Connection) -> rusqlite::Result<HashSet<String>> {
    path_set(connection, SELECT_INDEXED_FILE_PATHS)
}

/// The failed files whose contents are damaged. They are not tried again.
pub fn damaged_file_paths(connection: &Connection) -> rusqlite::Result<HashSet<String>> {
    path_set(connection, SELECT_DAMAGED_FILE_PATHS)
}

/// The failed files whose failure can pass. They are tried again.
pub fn retried_file_paths(connection: &Connection) -> rusqlite::Result<HashSet<String>> {
    path_set(connection, SELECT_RETRIED_FILE_PATHS)
}

/// Remove index entries for files that no longer exist. Dependent rows are
/// removed by the cascade.
pub fn remove_files(connection: &mut Connection, file_paths: &[String]) -> rusqlite::Result<usize> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let mut removed = 0;
    {
        let mut delete = transaction.prepare_cached(DELETE_PARQUET_FILE)?;
        for file_path in file_paths {
            removed += delete.execute(params![file_path])?;
        }
    }
    transaction.commit()?;
    Ok(removed)
}

/// Distinct cold-tier service names, alphabetically.
pub fn services(connection: &Connection) -> rusqlite::Result<Vec<String>> {
    connection
        .prepare_cached(SELECT_SERVICES)?
        .query_map([], |row| row.get(0))?
        .collect()
}

/// Indexed cold files that contain spans for one trace.
pub fn file_paths_for_trace(
    connection: &Connection,
    trace_id: &str,
) -> rusqlite::Result<Vec<String>> {
    connection
        .prepare_cached(SELECT_FILE_PATHS_FOR_TRACE)?
        .query_map(params![trace_id], |row| row.get(0))?
        .collect()
}

/// Indexed cold files that contain spans for one service, newest first.
///
/// With a limit, only that many of the newest files are returned. Listings
/// pass one so a query never registers a service's whole cold history
/// (ingestion ADR-002).
pub fn file_paths_for_service(
    connection: &Connection,
    service_name: &str,
    limit: Option<usize>,
) -> rusqlite::Result<Vec<String>> {
    match limit {
        Some(limit) => connection
            .prepare_cached(SELECT_NEWEST_FILE_PATHS_FOR_SERVICE)?
            .query_map(params![service_name, limit as i64], |row| row.get(0))?
            .collect(),
        None => connection
            .prepare_cached(SELECT_FILE_PATHS_FOR_SERVICE)?
            .query_map(params![service_name], |row| row.get(0))?
            .collect(),
    }
}

/// The newest indexed cold files that contain Workflow spans for one service.
pub fn workflow_file_paths(
    connection: &Connection,
    service_name: &str,
    limit: usize,
) -> rusqlite::Result<Vec<String>> {
    connection
        .prepare_cached(SELECT_NEWEST_WORKFLOW_FILE_PATHS)?
        .query_map(params![service_name, limit as i64], |row| row.get(0))?
        .collect()
}

/// The indexed cold files one page of an Agent listing reads.
#[derive(Debug, PartialEq, Eq)]
pub struct AgentPageFiles {
    pub file_paths: Vec<String>,
    /// The latest time an Agent span can start in the files that were left
    /// out. `None` when no file was left out.
    pub rest_starts_by_ns: Option<i64>,
}

/// The indexed cold files that can hold the newest Agent spans of one service
/// that start at or before `starts_by_ns`.
///
/// Those are the files that reach across that time, and the `files_below`
/// newest files that end before it. The time bounds a caller filters by leave
/// out the files that hold no span inside them.
pub fn agent_page_files(
    connection: &Connection,
    service_name: &str,
    started_from_ns: Option<i64>,
    ended_by_ns: Option<i64>,
    starts_by_ns: Option<i64>,
    files_below: usize,
) -> rusqlite::Result<AgentPageFiles> {
    let starts_by_ns = starts_by_ns.unwrap_or(i64::MAX);
    let mut statement = connection.prepare_cached(SELECT_AGENT_FILES_BETWEEN)?;
    let mut rows = statement.query(params![
        service_name,
        started_from_ns.unwrap_or(i64::MIN),
        // A span that ended by a time started by it.
        starts_by_ns.min(ended_by_ns.unwrap_or(i64::MAX)),
    ])?;
    let mut files = AgentPageFiles {
        file_paths: Vec::new(),
        rest_starts_by_ns: None,
    };
    let mut below = 0;
    while let Some(row) = rows.next()? {
        let latest_end_ns: i64 = row.get(1)?;
        if latest_end_ns < starts_by_ns {
            if below == files_below {
                files.rest_starts_by_ns = Some(latest_end_ns);
                break;
            }
            below += 1;
        }
        files.file_paths.push(row.get(0)?);
    }
    Ok(files)
}

/// The candidate traces that the index knows contain an LLM span of one
/// service.
///
/// Each candidate is one primary-key lookup, so the work follows the number
/// of candidates and never the size of the index.
pub fn filter_llm_trace_ids(
    connection: &Connection,
    service_name: &str,
    trace_ids: &HashSet<String>,
) -> rusqlite::Result<HashSet<String>> {
    let mut is_llm_trace = connection.prepare_cached(SELECT_LLM_TRACE)?;
    let mut matched = HashSet::new();
    for trace_id in trace_ids {
        if is_llm_trace.exists(params![service_name, trace_id])? {
            matched.insert(trace_id.clone());
        }
    }
    Ok(matched)
}

/// The given files that the index does not hold, in the given order.
///
/// Each file is one lookup on its unique path, so the work follows the number
/// of files asked about and never the size of the index.
pub fn unindexed_file_paths(
    connection: &Connection,
    file_paths: &[String],
) -> rusqlite::Result<Vec<String>> {
    let mut is_indexed = connection.prepare_cached(SELECT_INDEXED_FILE)?;
    let mut unindexed = Vec::new();
    for file_path in file_paths {
        if !is_indexed.exists(params![file_path])? {
            unindexed.push(file_path.clone());
        }
    }
    Ok(unindexed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::{METADATA_SCHEMA_SQL, METADATA_SCHEMA_VERSION, ensure_schema};

    fn index() -> Connection {
        let mut connection = Connection::open_in_memory().unwrap();
        connection.execute_batch("PRAGMA foreign_keys=ON;").unwrap();
        ensure_schema(
            &mut connection,
            METADATA_SCHEMA_SQL,
            METADATA_SCHEMA_VERSION,
        )
        .unwrap();
        connection
    }

    fn summary(file_path: &str) -> FileSummary {
        FileSummary {
            file_path: file_path.to_string(),
            size_bytes: 2048,
            row_count: 3,
            min_time_ns: 100,
            max_time_ns: 900,
            trace_ids: HashSet::from(["trace-a".to_string(), "trace-b".to_string()]),
            services: HashMap::from([
                (
                    "checkout".to_string(),
                    ServiceSummary {
                        span_count: 2,
                        min_time_ns: 100,
                        max_time_ns: 500,
                    },
                ),
                (
                    "billing".to_string(),
                    ServiceSummary {
                        span_count: 1,
                        min_time_ns: 300,
                        max_time_ns: 900,
                    },
                ),
            ]),
            llm_trace_ids: HashMap::from([(
                "checkout".to_string(),
                HashSet::from(["trace-a".to_string()]),
            )]),
            workflow_services: HashSet::from(["checkout".to_string()]),
            agent_services: HashSet::from(["billing".to_string()]),
        }
    }

    fn count(connection: &Connection, table: &str) -> i64 {
        connection
            .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| {
                row.get(0)
            })
            .unwrap()
    }

    #[test]
    fn unindexed_files_are_the_ones_the_index_does_not_hold() {
        let mut connection = index();
        index_file(&mut connection, &summary("/data/indexed.parquet")).unwrap();
        // A file whose indexing failed is not in the index either.
        record_failed_file(
            &connection,
            "/data/failed.parquet",
            "ParquetError",
            "damaged",
            12,
        )
        .unwrap();
        let asked = [
            "/data/recent-2.parquet".to_string(),
            "/data/indexed.parquet".to_string(),
            "/data/failed.parquet".to_string(),
            "/data/recent-1.parquet".to_string(),
        ];

        let unindexed = unindexed_file_paths(&connection, &asked).unwrap();

        assert_eq!(
            unindexed,
            [
                "/data/recent-2.parquet",
                "/data/failed.parquet",
                "/data/recent-1.parquet"
            ]
        );
        assert!(unindexed_file_paths(&connection, &[]).unwrap().is_empty());
    }

    #[test]
    fn every_statement_prepares_against_the_schema() {
        let connection = index();
        for statement in ALL_STATEMENTS {
            connection
                .prepare(statement)
                .unwrap_or_else(|error| panic!("{statement}: {error}"));
        }
    }

    #[test]
    fn a_file_is_indexed_into_every_selection_table() {
        let mut connection = index();
        index_file(&mut connection, &summary("/data/a.parquet")).unwrap();

        assert_eq!(count(&connection, "parquet_files"), 1);
        assert_eq!(count(&connection, "trace_files"), 2);
        assert_eq!(count(&connection, "file_services"), 2);
        assert_eq!(count(&connection, "llm_traces"), 1);
        assert_eq!(count(&connection, "workflow_files"), 1);
        assert_eq!(count(&connection, "agent_files"), 1);
        assert_eq!(services(&connection).unwrap(), ["billing", "checkout"]);
        assert_eq!(
            file_paths_for_trace(&connection, "trace-a").unwrap(),
            ["/data/a.parquet"]
        );
        assert!(
            file_paths_for_trace(&connection, "missing")
                .unwrap()
                .is_empty()
        );
        assert_eq!(
            indexed_file_paths(&connection).unwrap(),
            HashSet::from(["/data/a.parquet".to_string()])
        );
    }

    /// The same summary under another path, with another newest span time.
    fn summary_ending_at(file_path: &str, max_time_ns: i64) -> FileSummary {
        FileSummary {
            max_time_ns,
            ..summary(file_path)
        }
    }

    /// Three files indexed out of time order.
    fn index_with_three_files() -> Connection {
        let mut connection = index();
        for (file_path, max_time_ns) in [
            ("/data/old.parquet", 100),
            ("/data/new.parquet", 300),
            ("/data/middle.parquet", 200),
        ] {
            index_file(&mut connection, &summary_ending_at(file_path, max_time_ns)).unwrap();
        }
        connection
    }

    #[test]
    fn service_files_are_listed_newest_first_and_can_be_limited() {
        let connection = index_with_three_files();

        assert_eq!(
            file_paths_for_service(&connection, "checkout", None).unwrap(),
            [
                "/data/new.parquet",
                "/data/middle.parquet",
                "/data/old.parquet"
            ]
        );
        assert_eq!(
            file_paths_for_service(&connection, "checkout", Some(2)).unwrap(),
            ["/data/new.parquet", "/data/middle.parquet"]
        );
        assert!(
            file_paths_for_service(&connection, "missing", None)
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn workflow_and_agent_files_are_selected_by_the_service_that_emitted_them() {
        // In every summary, checkout emitted the Workflow spans and billing
        // emitted the Agent spans.
        let connection = index_with_three_files();

        assert_eq!(
            workflow_file_paths(&connection, "checkout", 2).unwrap(),
            ["/data/new.parquet", "/data/middle.parquet"]
        );
        assert!(
            workflow_file_paths(&connection, "billing", 2)
                .unwrap()
                .is_empty()
        );
        let every_file = agent_page_files(&connection, "billing", None, None, None, 3).unwrap();
        assert_eq!(every_file.file_paths.len(), 3);
        assert!(
            agent_page_files(&connection, "checkout", None, None, None, 3)
                .unwrap()
                .file_paths
                .is_empty()
        );
    }

    /// A file in which billing's Agent spans start at `earliest` at the
    /// earliest and end at `latest` at the latest.
    fn agent_file(file_path: &str, earliest: i64, latest: i64) -> FileSummary {
        let mut summary = summary(file_path);
        summary.services.insert(
            "billing".to_string(),
            ServiceSummary {
                span_count: 1,
                min_time_ns: earliest,
                max_time_ns: latest,
            },
        );
        summary
    }

    #[test]
    fn an_agent_page_reads_the_files_across_its_place_and_the_newest_below_it() {
        let mut connection = index();
        for summary in [
            agent_file("/data/long.parquet", 100, 900),
            agent_file("/data/d.parquet", 700, 800),
            agent_file("/data/c.parquet", 500, 600),
            agent_file("/data/b.parquet", 300, 400),
            agent_file("/data/a.parquet", 100, 200),
        ] {
            index_file(&mut connection, &summary).unwrap();
        }
        let page = |started_from, ended_by, starts_by| {
            agent_page_files(&connection, "billing", started_from, ended_by, starts_by, 2).unwrap()
        };

        // The first page has no place: the two newest files, and the time by
        // which a span of the next file starts.
        assert_eq!(
            page(None, None, None),
            AgentPageFiles {
                file_paths: vec!["/data/long.parquet".into(), "/data/d.parquet".into()],
                rest_starts_by_ns: Some(600),
            }
        );
        // From 600: the long file reaches across it, a file that starts
        // after it is left out, and two files below it are read.
        assert_eq!(
            page(None, None, Some(600)),
            AgentPageFiles {
                file_paths: vec![
                    "/data/long.parquet".into(),
                    "/data/c.parquet".into(),
                    "/data/b.parquet".into(),
                    "/data/a.parquet".into(),
                ],
                rest_starts_by_ns: None,
            }
        );
        assert_eq!(
            page(None, None, Some(650)),
            AgentPageFiles {
                file_paths: vec![
                    "/data/long.parquet".into(),
                    "/data/c.parquet".into(),
                    "/data/b.parquet".into(),
                ],
                rest_starts_by_ns: Some(200),
            }
        );
        // A file is left out when every span in it ended before the
        // caller's earliest start, or started after the caller's latest end.
        assert_eq!(
            page(Some(450), Some(650), None),
            AgentPageFiles {
                file_paths: vec!["/data/long.parquet".into(), "/data/c.parquet".into()],
                rest_starts_by_ns: None,
            }
        );
    }

    #[test]
    fn llm_trace_candidates_are_filtered_by_service() {
        // In every summary, trace-a is checkout's only LLM trace.
        let connection = index_with_three_files();
        let candidates = HashSet::from([
            "trace-a".to_string(),
            "trace-b".to_string(),
            "unknown".to_string(),
        ]);

        assert_eq!(
            filter_llm_trace_ids(&connection, "checkout", &candidates).unwrap(),
            HashSet::from(["trace-a".to_string()])
        );
        assert!(
            filter_llm_trace_ids(&connection, "billing", &candidates)
                .unwrap()
                .is_empty()
        );
        assert!(
            filter_llm_trace_ids(&connection, "checkout", &HashSet::new())
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn indexing_the_same_file_twice_fails_and_leaves_one_copy() {
        let mut connection = index();
        index_file(&mut connection, &summary("/data/a.parquet")).unwrap();
        assert!(index_file(&mut connection, &summary("/data/a.parquet")).is_err());
        assert_eq!(count(&connection, "parquet_files"), 1);
        assert_eq!(count(&connection, "trace_files"), 2);
    }

    #[test]
    fn removing_a_file_cascades_to_its_mappings() {
        let mut connection = index();
        index_file(&mut connection, &summary("/data/a.parquet")).unwrap();
        index_file(&mut connection, &summary("/data/b.parquet")).unwrap();

        let removed = remove_files(&mut connection, &["/data/a.parquet".to_string()]).unwrap();

        assert_eq!(removed, 1);
        assert_eq!(count(&connection, "parquet_files"), 1);
        assert_eq!(count(&connection, "trace_files"), 2);
        assert_eq!(count(&connection, "file_services"), 2);
        assert_eq!(count(&connection, "workflow_files"), 1);
        assert_eq!(count(&connection, "agent_files"), 1);
    }

    #[test]
    fn a_failed_file_is_recorded_once_and_counts_retries() {
        let connection = index();
        record_failed_file(
            &connection,
            "/data/bad.parquet",
            "Parquet",
            "corrupt footer",
            12,
        )
        .unwrap();
        record_failed_file(
            &connection,
            "/data/bad.parquet",
            "Parquet",
            "still corrupt",
            12,
        )
        .unwrap();

        let (message, retries): (String, i64) = connection
            .query_row(
                "SELECT error_message, retry_count FROM failed_parquet_files",
                [],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .unwrap();
        assert_eq!(message, "still corrupt");
        assert_eq!(retries, 2);
        assert_eq!(
            damaged_file_paths(&connection).unwrap(),
            HashSet::from(["/data/bad.parquet".to_string()])
        );
        assert!(retried_file_paths(&connection).unwrap().is_empty());
    }

    #[test]
    fn a_failure_that_can_pass_is_retried_and_forgotten_once_the_file_is_indexed() {
        let mut connection = index();
        for (path, kind) in [
            ("/data/unreadable.parquet", "Io"),
            ("/data/unwritten.parquet", "Sqlite"),
            ("/data/damaged.parquet", "InvalidData"),
        ] {
            record_failed_file(&connection, path, kind, "failed", 12).unwrap();
        }
        assert_eq!(
            retried_file_paths(&connection).unwrap(),
            HashSet::from([
                "/data/unreadable.parquet".to_string(),
                "/data/unwritten.parquet".to_string()
            ])
        );
        assert_eq!(
            damaged_file_paths(&connection).unwrap(),
            HashSet::from(["/data/damaged.parquet".to_string()])
        );

        index_file(&mut connection, &summary("/data/unreadable.parquet")).unwrap();

        assert_eq!(
            retried_file_paths(&connection).unwrap(),
            HashSet::from(["/data/unwritten.parquet".to_string()])
        );
    }
}

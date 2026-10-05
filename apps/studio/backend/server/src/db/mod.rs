//! SQLite access.
//!
//! Each database has exactly one writer connection and one reader connection,
//! each on its own thread. The writer connection is the write-serialization
//! boundary: a write transaction is one closure that runs to completion on the
//! database thread and never holds SQLite's write lock across an `await`.
//!
//! `schema/junjo.sql` and `schema/metadata.sql` are the only schema sources.

use std::path::Path;

use rusqlite::{Connection, OpenFlags, TransactionBehavior};

pub mod metadata;

/// The application database schema, and the version stamped on a database
/// created from it. Change both together.
pub const JUNJO_SCHEMA_SQL: &str = include_str!("../../../schema/junjo.sql");
pub const JUNJO_SCHEMA_VERSION: i32 = 4;

/// The metadata index schema and its version. Change both together.
pub const METADATA_SCHEMA_SQL: &str = include_str!("../../../schema/metadata.sql");
pub const METADATA_SCHEMA_VERSION: i32 = 2;

const APPLICATION_WRITER_PRAGMAS: &str = "
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;
    PRAGMA busy_timeout=5000;
    PRAGMA foreign_keys=ON;
";

const APPLICATION_READER_PRAGMAS: &str = "
    PRAGMA busy_timeout=5000;
";

const METADATA_WRITER_PRAGMAS: &str = "
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;
    PRAGMA busy_timeout=5000;
    PRAGMA cache_size=-10000;
    PRAGMA temp_store=MEMORY;
    PRAGMA mmap_size=52428800;
    PRAGMA foreign_keys=ON;
";

const METADATA_READER_PRAGMAS: &str = "
    PRAGMA busy_timeout=5000;
    PRAGMA cache_size=-10000;
    PRAGMA temp_store=MEMORY;
    PRAGMA mmap_size=52428800;
";

#[derive(Debug, thiserror::Error)]
pub enum DbError {
    #[error("database connection is closed")]
    Closed,
    #[error(transparent)]
    Sqlite(#[from] rusqlite::Error),
}

#[derive(Debug, thiserror::Error)]
pub enum SchemaError {
    #[error("database schema version {found} does not match this backend's version {expected}")]
    Mismatch { found: i32, expected: i32 },
    #[error(transparent)]
    Sqlite(#[from] rusqlite::Error),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SchemaState {
    Created,
    Current,
}

/// An asynchronous handle to one SQLite connection running on its own thread.
#[derive(Debug, Clone)]
pub struct Db {
    connection: tokio_rusqlite::Connection,
}

impl Db {
    pub fn new(connection: Connection) -> Self {
        Self {
            connection: tokio_rusqlite::Connection::from(connection),
        }
    }

    /// Run one closure on the connection's thread and return its result.
    pub async fn call<F, R>(&self, function: F) -> Result<R, DbError>
    where
        F: FnOnce(&mut Connection) -> rusqlite::Result<R> + Send + 'static,
        R: Send + 'static,
    {
        self.connection
            .call(function)
            .await
            .map_err(|error| match error {
                tokio_rusqlite::Error::Error(sqlite) => DbError::Sqlite(sqlite),
                _ => DbError::Closed,
            })
    }
}

/// The application database's two connections.
#[derive(Debug, Clone)]
pub struct ApplicationDb {
    pub writer: Db,
    pub reader: Db,
}

/// Create a database from its schema file, or confirm it has the expected
/// schema version.
pub fn ensure_schema(
    connection: &mut Connection,
    schema_sql: &str,
    version: i32,
) -> Result<SchemaState, SchemaError> {
    let found: i32 = connection.pragma_query_value(None, "user_version", |row| row.get(0))?;
    let object_count: i64 =
        connection.query_row("SELECT COUNT(*) FROM sqlite_schema", [], |row| row.get(0))?;
    if found == 0 && object_count == 0 {
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        transaction.execute_batch(schema_sql)?;
        transaction.pragma_update(None, "user_version", version)?;
        transaction.commit()?;
        return Ok(SchemaState::Created);
    }
    if found == version {
        return Ok(SchemaState::Current);
    }
    Err(SchemaError::Mismatch {
        found,
        expected: version,
    })
}

fn open_writer(path: &Path, pragmas: &str) -> rusqlite::Result<Connection> {
    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_CREATE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    connection.execute_batch(pragmas)?;
    Ok(connection)
}

fn open_reader(path: &Path, pragmas: &str) -> rusqlite::Result<Connection> {
    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    connection.execute_batch(pragmas)?;
    Ok(connection)
}

fn create_parent_directory(path: &Path) -> std::io::Result<()> {
    match path.parent() {
        Some(parent) if !parent.as_os_str().is_empty() => std::fs::create_dir_all(parent),
        _ => Ok(()),
    }
}

/// Open the application database. A database with another schema version is
/// refused: Studio has no upgrade path, so the data directory must be reset.
pub fn open_application_db(path: &Path) -> anyhow::Result<ApplicationDb> {
    create_parent_directory(path)?;
    let mut writer = open_writer(path, APPLICATION_WRITER_PRAGMAS)?;
    match ensure_schema(&mut writer, JUNJO_SCHEMA_SQL, JUNJO_SCHEMA_VERSION) {
        Ok(_) => {}
        Err(SchemaError::Mismatch { found, expected }) => anyhow::bail!(
            "{} has schema version {found}, but this backend requires version {expected}. \
             Studio has no upgrade path for application data: stop the stack, reset the \
             Studio data directory as described in \
             https://github.com/mdrideout/junjo/blob/master/apps/studio/deployments/RESET.md, \
             and start again.",
            path.display()
        ),
        Err(SchemaError::Sqlite(error)) => return Err(error.into()),
    }
    let reader = open_reader(path, APPLICATION_READER_PRAGMAS)?;
    Ok(ApplicationDb {
        writer: Db::new(writer),
        reader: Db::new(reader),
    })
}

/// The metadata index's two connections. The writer is a plain connection
/// because the indexer thread owns it.
pub struct MetadataDb {
    pub writer: Connection,
    pub reader: Db,
}

/// Open the metadata index. It is derived from cold Parquet files, so a
/// database with another schema version is deleted and rebuilt by the indexer.
pub fn open_metadata_db(path: &Path) -> anyhow::Result<MetadataDb> {
    create_parent_directory(path)?;
    let mut writer = open_writer(path, METADATA_WRITER_PRAGMAS)?;
    match ensure_schema(&mut writer, METADATA_SCHEMA_SQL, METADATA_SCHEMA_VERSION) {
        Ok(_) => {}
        Err(SchemaError::Mismatch { found, expected }) => {
            tracing::warn!(
                found,
                expected,
                path = %path.display(),
                "metadata index has another schema version; rebuilding it from Parquet"
            );
            drop(writer);
            remove_database_files(path)?;
            writer = open_writer(path, METADATA_WRITER_PRAGMAS)?;
            ensure_schema(&mut writer, METADATA_SCHEMA_SQL, METADATA_SCHEMA_VERSION)
                .map_err(anyhow::Error::from)?;
        }
        Err(SchemaError::Sqlite(error)) => return Err(error.into()),
    }
    let reader = open_reader(path, METADATA_READER_PRAGMAS)?;
    Ok(MetadataDb {
        writer,
        reader: Db::new(reader),
    })
}

fn remove_database_files(path: &Path) -> std::io::Result<()> {
    for suffix in ["", "-wal", "-shm"] {
        let mut name = path.as_os_str().to_owned();
        name.push(suffix);
        match std::fs::remove_file(&name) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

/// Write the WAL back into the main database file. Called at shutdown.
pub fn checkpoint(connection: &Connection) -> rusqlite::Result<()> {
    connection.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::auth::{session_store, users};
    use crate::features::{api_keys, cli_sign_in, evaluation, evaluation_tokens};

    /// Every feature that writes SQL for the application database lists its
    /// statements here, so a statement that no longer matches the schema
    /// fails this test instead of failing a request.
    #[test]
    fn every_application_statement_prepares_against_the_schema() {
        let mut connection = Connection::open_in_memory().unwrap();
        ensure_schema(&mut connection, JUNJO_SCHEMA_SQL, JUNJO_SCHEMA_VERSION).unwrap();
        let statements = session_store::ALL_STATEMENTS
            .iter()
            .chain(users::ALL_STATEMENTS.iter())
            .chain(api_keys::repo::ALL_STATEMENTS.iter())
            .chain(evaluation_tokens::repo::ALL_STATEMENTS.iter())
            .chain(cli_sign_in::repo::ALL_STATEMENTS.iter())
            .chain(evaluation::repo::ALL_STATEMENTS.iter());
        for statement in statements {
            connection
                .prepare(statement)
                .unwrap_or_else(|error| panic!("{statement}: {error}"));
        }
    }

    #[test]
    fn a_missing_database_is_created_and_stamped() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite/junjo.db");
        open_application_db(&path).unwrap();

        let connection = Connection::open(&path).unwrap();
        let version: i32 = connection
            .pragma_query_value(None, "user_version", |row| row.get(0))
            .unwrap();
        assert_eq!(version, JUNJO_SCHEMA_VERSION);
        let tables: Vec<String> = connection
            .prepare("SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name")
            .unwrap()
            .query_map([], |row| row.get(0))
            .unwrap()
            .collect::<rusqlite::Result<_>>()
            .unwrap();
        assert_eq!(
            tables,
            [
                "api_keys",
                "cli_sign_ins",
                "eval_case_attempts",
                "eval_cases",
                "eval_datasets",
                "eval_runs",
                "evaluation_tokens",
                "sessions",
                "users"
            ]
        );
    }

    #[test]
    fn an_existing_database_with_the_current_version_is_reused() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("junjo.db");
        drop(open_application_db(&path).unwrap());
        let mut connection = Connection::open(&path).unwrap();
        assert_eq!(
            ensure_schema(&mut connection, JUNJO_SCHEMA_SQL, JUNJO_SCHEMA_VERSION).unwrap(),
            SchemaState::Current
        );
    }

    #[test]
    fn an_application_database_from_another_backend_is_refused() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("junjo.db");
        // A database created by the Python backend: tables, but no version.
        Connection::open(&path)
            .unwrap()
            .execute_batch("CREATE TABLE alembic_version (version_num TEXT);")
            .unwrap();

        let error = open_application_db(&path).unwrap_err().to_string();
        assert!(error.contains("schema version 0"), "{error}");
        assert!(error.contains("reset the Studio data directory"), "{error}");
        assert!(error.contains("deployments/RESET.md"), "{error}");
    }

    #[test]
    fn a_metadata_index_with_another_version_is_rebuilt() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("metadata.db");
        Connection::open(&path)
            .unwrap()
            .execute_batch("CREATE TABLE legacy (value TEXT); PRAGMA user_version = 99;")
            .unwrap();

        let metadata = open_metadata_db(&path).unwrap();
        let legacy_tables: i64 = metadata
            .writer
            .query_row(
                "SELECT COUNT(*) FROM sqlite_schema WHERE name = 'legacy'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(legacy_tables, 0);
        let version: i32 = metadata
            .writer
            .pragma_query_value(None, "user_version", |row| row.get(0))
            .unwrap();
        assert_eq!(version, METADATA_SCHEMA_VERSION);
    }

    #[test]
    fn the_reader_connection_cannot_write() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("metadata.db");
        drop(open_metadata_db(&path).unwrap());
        let reader = open_reader(&path, METADATA_READER_PRAGMAS).unwrap();
        assert!(reader.execute("DELETE FROM parquet_files", []).is_err());
    }
}

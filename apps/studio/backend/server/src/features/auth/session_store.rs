//! The `tower-sessions` store, backed by the `sessions` table in `junjo.db`.
//!
//! `tower-sessions` owns session identifiers, cookie handling, and expiry
//! policy. This adapter only stores and loads its records.

use async_trait::async_trait;
use rusqlite::{OptionalExtension, params};
use time::OffsetDateTime;
use tower_sessions::SessionStore;
use tower_sessions::session::{Id, Record};
use tower_sessions::session_store::{Error, Result};

use crate::db::{ApplicationDb, DbError};

pub const INSERT_SESSION: &str =
    "INSERT OR IGNORE INTO sessions (id, data, expiry_date) VALUES (?1, ?2, ?3)";
pub const UPSERT_SESSION: &str = "
    INSERT INTO sessions (id, data, expiry_date) VALUES (?1, ?2, ?3)
    ON CONFLICT (id) DO UPDATE SET
        data = excluded.data,
        expiry_date = excluded.expiry_date";
pub const SELECT_SESSION: &str =
    "SELECT data, expiry_date FROM sessions WHERE id = ?1 AND expiry_date > ?2";
pub const DELETE_SESSION: &str = "DELETE FROM sessions WHERE id = ?1";
pub const DELETE_EXPIRED_SESSIONS: &str = "DELETE FROM sessions WHERE expiry_date <= ?1";

#[cfg(test)]
pub const ALL_STATEMENTS: [&str; 5] = [
    INSERT_SESSION,
    UPSERT_SESSION,
    SELECT_SESSION,
    DELETE_SESSION,
    DELETE_EXPIRED_SESSIONS,
];

#[derive(Debug, Clone)]
pub struct SqliteSessionStore {
    db: ApplicationDb,
}

impl SqliteSessionStore {
    pub fn new(db: ApplicationDb) -> Self {
        Self { db }
    }

    /// Remove sessions that have expired. Called when a session is created,
    /// so the table cannot grow without bound.
    pub async fn delete_expired(&self) -> std::result::Result<usize, DbError> {
        let now = OffsetDateTime::now_utc().unix_timestamp();
        self.db
            .writer
            .call(move |connection| {
                connection
                    .prepare_cached(DELETE_EXPIRED_SESSIONS)?
                    .execute(params![now])
            })
            .await
    }
}

fn backend(error: DbError) -> Error {
    Error::Backend(error.to_string())
}

fn encode(record: &Record) -> Result<String> {
    serde_json::to_string(&record.data).map_err(|error| Error::Encode(error.to_string()))
}

#[async_trait]
impl SessionStore for SqliteSessionStore {
    async fn create(&self, record: &mut Record) -> Result<()> {
        loop {
            let id = record.id.to_string();
            let data = encode(record)?;
            let expiry_date = record.expiry_date.unix_timestamp();
            let inserted = self
                .db
                .writer
                .call(move |connection| {
                    connection.prepare_cached(INSERT_SESSION)?.execute(params![
                        id,
                        data,
                        expiry_date
                    ])
                })
                .await
                .map_err(backend)?;
            if inserted == 1 {
                return Ok(());
            }
            // The identifier is already taken. Draw another.
            record.id = Id::default();
        }
    }

    async fn save(&self, record: &Record) -> Result<()> {
        let id = record.id.to_string();
        let data = encode(record)?;
        let expiry_date = record.expiry_date.unix_timestamp();
        self.db
            .writer
            .call(move |connection| {
                connection
                    .prepare_cached(UPSERT_SESSION)?
                    .execute(params![id, data, expiry_date])
            })
            .await
            .map_err(backend)?;
        Ok(())
    }

    async fn load(&self, session_id: &Id) -> Result<Option<Record>> {
        let id = session_id.to_string();
        let now = OffsetDateTime::now_utc().unix_timestamp();
        let stored: Option<(String, i64)> = self
            .db
            .reader
            .call(move |connection| {
                connection
                    .prepare_cached(SELECT_SESSION)?
                    .query_row(params![id, now], |row| Ok((row.get(0)?, row.get(1)?)))
                    .optional()
            })
            .await
            .map_err(backend)?;
        let Some((data, expiry_date)) = stored else {
            return Ok(None);
        };
        Ok(Some(Record {
            id: *session_id,
            data: serde_json::from_str(&data).map_err(|error| Error::Decode(error.to_string()))?,
            expiry_date: OffsetDateTime::from_unix_timestamp(expiry_date)
                .map_err(|error| Error::Decode(error.to_string()))?,
        }))
    }

    async fn delete(&self, session_id: &Id) -> Result<()> {
        let id = session_id.to_string();
        self.db
            .writer
            .call(move |connection| {
                connection
                    .prepare_cached(DELETE_SESSION)?
                    .execute(params![id])
            })
            .await
            .map_err(backend)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use serde_json::json;
    use time::Duration;

    use super::*;
    use crate::db;

    fn store() -> (SqliteSessionStore, tempfile::TempDir) {
        let directory = tempfile::tempdir().unwrap();
        let db = db::open_application_db(&directory.path().join("junjo.db")).unwrap();
        (SqliteSessionStore::new(db), directory)
    }

    fn record(expires_in: Duration) -> Record {
        Record {
            id: Id::default(),
            data: HashMap::from([("user_id".to_string(), json!("user-1"))]),
            expiry_date: OffsetDateTime::now_utc() + expires_in,
        }
    }

    #[tokio::test]
    async fn a_session_is_created_loaded_updated_and_deleted() {
        let (store, _directory) = store();
        let mut created = record(Duration::hours(1));
        store.create(&mut created).await.unwrap();

        let loaded = store.load(&created.id).await.unwrap().unwrap();
        assert_eq!(loaded.data, created.data);
        assert_eq!(
            loaded.expiry_date.unix_timestamp(),
            created.expiry_date.unix_timestamp()
        );

        let mut updated = created.clone();
        updated.data.insert("renewed_at".to_string(), json!(42));
        updated.expiry_date += Duration::days(1);
        store.save(&updated).await.unwrap();
        let loaded = store.load(&created.id).await.unwrap().unwrap();
        assert_eq!(loaded.data["renewed_at"], json!(42));
        assert_eq!(
            loaded.expiry_date.unix_timestamp(),
            updated.expiry_date.unix_timestamp()
        );

        store.delete(&created.id).await.unwrap();
        assert!(store.load(&created.id).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn an_expired_session_is_not_loaded_and_is_cleaned_up() {
        let (store, _directory) = store();
        let mut expired = record(Duration::seconds(-1));
        let mut live = record(Duration::hours(1));
        store.create(&mut expired).await.unwrap();
        store.create(&mut live).await.unwrap();

        assert!(store.load(&expired.id).await.unwrap().is_none());
        assert!(store.load(&live.id).await.unwrap().is_some());
        assert_eq!(store.delete_expired().await.unwrap(), 1);
        assert_eq!(store.delete_expired().await.unwrap(), 0);
    }

    #[tokio::test]
    async fn creating_a_session_never_reuses_an_existing_identifier() {
        let (store, _directory) = store();
        let mut first = record(Duration::hours(1));
        store.create(&mut first).await.unwrap();

        let mut second = record(Duration::hours(1));
        second.id = first.id;
        second.data.insert("user_id".to_string(), json!("user-2"));
        store.create(&mut second).await.unwrap();

        assert_ne!(second.id, first.id);
        let original = store.load(&first.id).await.unwrap().unwrap();
        assert_eq!(original.data["user_id"], json!("user-1"));
    }
}

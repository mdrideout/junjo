//! Statements for the `api_keys` table.

use rusqlite::{Connection, OptionalExtension, Row, params};
use serde::Serialize;
use utoipa::ToSchema;

use crate::timestamps::UtcSeconds;

/// One Application Telemetry API key. The key value is recoverable by design
/// (Studio ADR-010).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[schema(as = APIKeyRead)]
pub struct ApiKey {
    /// Unique identifier.
    #[schema(examples("key_9x7v6u5t4s3r2q1p"))]
    pub id: String,
    /// Canonical application telemetry API key.
    #[schema(examples("jtel_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2"))]
    pub key: String,
    /// Human-readable name.
    #[schema(examples("Production API Key"))]
    pub name: String,
    /// When the key was created (UTC).
    #[schema(value_type = String, format = DateTime, examples("2025-01-15T10:30:00Z"))]
    pub created_at: UtcSeconds,
}

pub const INSERT_API_KEY: &str =
    "INSERT INTO api_keys (id, key, name, created_at) VALUES (?1, ?2, ?3, ?4)";
pub const SELECT_API_KEYS: &str = "
    SELECT id, key, name, created_at FROM api_keys
    WHERE deleted_at IS NULL
    ORDER BY created_at DESC, rowid DESC";
/// Deleting deactivates: the row stays, without the key value.
pub const DEACTIVATE_API_KEY: &str =
    "UPDATE api_keys SET key = NULL, deleted_at = ?2 WHERE id = ?1 AND deleted_at IS NULL";
pub const SELECT_ACTIVE_KEY_ID: &str = "SELECT id FROM api_keys WHERE key = ?1";

#[cfg(test)]
pub const ALL_STATEMENTS: [&str; 4] = [
    INSERT_API_KEY,
    SELECT_API_KEYS,
    DEACTIVATE_API_KEY,
    SELECT_ACTIVE_KEY_ID,
];

fn api_key_from_row(row: &Row<'_>) -> rusqlite::Result<ApiKey> {
    Ok(ApiKey {
        id: row.get(0)?,
        key: row.get(1)?,
        name: row.get(2)?,
        created_at: row.get(3)?,
    })
}

pub fn create(connection: &Connection, api_key: &ApiKey) -> rusqlite::Result<()> {
    connection.prepare_cached(INSERT_API_KEY)?.execute(params![
        api_key.id,
        api_key.key,
        api_key.name,
        api_key.created_at
    ])?;
    Ok(())
}

/// The active API keys, newest first.
pub fn list(connection: &Connection) -> rusqlite::Result<Vec<ApiKey>> {
    connection
        .prepare_cached(SELECT_API_KEYS)?
        .query_map([], api_key_from_row)?
        .collect()
}

/// Delete one key: deactivate it and forget its key value. Its identifier
/// and name stay on record. Returns whether an active key was deleted.
pub fn delete(connection: &Connection, id: &str, now: UtcSeconds) -> rusqlite::Result<bool> {
    Ok(connection
        .prepare_cached(DEACTIVATE_API_KEY)?
        .execute(params![id, now])?
        > 0)
}

/// The identifier of the active ingestion API key with this value. This is
/// the authoritative answer the ingestion service asks for. A deleted key
/// has no value, so it never matches.
pub fn active_key_id(connection: &Connection, key: &str) -> rusqlite::Result<Option<String>> {
    connection
        .prepare_cached(SELECT_ACTIVE_KEY_ID)?
        .query_row(params![key], |row| row.get(0))
        .optional()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::{JUNJO_SCHEMA_SQL, JUNJO_SCHEMA_VERSION, ensure_schema};

    #[test]
    fn a_deleted_key_keeps_its_row_without_its_value_and_no_longer_validates() {
        let mut connection = Connection::open_in_memory().unwrap();
        ensure_schema(&mut connection, JUNJO_SCHEMA_SQL, JUNJO_SCHEMA_VERSION).unwrap();
        let api_key = ApiKey {
            id: "key-1".to_string(),
            key: "jtel_secret".to_string(),
            name: "Production".to_string(),
            created_at: UtcSeconds::now(),
        };
        create(&connection, &api_key).unwrap();
        let active = active_key_id(&connection, "jtel_secret").unwrap();
        assert_eq!(active.as_deref(), Some("key-1"));

        assert!(delete(&connection, "key-1", UtcSeconds::now()).unwrap());

        assert_eq!(active_key_id(&connection, "jtel_secret").unwrap(), None);
        assert!(list(&connection).unwrap().is_empty());
        let (name, key, deleted): (String, Option<String>, bool) = connection
            .query_row(
                "SELECT name, key, deleted_at IS NOT NULL FROM api_keys WHERE id = 'key-1'",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!((name.as_str(), key, deleted), ("Production", None, true));
        // A key is deleted once.
        assert!(!delete(&connection, "key-1", UtcSeconds::now()).unwrap());
    }
}

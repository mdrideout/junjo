//! Statements for the `evaluation_tokens` table.

use rusqlite::{Connection, OptionalExtension, Row, params};

use super::{EvaluationTokenCurrent, EvaluationTokenRead, TokenScopes};
use crate::pagination::TimePosition;
use crate::timestamps::UtcSeconds;

pub const INSERT_TOKEN: &str = "
    INSERT INTO evaluation_tokens (
        id, name, token, evaluation_read, evaluation_write, evidence_read,
        expires_at, created_by_user_id, created_at
    ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)";
pub const SELECT_NEWEST_TOKENS: &str = "
    SELECT id, name, token, evaluation_read, evaluation_write, evidence_read,
           expires_at, created_by_user_id, created_at
    FROM evaluation_tokens
    ORDER BY created_at DESC, id DESC
    LIMIT ?1";
pub const SELECT_TOKENS_AFTER: &str = "
    SELECT id, name, token, evaluation_read, evaluation_write, evidence_read,
           expires_at, created_by_user_id, created_at
    FROM evaluation_tokens
    WHERE created_at < ?1 OR (created_at = ?1 AND id < ?2)
    ORDER BY created_at DESC, id DESC
    LIMIT ?3";
pub const DELETE_TOKEN: &str = "DELETE FROM evaluation_tokens WHERE id = ?1";
pub const SELECT_TOKEN_CREDENTIAL: &str = "
    SELECT t.id, t.evaluation_read, t.evaluation_write, t.evidence_read,
           t.expires_at, u.id, u.email, u.is_active
    FROM evaluation_tokens AS t
    JOIN users AS u ON u.id = t.created_by_user_id
    WHERE t.token = ?1";
pub const SELECT_CURRENT_TOKEN: &str = "
    SELECT id, name, evaluation_read, evaluation_write, evidence_read,
           expires_at, created_at
    FROM evaluation_tokens
    WHERE id = ?1";

#[cfg(test)]
pub const ALL_STATEMENTS: [&str; 6] = [
    INSERT_TOKEN,
    SELECT_NEWEST_TOKENS,
    SELECT_TOKENS_AFTER,
    DELETE_TOKEN,
    SELECT_TOKEN_CREDENTIAL,
    SELECT_CURRENT_TOKEN,
];

/// What one authentication check needs to know about a token.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TokenCredential {
    pub id: String,
    pub scopes: TokenScopes,
    pub expires_at: Option<UtcSeconds>,
    pub user_id: String,
    pub user_email: String,
    pub user_is_active: bool,
}

fn token_from_row(row: &Row<'_>) -> rusqlite::Result<EvaluationTokenRead> {
    Ok(EvaluationTokenRead {
        id: row.get(0)?,
        name: row.get(1)?,
        token: row.get(2)?,
        scopes: TokenScopes {
            evaluation_read: row.get(3)?,
            evaluation_write: row.get(4)?,
            evidence_read: row.get(5)?,
        },
        expires_at: row.get(6)?,
        created_by_user_id: row.get(7)?,
        created_at: row.get(8)?,
    })
}

pub fn create(connection: &Connection, token: &EvaluationTokenRead) -> rusqlite::Result<()> {
    connection.prepare_cached(INSERT_TOKEN)?.execute(params![
        token.id,
        token.name,
        token.token,
        token.scopes.evaluation_read,
        token.scopes.evaluation_write,
        token.scopes.evidence_read,
        token.expires_at,
        token.created_by_user_id,
        token.created_at,
    ])?;
    Ok(())
}

/// Up to `limit` tokens, newest first, starting after `after`.
pub fn list(
    connection: &Connection,
    after: Option<&TimePosition>,
    limit: u32,
) -> rusqlite::Result<Vec<EvaluationTokenRead>> {
    match after {
        None => connection
            .prepare_cached(SELECT_NEWEST_TOKENS)?
            .query_map(params![limit], token_from_row)?
            .collect(),
        Some(after) => connection
            .prepare_cached(SELECT_TOKENS_AFTER)?
            .query_map(params![after.created_at, after.id, limit], token_from_row)?
            .collect(),
    }
}

/// Delete one token. Returns whether a token was deleted.
pub fn delete(connection: &Connection, id: &str) -> rusqlite::Result<bool> {
    Ok(connection
        .prepare_cached(DELETE_TOKEN)?
        .execute(params![id])?
        > 0)
}

/// The credential a bearer token names. This only reads: authenticating a
/// request never writes.
pub fn credential(
    connection: &Connection,
    token: &str,
) -> rusqlite::Result<Option<TokenCredential>> {
    connection
        .prepare_cached(SELECT_TOKEN_CREDENTIAL)?
        .query_row(params![token], |row| {
            Ok(TokenCredential {
                id: row.get(0)?,
                scopes: TokenScopes {
                    evaluation_read: row.get(1)?,
                    evaluation_write: row.get(2)?,
                    evidence_read: row.get(3)?,
                },
                expires_at: row.get(4)?,
                user_id: row.get(5)?,
                user_email: row.get(6)?,
                user_is_active: row.get(7)?,
            })
        })
        .optional()
}

/// What a token is told about itself. The token value is not part of it.
pub fn current(
    connection: &Connection,
    id: &str,
) -> rusqlite::Result<Option<EvaluationTokenCurrent>> {
    connection
        .prepare_cached(SELECT_CURRENT_TOKEN)?
        .query_row(params![id], |row| {
            Ok(EvaluationTokenCurrent {
                id: row.get(0)?,
                name: row.get(1)?,
                scopes: TokenScopes {
                    evaluation_read: row.get(2)?,
                    evaluation_write: row.get(3)?,
                    evidence_read: row.get(4)?,
                },
                expires_at: row.get(5)?,
                created_at: row.get(6)?,
            })
        })
        .optional()
}

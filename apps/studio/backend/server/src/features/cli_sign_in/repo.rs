//! Statements and transactions for the `cli_sign_ins` table.
//!
//! A CLI sign-in past its `expires_at` is treated as absent. Every lookup
//! compares the stored expiry with the current time, so nothing has to run
//! for a sign-in to expire.

use rusqlite::types::{FromSql, FromSqlError, FromSqlResult, ValueRef};
use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};

use super::{CliSignInApproved, CliSignInToken, TokenType};
use crate::features::evaluation_tokens::{self, EvaluationTokenRead, TokenScopes};
use crate::timestamps::UtcSeconds;

pub const DELETE_EXPIRED_SIGN_INS: &str = "DELETE FROM cli_sign_ins WHERE expires_at <= ?1";
pub const INSERT_SIGN_IN: &str = "
    INSERT INTO cli_sign_ins (
        device_code, user_code, client_name, evaluation_read, evaluation_write,
        evidence_read, status, token_id, created_at, expires_at
    ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'pending', NULL, ?7, ?8)
    ON CONFLICT DO NOTHING";
pub const SELECT_PENDING_SIGN_IN: &str = "
    SELECT client_name, evaluation_read, evaluation_write, evidence_read,
           expires_at
    FROM cli_sign_ins
    WHERE user_code = ?1 AND status = 'pending' AND expires_at > ?2";
pub const APPROVE_SIGN_IN: &str = "
    UPDATE cli_sign_ins SET status = 'approved', token_id = ?2
    WHERE user_code = ?1";
pub const DENY_SIGN_IN: &str = "
    UPDATE cli_sign_ins SET status = 'denied'
    WHERE user_code = ?1 AND status = 'pending' AND expires_at > ?2";
pub const SELECT_SIGN_IN_STATUS: &str =
    "SELECT status FROM cli_sign_ins WHERE device_code = ?1 AND expires_at > ?2";
pub const SELECT_APPROVED_TOKEN: &str = "
    SELECT t.token, t.id, t.evaluation_read, t.evaluation_write,
           t.evidence_read, t.expires_at
    FROM cli_sign_ins AS s
    JOIN evaluation_tokens AS t ON t.id = s.token_id
    WHERE s.device_code = ?1";
pub const DELETE_SIGN_IN: &str = "DELETE FROM cli_sign_ins WHERE device_code = ?1";

#[cfg(test)]
pub const ALL_STATEMENTS: [&str; 8] = [
    DELETE_EXPIRED_SIGN_INS,
    INSERT_SIGN_IN,
    SELECT_PENDING_SIGN_IN,
    APPROVE_SIGN_IN,
    DENY_SIGN_IN,
    SELECT_SIGN_IN_STATUS,
    SELECT_APPROVED_TOKEN,
    DELETE_SIGN_IN,
];

/// What starting a CLI sign-in stores.
pub struct NewSignIn {
    pub device_code: String,
    /// The user code without its hyphen.
    pub user_code: String,
    pub client_name: String,
    pub scopes: TokenScopes,
    pub created_at: UtcSeconds,
    pub expires_at: UtcSeconds,
}

/// What a pending CLI sign-in asks for.
pub struct PendingSignIn {
    pub client_name: String,
    pub scopes: TokenScopes,
    pub expires_at: UtcSeconds,
}

/// Where an unexpired CLI sign-in stands.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SignInStatus {
    Pending,
    Approved,
    Denied,
}

// A status is stored as its lowercase name.
impl FromSql for SignInStatus {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        match value.as_str()? {
            "pending" => Ok(Self::Pending),
            "approved" => Ok(Self::Approved),
            "denied" => Ok(Self::Denied),
            other => Err(FromSqlError::Other(
                format!("unknown stored status {other:?}").into(),
            )),
        }
    }
}

/// What collecting with a device code produced.
pub enum Collection {
    /// No unexpired sign-in has the device code.
    Expired,
    /// The sign-in is not decided yet. It stays.
    Pending,
    /// The sign-in was denied. It is deleted.
    Denied,
    /// The sign-in was approved. It is deleted, and this is its token.
    Token(CliSignInToken),
}

/// Start a CLI sign-in, after deleting every expired one, so the table grows
/// only with sign-ins that can still be used.
///
/// Returns false, and starts nothing, when a sign-in already has the device
/// code or the user code.
pub fn start(connection: &mut Connection, sign_in: &NewSignIn) -> rusqlite::Result<bool> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    transaction
        .prepare_cached(DELETE_EXPIRED_SIGN_INS)?
        .execute(params![sign_in.created_at])?;
    let inserted = transaction
        .prepare_cached(INSERT_SIGN_IN)?
        .execute(params![
            sign_in.device_code,
            sign_in.user_code,
            sign_in.client_name,
            sign_in.scopes.evaluation_read,
            sign_in.scopes.evaluation_write,
            sign_in.scopes.evidence_read,
            sign_in.created_at,
            sign_in.expires_at,
        ])?;
    transaction.commit()?;
    Ok(inserted == 1)
}

/// The pending, unexpired CLI sign-in with a user code.
pub fn pending(
    connection: &Connection,
    user_code: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Option<PendingSignIn>> {
    connection
        .prepare_cached(SELECT_PENDING_SIGN_IN)?
        .query_row(params![user_code, now], |row| {
            Ok(PendingSignIn {
                client_name: row.get(0)?,
                scopes: TokenScopes {
                    evaluation_read: row.get(1)?,
                    evaluation_write: row.get(2)?,
                    evidence_read: row.get(3)?,
                },
                expires_at: row.get(4)?,
            })
        })
        .optional()
}

/// Approve a pending CLI sign-in. One write transaction mints its developer
/// access token, an ordinary one with no expiry that belongs to the approving
/// user, and records that token on the sign-in.
///
/// Returns `None`, and mints nothing, when no pending, unexpired sign-in has
/// the user code.
pub fn approve(
    connection: &mut Connection,
    user_code: &str,
    token_id: &str,
    token: &str,
    user_id: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Option<CliSignInApproved>> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let Some(sign_in) = pending(&transaction, user_code, now)? else {
        return Ok(None);
    };
    let minted = EvaluationTokenRead {
        id: token_id.to_string(),
        name: sign_in.client_name,
        token: token.to_string(),
        scopes: sign_in.scopes,
        expires_at: None,
        created_by_user_id: Some(user_id.to_string()),
        created_at: now,
    };
    evaluation_tokens::repo::create(&transaction, &minted)?;
    transaction
        .prepare_cached(APPROVE_SIGN_IN)?
        .execute(params![user_code, minted.id])?;
    transaction.commit()?;
    Ok(Some(CliSignInApproved {
        token_id: minted.id,
        token_name: minted.name,
    }))
}

/// Deny a pending, unexpired CLI sign-in. Returns whether one was denied.
pub fn deny(connection: &Connection, user_code: &str, now: UtcSeconds) -> rusqlite::Result<bool> {
    Ok(connection
        .prepare_cached(DENY_SIGN_IN)?
        .execute(params![user_code, now])?
        > 0)
}

/// Where the unexpired CLI sign-in with a device code stands.
pub fn status(
    connection: &Connection,
    device_code: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Option<SignInStatus>> {
    connection
        .prepare_cached(SELECT_SIGN_IN_STATUS)?
        .query_row(params![device_code, now], |row| row.get(0))
        .optional()
}

/// Collect a decided CLI sign-in. One write transaction reads what the
/// sign-in came to and deletes it, so its token is handed over once.
pub fn collect(
    connection: &mut Connection,
    device_code: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Collection> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let collection = match status(&transaction, device_code, now)? {
        None => return Ok(Collection::Expired),
        Some(SignInStatus::Pending) => return Ok(Collection::Pending),
        Some(SignInStatus::Denied) => Collection::Denied,
        Some(SignInStatus::Approved) => Collection::Token(
            transaction
                .prepare_cached(SELECT_APPROVED_TOKEN)?
                .query_row(params![device_code], |row| {
                    Ok(CliSignInToken {
                        access_token: row.get(0)?,
                        token_type: TokenType::Bearer,
                        token_id: row.get(1)?,
                        scopes: TokenScopes {
                            evaluation_read: row.get(2)?,
                            evaluation_write: row.get(3)?,
                            evidence_read: row.get(4)?,
                        },
                        expires_at: row.get(5)?,
                    })
                })?,
        ),
    };
    transaction
        .prepare_cached(DELETE_SIGN_IN)?
        .execute(params![device_code])?;
    transaction.commit()?;
    Ok(collection)
}

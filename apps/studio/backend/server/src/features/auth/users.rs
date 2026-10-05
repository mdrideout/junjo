//! Statements for the `users` table.

use rusqlite::{Connection, OptionalExtension, Row, TransactionBehavior, params};
use serde::Serialize;
use utoipa::ToSchema;

use crate::timestamps::UtcSeconds;

/// One Studio user. The password hash is never part of this type.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[schema(as = UserRead)]
pub struct User {
    /// Unique user identifier.
    #[schema(examples("usr_2k4h6j8m9n0p1q2r"))]
    pub id: String,
    /// User email address.
    #[schema(format = Email, examples("alice@example.com"))]
    pub email: String,
    /// Whether the user account is active.
    #[schema(examples(true))]
    pub is_active: bool,
    /// When the user was created (UTC).
    #[schema(value_type = String, format = DateTime, examples("2025-01-15T10:30:00Z"))]
    pub created_at: UtcSeconds,
    /// When the user was last updated (UTC).
    #[schema(value_type = String, format = DateTime, examples("2025-01-15T10:30:00Z"))]
    pub updated_at: UtcSeconds,
}

/// What sign-in needs to know about the user an email address names.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UserCredentials {
    pub id: String,
    pub password_hash: String,
    pub is_active: bool,
}

pub const COUNT_USERS: &str = "SELECT COUNT(*) FROM users";
pub const INSERT_USER: &str = "
    INSERT INTO users (id, email, password_hash, is_active, created_at, updated_at)
    VALUES (?1, ?2, ?3, 1, ?4, ?4)
    ON CONFLICT (email) DO NOTHING";
pub const SELECT_USER_BY_ID: &str =
    "SELECT id, email, is_active, created_at, updated_at FROM users WHERE id = ?1";
pub const SELECT_USER_CREDENTIALS: &str =
    "SELECT id, password_hash, is_active FROM users WHERE email = ?1";
pub const SELECT_USERS: &str =
    "SELECT id, email, is_active, created_at, updated_at FROM users ORDER BY rowid";
pub const DELETE_USER: &str = "DELETE FROM users WHERE id = ?1";

#[cfg(test)]
pub const ALL_STATEMENTS: [&str; 6] = [
    COUNT_USERS,
    INSERT_USER,
    SELECT_USER_BY_ID,
    SELECT_USER_CREDENTIALS,
    SELECT_USERS,
    DELETE_USER,
];

fn user_from_row(row: &Row<'_>) -> rusqlite::Result<User> {
    Ok(User {
        id: row.get(0)?,
        email: row.get(1)?,
        is_active: row.get(2)?,
        created_at: row.get(3)?,
        updated_at: row.get(4)?,
    })
}

pub fn has_users(connection: &Connection) -> rusqlite::Result<bool> {
    let count: i64 = connection
        .prepare_cached(COUNT_USERS)?
        .query_row([], |row| row.get(0))?;
    Ok(count > 0)
}

#[derive(Debug, PartialEq, Eq)]
pub enum FirstUserOutcome {
    Created(User),
    UsersAlreadyExist,
}

/// Create the first user only if no user exists.
///
/// The check and the insert share one write transaction, so concurrent
/// bootstrap requests cannot both succeed.
pub fn create_first_user(
    connection: &mut Connection,
    id: &str,
    email: &str,
    password_hash: &str,
    now: UtcSeconds,
) -> rusqlite::Result<FirstUserOutcome> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    if has_users(&transaction)? {
        return Ok(FirstUserOutcome::UsersAlreadyExist);
    }
    let user = create_user(&transaction, id, email, password_hash, now)?;
    transaction.commit()?;
    Ok(user.map_or(
        FirstUserOutcome::UsersAlreadyExist,
        FirstUserOutcome::Created,
    ))
}

/// Create a user. Returns `None` when the email address is already taken.
pub fn create_user(
    connection: &Connection,
    id: &str,
    email: &str,
    password_hash: &str,
    now: UtcSeconds,
) -> rusqlite::Result<Option<User>> {
    let inserted =
        connection
            .prepare_cached(INSERT_USER)?
            .execute(params![id, email, password_hash, now])?;
    Ok((inserted > 0).then(|| User {
        id: id.to_string(),
        email: email.to_string(),
        is_active: true,
        created_at: now,
        updated_at: now,
    }))
}

pub fn user_by_id(connection: &Connection, id: &str) -> rusqlite::Result<Option<User>> {
    connection
        .prepare_cached(SELECT_USER_BY_ID)?
        .query_row(params![id], user_from_row)
        .optional()
}

pub fn credentials_by_email(
    connection: &Connection,
    email: &str,
) -> rusqlite::Result<Option<UserCredentials>> {
    connection
        .prepare_cached(SELECT_USER_CREDENTIALS)?
        .query_row(params![email], |row| {
            Ok(UserCredentials {
                id: row.get(0)?,
                password_hash: row.get(1)?,
                is_active: row.get(2)?,
            })
        })
        .optional()
}

/// Every user, oldest first.
pub fn list(connection: &Connection) -> rusqlite::Result<Vec<User>> {
    connection
        .prepare_cached(SELECT_USERS)?
        .query_map([], user_from_row)?
        .collect()
}

/// Delete one user. Returns whether a user was deleted.
pub fn delete(connection: &Connection, id: &str) -> rusqlite::Result<bool> {
    Ok(connection
        .prepare_cached(DELETE_USER)?
        .execute(params![id])?
        > 0)
}

"""
Authentication utilities for password hashing.

Uses bcrypt for secure password hashing, compatible with the Go implementation.
Session management is handled by middleware (SecureCookiesMiddleware + SessionMiddleware).
"""

import bcrypt


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Matches the Go implementation: bcrypt.GenerateFromPassword with DefaultCost.

    Args:
        password: Plain text password

    Returns:
        Hashed password string (bcrypt format)

    Example:
        >>> hashed = hash_password("my_secure_password")
        >>> isinstance(hashed, str)
        True
        >>> len(hashed) > 0
        True
    """
    # bcrypt requires bytes input
    password_bytes = password.encode("utf-8")

    # Generate salt and hash (cost=12 is bcrypt default, matching Go)
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())

    # Return as string
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Matches the Go implementation: bcrypt.CompareHashAndPassword.

    Args:
        plain_password: Plain text password from user
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise

    Example:
        >>> hashed = hash_password("test123")
        >>> verify_password("test123", hashed)
        True
        >>> verify_password("wrong", hashed)
        False
    """
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except (ValueError, AttributeError):
        # Invalid hash format or encoding error
        return False

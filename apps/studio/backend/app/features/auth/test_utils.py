"""Unit tests for password hashing.

Tests the password hashing and verification functions using bcrypt.
"""

import pytest

from app.features.auth.utils import hash_password, verify_password


@pytest.mark.unit
def test_hash_password():
    """Test password hashing."""
    password = "test_password_123"
    hashed = hash_password(password)

    # Should return a non-empty string
    assert isinstance(hashed, str)
    assert len(hashed) > 0
    assert hashed != password
    # Bcrypt hashes start with $2b$ or $2a$
    assert hashed.startswith("$2")


@pytest.mark.unit
def test_verify_password_correct():
    """Test password verification with correct password."""
    password = "test_password_123"
    hashed = hash_password(password)

    # Should verify correctly
    assert verify_password(password, hashed) is True


@pytest.mark.unit
def test_verify_password_incorrect():
    """Test password verification with incorrect password."""
    password = "test_password_123"
    wrong_password = "wrong_password"
    hashed = hash_password(password)

    # Should fail verification
    assert verify_password(wrong_password, hashed) is False


@pytest.mark.unit
def test_hash_password_different_each_time():
    """Test that hashing the same password twice produces different hashes (due to salt)."""
    password = "test_password_123"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    # Should be different due to random salt
    assert hash1 != hash2

    # But both should verify correctly
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True


@pytest.mark.unit
def test_verify_password_with_invalid_hash():
    """Test password verification with an invalid hash format."""
    password = "test_password"
    invalid_hash = "not_a_valid_hash"

    # Should return False, not raise an exception
    assert verify_password(password, invalid_hash) is False


@pytest.mark.unit
def test_verify_password_empty_password():
    """Test password verification with empty password."""
    hashed = hash_password("test123")

    # Should return False for empty password
    assert verify_password("", hashed) is False


@pytest.mark.unit
def test_hash_password_unicode():
    """Test password hashing with Unicode characters."""
    password = "пароль123!@#$"  # Russian + numbers + symbols
    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert verify_password(password, hashed) is True
    assert verify_password("wrong", hashed) is False

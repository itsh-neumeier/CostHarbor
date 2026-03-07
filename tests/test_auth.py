"""Tests for authentication."""

from app.auth.security import hash_password, verify_password


def test_password_hashing():
    password = "test-password-123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_password_hash_uniqueness():
    pw = "same-password"
    h1 = hash_password(pw)
    h2 = hash_password(pw)
    assert h1 != h2  # bcrypt salts differ
    assert verify_password(pw, h1)
    assert verify_password(pw, h2)

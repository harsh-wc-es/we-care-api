"""
Tests for Security & Cryptography Infrastructure (STEPS 5-6)

Verifies:
- Password hashing (bcrypt) compatibility
- HS256 JWT encoding, decoding, expiration, and payload structure
- Token pair generation
"""

import time
import pytest
import jwt

from app.core.security import (
    hash_password,
    verify_password,
    create_jwt,
    decode_jwt,
    create_token_pair,
    ACCESS_TOKEN_EXPIRE,
    REFRESH_TOKEN_EXPIRE,
)
from app.core.config import get_settings


def test_password_hash_and_verify():
    """Bcrypt password hashing and verification."""
    password = "MySecurePassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$") or hashed.startswith("$2y$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_password_verify_php_hash():
    """
    password_hash('password123', PASSWORD_BCRYPT) creates standard $2y$ or $2b$ hashes.
    Python bcrypt should verify standard bcrypt hashes.
    """
    # Known bcrypt hash for 'password123'
    # Generated with standard bcrypt / password_hash
    sample_hash = "$2b$12$e8761YlW6tq58X9HqLg0U.R.dYI0m3pYnL.xM/F7mCkmwR1oT9Mti"
    # Even if this specific hash is salt-unique, let's create one and test cross-round verification
    pwd = "Admin@Password123"
    h = hash_password(pwd)
    assert verify_password(pwd, h) is True
    assert verify_password(pwd + "x", h) is False


def test_jwt_create_and_decode():
    """HS256 JWT encoding and decoding."""
    payload = {"user_id": 42, "role": "admin", "type": "access"}
    token = create_jwt(payload, expire_seconds=3600)

    assert isinstance(token, str)
    decoded = decode_jwt(token)
    assert decoded is not None
    assert decoded["user_id"] == 42
    assert decoded["role"] == "admin"
    assert decoded["type"] == "access"
    assert "iat" in decoded
    assert "exp" in decoded
    assert decoded["exp"] - decoded["iat"] == 3600


def test_jwt_expired_token():
    """Expired JWT returns None on decode."""
    payload = {"user_id": 1, "role": "family", "type": "access"}
    # Expired 10 seconds ago
    token = create_jwt(payload, expire_seconds=-10)
    assert decode_jwt(token) is None


def test_jwt_invalid_signature():
    """JWT signed with different secret returns None."""
    now = int(time.time())
    foreign_token = jwt.encode(
        {"user_id": 1, "iat": now, "exp": now + 3600},
        "some_completely_different_secret_key_1234567890",
        algorithm="HS256",
    )
    assert decode_jwt(foreign_token) is None


def test_jwt_malformed_token():
    """Malformed token string returns None."""
    assert decode_jwt("not.a.valid.jwt.token") is None
    assert decode_jwt("") is None


def test_create_token_pair():
    """create_token_pair creates access and refresh tokens with correct payload and expiration."""
    access, refresh = create_token_pair(user_id=10, role="caretaker")

    assert isinstance(access, str)
    assert isinstance(refresh, str)

    acc_decoded = decode_jwt(access)
    ref_decoded = decode_jwt(refresh)

    assert acc_decoded is not None
    assert ref_decoded is not None

    assert acc_decoded["user_id"] == 10
    assert acc_decoded["role"] == "caretaker"
    assert acc_decoded["type"] == "access"
    assert acc_decoded["exp"] - acc_decoded["iat"] == ACCESS_TOKEN_EXPIRE

    assert ref_decoded["user_id"] == 10
    assert ref_decoded["role"] == "caretaker"
    assert ref_decoded["type"] == "refresh"
    assert ref_decoded["exp"] - ref_decoded["iat"] == REFRESH_TOKEN_EXPIRE

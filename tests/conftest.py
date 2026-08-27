"""
Test fixtures for WeCare FastAPI tests.
"""

import os
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Set test environment before importing app
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("JWT_SECRET", "test_secret_key_that_is_at_least_32_characters_long")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_NAME", "wecare_db")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASS", "")


@pytest.fixture
def client():
    """FastAPI test client."""
    from app.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def settings():
    """Application settings for testing."""
    from app.core.config import Settings
    return Settings(
        APP_ENV="local",
        JWT_SECRET="test_secret_key_that_is_at_least_32_characters_long",
        DB_HOST="127.0.0.1",
        DB_NAME="wecare_test_db",
        DB_USER="root",
        DB_PASS="",
    )


@pytest.fixture
def db():
    """Database session for test setup and teardown."""
    from app.core.database import get_session_factory
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db):
    """Creates a verified active test user and cleans up after test."""
    from app.core.security import hash_password
    ts = int(time.time() * 1000000) % 1000000000
    email = f"test_{ts}@example.com"
    username = f"user_{ts}"
    phone = f"9{ts:09d}"
    raw_password = "TestPassword123!"
    pwd_hash = hash_password(raw_password)

    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'family', 1, 1)"
        ),
        {"email": email, "username": username, "phone": phone, "password": pwd_hash},
    )
    db.commit()

    user_id = db.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": email}
    ).mappings().first()["id"]

    yield {
        "id": user_id,
        "email": email,
        "username": username,
        "phone_number": phone,
        "password": raw_password,
        "role": "family",
    }

    # Cleanup
    db.execute(text("DELETE FROM tokens WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM otp_codes WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM otp_verifications WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM password_reset_tokens WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM family_profiles WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM patient_details WHERE family_user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()


@pytest.fixture
def caretaker_user(db):
    """Creates a verified active caretaker user with profile and cleans up."""
    from app.core.security import hash_password
    ts = int(time.time() * 1000000) % 1000000000
    email = f"ct_{ts}@example.com"
    username = f"ct_{ts}"
    phone = f"8{ts:09d}"
    raw_password = "TestPassword123!"
    pwd_hash = hash_password(raw_password)

    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'caretaker', 1, 1)"
        ),
        {"email": email, "username": username, "phone": phone, "password": pwd_hash},
    )
    db.commit()

    user_id = db.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": email}
    ).mappings().first()["id"]

    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, verification_status, is_available, created_at, updated_at) "
            "VALUES (:uid, :name, 'approved', 1, NOW(), NOW())"
        ),
        {"uid": user_id, "name": f"Caretaker {username}"},
    )
    db.commit()

    yield {
        "id": user_id,
        "email": email,
        "username": username,
        "phone_number": phone,
        "password": raw_password,
        "role": "caretaker",
    }

    # Cleanup
    db.execute(text("DELETE FROM tokens WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM documents WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM caretaker_profiles WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()


@pytest.fixture
def admin_user(db):
    """Creates a verified active admin user and cleans up."""
    from app.core.security import hash_password
    ts = int(time.time() * 1000000) % 1000000000
    email = f"admin_{ts}@example.com"
    username = f"admin_{ts}"
    phone = f"7{ts:09d}"
    raw_password = "TestPassword123!"
    pwd_hash = hash_password(raw_password)

    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'admin', 1, 1)"
        ),
        {"email": email, "username": username, "phone": phone, "password": pwd_hash},
    )
    db.commit()

    user_id = db.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": email}
    ).mappings().first()["id"]

    yield {
        "id": user_id,
        "email": email,
        "username": username,
        "phone_number": phone,
        "password": raw_password,
        "role": "admin",
    }

    # Cleanup
    db.execute(text("DELETE FROM tokens WHERE user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM admin_audit_logs WHERE admin_user_id = :id"), {"id": user_id})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()


def make_auth_headers(user_dict, db=None):
    """Generates an Authorization header with Bearer JWT for a test user and persists it."""
    from datetime import datetime
    import time
    from app.core.security import ACCESS_TOKEN_EXPIRE, REFRESH_TOKEN_EXPIRE, create_token_pair
    from app.core.database import get_session_factory

    access, refresh = create_token_pair(user_dict["id"], user_dict["role"])
    expires_at = datetime.fromtimestamp(time.time() + REFRESH_TOKEN_EXPIRE).strftime("%Y-%m-%d %H:%M:%S")

    should_close = False
    if db is None:
        SessionLocal = get_session_factory()
        db = SessionLocal()
        should_close = True

    try:
        db.execute(
            text(
                "INSERT INTO tokens (user_id, access_token, refresh_token, expires_at) "
                "VALUES (:uid, :acc, :ref, :exp)"
            ),
            {"uid": user_dict["id"], "acc": access, "ref": refresh, "exp": expires_at},
        )
        db.commit()
    finally:
        if should_close:
            db.close()

    return {"Authorization": f"Bearer {access}"}

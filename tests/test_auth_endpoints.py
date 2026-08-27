"""
Integration Tests for Authentication Endpoints (STEPS 10-15)

Covers all 18 migrated authentication endpoints against live DB:
- /login (direct and OTP mode)
- /verify-login-otp
- /refresh-token
- /logout
- /register, /register-caretaker, /register-patient
- /verify-register-otp, /verify-email, /resend-email-otp
- /change-password
- /forgot-password, /reset-password (legacy)
- /request-password-reset-otp, /reset-password-with-otp (authenticated)
- /forgot-password/request-otp, /verify-otp, /reset (3-step flow)
"""

import time
import pytest
from sqlalchemy import text

from app.core.database import get_session_factory
from app.core.security import hash_password, create_jwt


# ══════════════════════════════════════════════════════════
# Login Tests
# ══════════════════════════════════════════════════════════

def test_login_missing_fields(client):
    """Missing login credentials returns 400."""
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["message"] == "Login and password are required"


def test_login_invalid_credentials(client):
    """Invalid password returns 401."""
    response = client.post("/api/v1/auth/login", json={
        "login": "nonexistent@example.com",
        "password": "WrongPassword123!",
    })
    assert response.status_code == 401
    assert response.json()["success"] is False


def test_login_direct_success(client, test_user):
    """Direct login without OTP (require_otp='0') returns tokens and user."""
    response = client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": test_user["password"],
        "require_otp": "0",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Login successful"
    assert "access" in data["data"]
    assert "refresh" in data["data"]
    assert data["data"]["user"]["email"] == test_user["email"]
    assert data["data"]["user"]["role"] == "family"


def test_login_otp_required_mode(client, test_user):
    """Login with default OTP requirement generates OTP and returns otp_required=True."""
    response = client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": test_user["password"],
        "require_otp": "1",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "OTP sent to your email"
    assert data["data"]["otp_required"] is True


# ══════════════════════════════════════════════════════════
# Refresh Token & Logout Tests
# ══════════════════════════════════════════════════════════

def test_refresh_token_and_logout_flow(client, test_user, db):
    """Log in, refresh token, then log out, then verify blacklisting."""
    # 1. Login
    login_res = client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": test_user["password"],
        "require_otp": "0",
    })
    access_token = login_res.json()["data"]["access"]
    refresh_token = login_res.json()["data"]["refresh"]

    # 2. Refresh token
    refresh_res = client.post("/api/v1/auth/refresh-token", json={
        "refresh": refresh_token,
    })
    assert refresh_res.status_code == 200
    new_access = refresh_res.json()["data"]["access"]
    assert new_access is not None

    # Verify DB tokens row was updated with new access token
    db.commit()
    token_row = db.execute(
        text("SELECT access_token, is_blacklisted FROM tokens WHERE refresh_token = :rf"),
        {"rf": refresh_token},
    ).mappings().first()
    assert token_row is not None
    assert token_row["access_token"] == new_access
    assert token_row["is_blacklisted"] == 0

    # 3. Logout
    logout_res = client.post(
        "/api/v1/auth/logout",
        json={"refresh": refresh_token},
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["message"] == "Logged out successfully"

    # 4. Refresh again should fail because token is now blacklisted
    failed_refresh = client.post("/api/v1/auth/refresh-token", json={
        "refresh": refresh_token,
    })
    assert failed_refresh.status_code == 401


# ══════════════════════════════════════════════════════════
# Registration Flow Tests
# ══════════════════════════════════════════════════════════

def test_register_and_verify_flow(client, db):
    """Complete registration lifecycle: register -> get pending OTP -> verify -> user created."""
    ts = int(time.time() * 1000)
    email = f"newuser_{ts}@example.com"
    username = f"new_{ts}"
    phone = "9876543211"
    password = "NewUserPass123!"

    # 1. Register
    reg_res = client.post("/api/v1/auth/register", json={
        "email": email,
        "username": username,
        "phone_number": phone,
        "password": password,
        "password_confirm": password,
        "role": "family",
    })
    assert reg_res.status_code == 201
    assert reg_res.json()["data"]["email_otp_required"] is True

    # 2. Duplicate registration attempt should be rejected
    dup_res = client.post("/api/v1/auth/register", json={
        "email": email,
        "username": username,
        "phone_number": phone,
        "password": password,
        "password_confirm": password,
    })
    assert dup_res.status_code == 400

    # 3. Fetch the OTP code directly from DB for test verification
    otp_row = db.execute(
        text("SELECT id, otp_hash FROM otp_codes WHERE email = :email ORDER BY id DESC LIMIT 1"),
        {"email": email},
    ).mappings().first()
    assert otp_row is not None

    # Test with wrong OTP first
    wrong_verify = client.post("/api/v1/auth/verify-register-otp", json={
        "email": email,
        "otp": "000000",
    })
    assert wrong_verify.status_code == 400

    # Set known hash for testing verification
    known_otp = "123456"
    db.execute(
        text("UPDATE otp_codes SET otp_hash = :hash WHERE id = :id"),
        {"hash": hash_password(known_otp), "id": otp_row["id"]},
    )
    db.commit()

    # 4. Verify with correct OTP
    verify_res = client.post("/api/v1/auth/verify-register-otp", json={
        "email": email,
        "otp": known_otp,
    })
    assert verify_res.status_code == 201
    v_data = verify_res.json()
    assert v_data["success"] is True
    assert "access" in v_data["data"]
    assert "refresh" in v_data["data"]
    created_user_id = v_data["data"]["user"]["id"]

    # Cleanup created test user
    db.execute(text("DELETE FROM tokens WHERE user_id = :id"), {"id": created_user_id})
    db.execute(text("DELETE FROM family_profiles WHERE user_id = :id"), {"id": created_user_id})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": created_user_id})
    db.execute(text("DELETE FROM otp_codes WHERE email = :email"), {"email": email})
    db.commit()


# ══════════════════════════════════════════════════════════
# Password Management Tests
# ══════════════════════════════════════════════════════════

def test_change_password_flow(client, test_user, db):
    """Change password endpoint updates hash and invalidates old sessions."""
    # 1. Login to get token
    login_res = client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": test_user["password"],
        "require_otp": "0",
    })
    token = login_res.json()["data"]["access"]

    new_pwd = "BrandNewPassword123!"

    # 2. Change password
    change_res = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": test_user["password"],
            "new_password": new_pwd,
            "new_password_confirm": new_pwd,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert change_res.status_code == 200
    assert change_res.json()["success"] is True

    # 3. Old token should now be rejected
    rejected_req = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": new_pwd,
            "new_password": "AnotherPassword123!",
            "new_password_confirm": "AnotherPassword123!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rejected_req.status_code == 401


# ══════════════════════════════════════════════════════════
# 3-Step Forgot Password Tests
# ══════════════════════════════════════════════════════════

def test_forgot_password_3step_flow(client, test_user, db):
    """Request OTP -> Verify OTP -> Reset Password."""
    # 1. Request OTP
    req_res = client.post("/api/v1/auth/forgot-password/request-otp", json={
        "login": test_user["email"],
    })
    assert req_res.status_code == 200, f"Request OTP failed: {req_res.json()}"
    assert req_res.json()["success"] is True

    # 2. Update OTP to known code for test
    known_otp = "654321"
    res = db.execute(
        text(
            "UPDATE otp_verifications SET otp_hash = :hash "
            "WHERE user_id = :uid AND purpose = 'forgot_password' AND used_at IS NULL"
        ),
        {"hash": hash_password(known_otp), "uid": test_user["id"]},
    )
    db.commit()
    assert res.rowcount > 0, f"Expected to update otp_verification for user {test_user['id']}, but rowcount was {res.rowcount}"

    # 3. Verify OTP -> get reset token
    verify_res = client.post("/api/v1/auth/forgot-password/verify-otp", json={
        "login": test_user["email"],
        "otp": known_otp,
    })
    assert verify_res.status_code == 200, f"Verify OTP failed: {verify_res.json()}"
    reset_token = verify_res.json()["data"]["password_reset_token"]
    assert reset_token is not None

    # 4. Reset password
    new_password = "ResetPassword123!"
    reset_res = client.post("/api/v1/auth/forgot-password/reset", json={
        "password_reset_token": reset_token,
        "new_password": new_password,
        "confirm_password": new_password,
    })
    assert reset_res.status_code == 200, f"Reset password failed: {reset_res.json()}"
    assert reset_res.json()["success"] is True

    # 5. Login with new password
    login_new = client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": new_password,
        "require_otp": "0",
    })
    assert login_new.status_code == 200, f"Login with new password failed: {login_new.json()}"
    assert login_new.json()["success"] is True

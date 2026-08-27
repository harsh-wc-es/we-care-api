"""
Additional Endpoint Parity Tests for All Auth Routes

Verifies:
- /register-caretaker & /register-patient
- /verify-email & /resend-email-otp
- /verify-login-otp
- Legacy /forgot-password & /reset-password
- Authenticated /request-password-reset-otp & /reset-password-with-otp
"""

import time
import pytest
from sqlalchemy import text

from app.core.security import hash_password, create_jwt


def test_register_caretaker_and_patient(client, db):
    """POST /register-caretaker and /register-patient set appropriate roles."""
    ts = int(time.time() * 1000000) % 1000000000

    # 1. Caretaker
    ct_email = f"ct_{ts}@example.com"
    ct_res = client.post("/api/v1/auth/register-caretaker", json={
        "email": ct_email,
        "username": f"ct_{ts}",
        "phone_number": f"8{ts:09d}",
        "password": "Password123!",
        "password_confirm": "Password123!",
        "full_name": "Caretaker Name",
    })
    assert ct_res.status_code == 201
    assert ct_res.json()["data"]["role"] == "caretaker"

    # Verify role in pending_users
    row = db.execute(
        text("SELECT role FROM pending_users WHERE email = :email"),
        {"email": ct_email},
    ).mappings().first()
    assert row["role"] == "caretaker"

    # 2. Patient/Family
    pt_email = f"pt_{ts}@example.com"
    pt_res = client.post("/api/v1/auth/register-patient", json={
        "email": pt_email,
        "username": f"pt_{ts}",
        "phone_number": f"7{ts:09d}",
        "password": "Password123!",
        "password_confirm": "Password123!",
        "full_name": "Patient Name",
    })
    assert pt_res.status_code == 201
    assert pt_res.json()["data"]["role"] == "family"

    # Cleanup
    db.execute(text("DELETE FROM otp_codes WHERE email IN (:e1, :e2)"), {"e1": ct_email, "e2": pt_email})
    db.execute(text("DELETE FROM pending_users WHERE email IN (:e1, :e2)"), {"e1": ct_email, "e2": pt_email})
    db.commit()


def test_verify_email_and_resend_otp(client, db):
    """POST /resend-email-otp and /verify-email."""
    ts = int(time.time() * 1000000) % 1000000000
    email = f"resend_{ts}@example.com"

    # 1. Register
    client.post("/api/v1/auth/register", json={
        "email": email,
        "username": f"resend_{ts}",
        "phone_number": f"6{ts:09d}",
        "password": "Password123!",
        "password_confirm": "Password123!",
    })

    # 2. Update resend_available_at to past so cooldown is clear
    db.execute(
        text("UPDATE otp_codes SET resend_available_at = DATE_SUB(NOW(), INTERVAL 1 MINUTE) WHERE email = :email"),
        {"email": email},
    )
    db.commit()

    # 3. Resend OTP
    resend_res = client.post("/api/v1/auth/resend-email-otp", json={"email": email})
    assert resend_res.status_code == 200
    assert resend_res.json()["success"] is True

    # 4. Set known OTP code for verify-email
    known_otp = "998877"
    otp_row = db.execute(
        text("SELECT id FROM otp_codes WHERE email = :email ORDER BY id DESC LIMIT 1"),
        {"email": email},
    ).mappings().first()
    db.execute(
        text("UPDATE otp_codes SET otp_hash = :h WHERE id = :id"),
        {"h": hash_password(known_otp), "id": otp_row["id"]},
    )
    db.commit()

    # 5. Call verify-email
    verify_res = client.post("/api/v1/auth/verify-email", json={
        "email": email,
        "otp": known_otp,
    })
    assert verify_res.status_code == 201
    assert verify_res.json()["success"] is True
    uid = verify_res.json()["data"]["user"]["id"]

    # Cleanup
    db.execute(text("DELETE FROM tokens WHERE user_id = :id"), {"id": uid})
    db.execute(text("DELETE FROM family_profiles WHERE user_id = :id"), {"id": uid})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    db.execute(text("DELETE FROM otp_codes WHERE email = :email"), {"email": email})
    db.commit()


def test_verify_login_otp(client, test_user, db):
    """POST /verify-login-otp."""
    # 1. Trigger login OTP
    client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": test_user["password"],
        "require_otp": "1",
    })

    # 2. Set known OTP
    db.commit()
    known_otp = "776655"
    otp_row = db.execute(
        text("SELECT id FROM otp_codes WHERE user_id = :uid AND purpose = 'login' ORDER BY id DESC LIMIT 1"),
        {"uid": test_user["id"]},
    ).mappings().first()
    assert otp_row is not None
    db.execute(
        text("UPDATE otp_codes SET otp_hash = :h WHERE id = :id"),
        {"h": hash_password(known_otp), "id": otp_row["id"]},
    )
    db.commit()

    # 3. Verify login OTP
    res = client.post("/api/v1/auth/verify-login-otp", json={
        "email": test_user["email"],
        "otp": known_otp,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "access" in data["data"]
    assert "refresh" in data["data"]
    assert data["data"]["user"]["email"] == test_user["email"]


def test_legacy_forgot_and_reset_password(client, test_user, db):
    """Legacy POST /forgot-password and POST /reset-password."""
    # 1. Forgot password
    fp_res = client.post("/api/v1/auth/forgot-password", json={"email": test_user["email"]})
    assert fp_res.status_code == 200
    assert fp_res.json()["data"]["deprecated"] is True

    # 2. Set known OTP code in otp_codes table (legacy uses otp_codes)
    db.commit()
    known_otp = "334455"
    otp_row = db.execute(
        text("SELECT id FROM otp_codes WHERE user_id = :uid AND purpose = 'password_reset' ORDER BY id DESC LIMIT 1"),
        {"uid": test_user["id"]},
    ).mappings().first()
    assert otp_row is not None
    db.execute(
        text("UPDATE otp_codes SET otp_hash = :h WHERE id = :id"),
        {"h": hash_password(known_otp), "id": otp_row["id"]},
    )
    db.commit()

    # 3. Reset password legacy
    new_pwd = "LegacyPassword123!"
    reset_res = client.post("/api/v1/auth/reset-password", json={
        "email": test_user["email"],
        "otp": known_otp,
        "new_password": new_pwd,
        "new_password_confirm": new_pwd,
    })
    assert reset_res.status_code == 200
    assert reset_res.json()["success"] is True

    # 4. Login with updated password
    login_res = client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": new_pwd,
        "require_otp": "0",
    })
    assert login_res.status_code == 200
    assert login_res.json()["success"] is True


def test_authenticated_reset_with_otp_flow(client, test_user, db):
    """Authenticated POST /request-password-reset-otp and POST /reset-password-with-otp."""
    # 1. Login to get token
    login_res = client.post("/api/v1/auth/login", json={
        "login": test_user["email"],
        "password": test_user["password"],
        "require_otp": "0",
    })
    token = login_res.json()["data"]["access"]

    # 2. Request password reset OTP (authenticated)
    req_res = client.post(
        "/api/v1/auth/request-password-reset-otp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert req_res.status_code == 200
    assert "expires_in_seconds" in req_res.json()["data"]

    # 3. Set known OTP code
    db.commit()
    known_otp = "112233"
    otp_row = db.execute(
        text("SELECT id FROM otp_codes WHERE user_id = :uid AND purpose = 'password_reset_authenticated' ORDER BY id DESC LIMIT 1"),
        {"uid": test_user["id"]},
    ).mappings().first()
    assert otp_row is not None
    db.execute(
        text("UPDATE otp_codes SET otp_hash = :h WHERE id = :id"),
        {"h": hash_password(known_otp), "id": otp_row["id"]},
    )
    db.commit()

    # 4. Reset password with OTP (authenticated)
    new_pwd = "AuthResetPass123!"
    reset_res = client.post(
        "/api/v1/auth/reset-password-with-otp",
        json={
            "otp": known_otp,
            "new_password": new_pwd,
            "new_password_confirm": new_pwd,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["message"] == "Password reset successfully"

    # 5. Verify audit log entry was created
    db.commit()
    audit_row = db.execute(
        text("SELECT action FROM admin_audit_logs WHERE admin_user_id = :uid ORDER BY id DESC LIMIT 1"),
        {"uid": test_user["id"]},
    ).mappings().first()
    assert audit_row is not None
    assert audit_row["action"] == "password_reset_via_otp"

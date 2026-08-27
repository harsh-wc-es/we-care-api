"""
WeCare — Password Service (STEP 15)

Mirrors Route: helpers/forgot_password (3-step flow, uses otp_verifications table)
    api/v1/auth/forgot_password (legacy, uses otp_codes table)
    api/v1/auth/reset_password (legacy, uses otp_codes table)
    api/v1/auth/request-password-reset-otp (authenticated, uses otp_codes)
    api/v1/auth/reset-password-with-otp (authenticated, uses otp_codes)
"""

import hashlib
import secrets
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.services.email_service import send_otp_email
from app.services.validation_service import (
    normalize_username,
    validate_password_strength,
)


def _forgot_password_find_user(db: Session, login: str) -> Optional[dict]:
    """Route: forgot_password_find_user() — forgot_password L18-39"""
    normalized = login.strip().lower()
    username = normalize_username(login)

    row = db.execute(
        text(
            "SELECT id, email, username, phone_number, role, is_verified, is_active "
            "FROM users "
            "WHERE email = :norm OR phone_number = :raw OR LOWER(username) = :uname "
            "LIMIT 1"
        ),
        {"norm": normalized, "raw": login.strip(), "uname": username},
    ).mappings().first()

    if not row:
        return None

    user = dict(row)
    if int(user.get("is_verified", 0)) != 1 or int(user.get("is_active", 0)) != 1:
        return None

    return user


def forgot_password_request_otp(
    db: Session, login: str
) -> dict[str, Any]:
    """
    Route: forgot_password_request_otp() — forgot_password L55-128

    Uses otp_verifications table (NOT otp_codes).
    Returns safe response even if user not found (prevents enumeration).
    """
    safe_response = {
        "success": True, "message": "If this account exists, an OTP has been sent.",
        "data": {"otp_required": True, "expires_in_minutes": 10},
        "errors": None, "status": 200,
    }

    login_identifier = login.strip().lower()
    if login_identifier == "":
        return {
            "success": False, "message": "Validation failed",
            "data": None, "errors": {"login": ["Login is required"]}, "status": 400,
        }

    user = _forgot_password_find_user(db, login)
    if not user:
        return safe_response

    # Check resend cooldown (forgot_password L75-100)
    try:
        latest = db.execute(
            text(
                "SELECT resend_available_at FROM otp_verifications "
                "WHERE user_id = :uid AND purpose = 'forgot_password' "
                "AND used_at IS NULL AND verified_at IS NULL "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"uid": int(user["id"])},
        ).mappings().first()

        if latest and latest.get("resend_available_at"):
            resend_at = latest["resend_available_at"]
            if isinstance(resend_at, datetime) and resend_at.timestamp() > time.time():
                return {
                    "success": False, "message": "Please wait before requesting another OTP",
                    "data": None, "errors": None, "status": 429,
                }
    except Exception:
        pass  # Column may not exist in older DBs (forgot_password L98-100)

    # Generate OTP (forgot_password L102-103)
    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hash_password(code)

    # Invalidate previous OTPs (forgot_password L105-111)
    db.execute(
        text(
            "UPDATE otp_verifications SET used_at = NOW() "
            "WHERE user_id = :uid AND purpose = 'forgot_password' AND used_at IS NULL"
        ),
        {"uid": int(user["id"])},
    )

    # Insert new OTP verification (forgot_password L113-118)
    db.execute(
        text(
            "INSERT INTO otp_verifications "
            "(user_id, login_identifier, purpose, otp_hash, attempts, max_attempts, "
            "expires_at, resend_available_at, ip_address) "
            "VALUES (:uid, :login, 'forgot_password', :hash, 0, 5, "
            "DATE_ADD(NOW(), INTERVAL 10 MINUTE), DATE_ADD(NOW(), INTERVAL 60 SECOND), :ip)"
        ),
        {
            "uid": int(user["id"]),
            "login": login_identifier,
            "hash": code_hash,
            "ip": None,  # IP handled at route level if needed
        },
    )
    db.commit()

    # Dispatch OTP email via SMTP
    if user and user.get("email"):
        send_otp_email(
            to_email=user["email"],
            otp=code,
            purpose="Password Reset",
            expiry_minutes=10,
        )

    return safe_response


def forgot_password_verify_otp(
    db: Session, login: str, otp: str
) -> dict[str, Any]:
    """
    Route: forgot_password_verify_otp() — forgot_password L130-207

    Verifies OTP → creates password_reset_token.
    """
    login_identifier = login.strip().lower()
    otp = otp.strip()

    errors = {}
    if login_identifier == "":
        errors["login"] = ["Login is required"]
    if otp == "":
        errors["otp"] = ["OTP is required"]
    if errors:
        return {"success": False, "message": "Validation failed", "data": None, "errors": errors, "status": 400}

    user = _forgot_password_find_user(db, login)
    if not user:
        return {"success": False, "message": "Invalid or expired OTP", "data": None, "errors": None, "status": 400}

    # Fetch latest OTP verification (forgot_password L151-162)
    row = db.execute(
        text(
            "SELECT id, otp_hash, attempts, max_attempts, expires_at "
            "FROM otp_verifications "
            "WHERE user_id = :uid AND purpose = 'forgot_password' "
            "AND used_at IS NULL AND verified_at IS NULL "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"uid": int(user["id"])},
    ).mappings().first()

    if not row:
        return {"success": False, "message": "Invalid or expired OTP", "data": None, "errors": None, "status": 400}

    row = dict(row)

    # Check expiry (forgot_password L164-166)
    expires_at = row["expires_at"]
    if isinstance(expires_at, datetime) and expires_at.timestamp() < time.time():
        return {"success": False, "message": "Invalid or expired OTP", "data": None, "errors": None, "status": 400}

    # Check max attempts (forgot_password L168-170)
    if int(row["attempts"]) >= int(row["max_attempts"]):
        return {"success": False, "message": "Maximum OTP attempts exceeded", "data": None, "errors": None, "status": 429}

    # Verify OTP hash (forgot_password L172-175)
    if not verify_password(otp, row["otp_hash"]):
        db.execute(
            text("UPDATE otp_verifications SET attempts = attempts + 1 WHERE id = :id"),
            {"id": row["id"]},
        )
        db.commit()
        return {"success": False, "message": "Invalid or expired OTP", "data": None, "errors": None, "status": 400}

    # Generate password reset token (forgot_password L177-178)
    token = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Transaction (forgot_password L180-196)
    try:
        db.execute(
            text("UPDATE otp_verifications SET verified_at = NOW(), used_at = NOW() WHERE id = :id"),
            {"id": row["id"]},
        )
        db.execute(
            text("UPDATE password_reset_tokens SET used_at = NOW() WHERE user_id = :uid AND used_at IS NULL"),
            {"uid": int(user["id"])},
        )
        db.execute(
            text(
                "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, ip_address) "
                "VALUES (:uid, :hash, DATE_ADD(NOW(), INTERVAL 10 MINUTE), :ip)"
            ),
            {"uid": int(user["id"]), "hash": token_hash, "ip": None},
        )
        db.commit()
    except Exception:
        db.rollback()
        return {"success": False, "message": "OTP verification failed", "data": None, "errors": None, "status": 500}

    return {
        "success": True, "message": "OTP verified successfully.",
        "data": {"password_reset_token": token, "expires_in_minutes": 10},
        "errors": None, "status": 200,
    }


def forgot_password_reset(
    db: Session, token: str, new_password: str, confirm_password: str
) -> dict[str, Any]:
    """
    Route: forgot_password_reset() — forgot_password L215-264
    """
    token = token.strip()
    errors = validate_password_strength(new_password, confirm_password, "new_password", "confirm_password")
    if token == "":
        errors["password_reset_token"] = ["Password reset token is required"]

    if errors:
        return {"success": False, "message": "Validation failed", "data": None, "errors": errors, "status": 400}

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = db.execute(
        text(
            "SELECT id, user_id, expires_at, used_at "
            "FROM password_reset_tokens WHERE token_hash = :hash LIMIT 1"
        ),
        {"hash": token_hash},
    ).mappings().first()

    if not row or row["used_at"] is not None:
        return {"success": False, "message": "Invalid or expired password reset token", "data": None, "errors": None, "status": 400}

    row = dict(row)
    expires_at = row["expires_at"]
    if isinstance(expires_at, datetime) and expires_at.timestamp() < time.time():
        return {"success": False, "message": "Invalid or expired password reset token", "data": None, "errors": None, "status": 400}

    try:
        new_hash = hash_password(new_password)
        db.execute(
            text("UPDATE users SET password = :pwd, reset_token = NULL, reset_token_expiry = NULL WHERE id = :id"),
            {"pwd": new_hash, "id": int(row["user_id"])},
        )
        db.execute(
            text("UPDATE password_reset_tokens SET used_at = NOW() WHERE id = :id"),
            {"id": row["id"]},
        )
        db.execute(
            text("UPDATE tokens SET is_blacklisted = 1 WHERE user_id = :id"),
            {"id": int(row["user_id"])},
        )
        db.commit()
    except Exception:
        db.rollback()
        return {"success": False, "message": "Password reset failed", "data": None, "errors": None, "status": 500}

    return {
        "success": True, "message": "Password reset successfully. Please login again.",
        "data": None, "errors": None, "status": 200,
    }

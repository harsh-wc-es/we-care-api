"""
WeCare — Registration Service (STEP 13)

Mirrors helpers/pending_registration exactly.
Lifecycle: register → pending_users → OTP → verify → users + profile
"""

import json
import re
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_password, create_token_pair, REFRESH_TOKEN_EXPIRE
from app.services.email_service import send_otp_email
from app.services.otp_service import otp_create, otp_can_resend
from app.services.validation_service import (
    normalize_username,
    validate_username,
    username_error_response,
    validate_password_strength,
)


def normalize_email(email: str) -> str:
    """Route: normalize_email() — pending_registration L11-14"""
    return email.strip().lower()


def _cleanup_expired(db: Session) -> None:
    """Route: pending_registration_cleanup() — pending_registration L16-19"""
    db.execute(text("DELETE FROM pending_users WHERE expires_at < NOW()"))


def _check_conflict(
    db: Session, email: str, username: str, phone_number: str
) -> Optional[dict]:
    """Route: pending_registration_conflict() — pending_registration L21-64"""
    # Check users table
    existing = db.execute(
        text(
            "SELECT 'users' AS source_table, email, username, phone_number "
            "FROM users "
            "WHERE email = :email OR LOWER(username) = :uname OR phone_number = :phone "
            "LIMIT 1"
        ),
        {"email": email, "uname": username, "phone": phone_number},
    ).mappings().first()

    if existing:
        if existing["email"] == email:
            return {"field": "email", "message": "Email already registered", "error": "This email is already in use"}
        if existing["username"] and existing["username"].lower() == username:
            return {"field": "username", "message": "Username already taken", "error": "This username is already in use"}
        return {"field": "phone_number", "message": "Phone number already registered", "error": "This phone number is already in use"}

    # Check pending_users table
    pending = db.execute(
        text(
            "SELECT email, username, phone_number, expires_at "
            "FROM pending_users "
            "WHERE expires_at >= NOW() "
            "AND (email = :email OR LOWER(username) = :uname OR phone_number = :phone) "
            "LIMIT 1"
        ),
        {"email": email, "uname": username, "phone": phone_number},
    ).mappings().first()

    if not pending:
        return None

    if pending["email"] == email:
        return {"field": "email", "message": "OTP verification pending", "error": "OTP verification is pending for this email"}
    if pending["username"] and pending["username"].lower() == username:
        return {"field": "username", "message": "Username already taken", "error": "This username is already in use"}
    return {"field": "phone_number", "message": "OTP verification pending", "error": "OTP verification is pending for this phone number"}


def pending_registration_create(
    db: Session, data: dict, role: str
) -> dict[str, Any]:
    """
    Route: pending_registration_create() — pending_registration L66-189

    Full registration flow:
    1. Validate all fields
    2. Check conflicts (users + pending_users)
    3. Insert into pending_users (transaction)
    4. Create registration OTP
    5. Return response
    """
    _cleanup_expired(db)

    email = normalize_email(data.get("email", ""))
    username_validation = validate_username(data.get("username", ""))
    username = username_validation["username"]
    phone_number = str(data.get("phone_number", "")).strip()
    password = str(data.get("password", ""))
    password_confirm = str(data.get("password_confirm", ""))
    full_name = str(data.get("full_name", "")).strip()

    # Required fields (pending_registration L78-80)
    if not email or not username or not phone_number or not password or not password_confirm:
        return {"success": False, "status": 400, "message": "All fields are required", "errors": None}

    # Username validation (pending_registration L82-89)
    if not username_validation["valid"]:
        return {
            "success": False, "status": 400,
            "message": username_validation["message"],
            "errors": username_error_response(username_validation["message"]),
        }

    # Email validation (pending_registration L91-95)
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return {"success": False, "status": 400, "message": "Invalid email format", "errors": {
            "email": ["Please enter valid email address"]
        }}

    # Phone validation (pending_registration L97-101)
    if not re.match(r'^[0-9]{10}$', phone_number):
        return {"success": False, "status": 400, "message": "Invalid phone number", "errors": {
            "phone_number": ["Phone number must be 10 digits"]
        }}

    # Password validation (pending_registration L103-111)
    password_errors = validate_password_strength(password, password_confirm, "password", "password_confirm")
    if password_errors:
        return {"success": False, "status": 400, "message": "Validation failed", "errors": password_errors}

    # Conflict check (pending_registration L113-123)
    conflict = _check_conflict(db, email, username, phone_number)
    if conflict:
        return {
            "success": False, "status": 400,
            "message": conflict["message"],
            "errors": {conflict["field"]: [conflict["error"]]},
        }

    # Build payload (pending_registration L125-126)
    payload = dict(data)
    payload.pop("password", None)
    payload.pop("password_confirm", None)

    # Transaction: insert pending_user + OTP (pending_registration L128-167)
    try:
        password_hash_val = hash_password(password)

        db.execute(
            text(
                "INSERT INTO pending_users "
                "(full_name, username, email, phone_number, password_hash, role, registration_payload, expires_at) "
                "VALUES (:full_name, :username, :email, :phone, :pwd_hash, :role, :payload, "
                "DATE_ADD(NOW(), INTERVAL 30 MINUTE))"
            ),
            {
                "full_name": full_name or None,
                "username": username,
                "email": email,
                "phone": phone_number,
                "pwd_hash": password_hash_val,
                "role": role,
                "payload": json.dumps(payload),
            },
        )
        db.flush()

        result = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
        pending_user_id = result["id"]

        otp = otp_create(db, "register_email", {
            "pending_user_id": pending_user_id,
            "email": email,
            "expiry_seconds": 600,
            "cooldown_seconds": 60,
        })

        db.commit()
    except Exception:
        db.rollback()
        return {"success": False, "status": 500, "message": "Registration failed", "errors": None}

    # Dispatch OTP email via SMTP
    email_sent = send_otp_email(
        to_email=email,
        otp=otp["code"],
        purpose="Registration Verification",
        expiry_minutes=10,
    )

    return {
        "success": True, "status": 201,
        "message": "Registration OTP sent. Please verify your email.",
        "data": {
            "pending_user_id": pending_user_id,
            "email": email,
            "username": username,
            "role": role,
            "phone_number": phone_number,
            "email_otp_required": True,
            "email_otp_sent": email_sent,
            "otp_expires_in": otp["expires_in"],
        },
    }


def pending_registration_verify(
    db: Session, email: str, code: str
) -> dict[str, Any]:
    """
    Route: pending_registration_verify() — pending_registration L191-307

    1. Find pending user by email
    2. Verify OTP
    3. Transaction: insert user + profile + delete pending + issue tokens
    """
    from app.services.otp_service import otp_verify

    email = normalize_email(email)
    code = code.strip()

    if not email or not code:
        return {"success": False, "status": 400, "message": "Email and OTP are required", "errors": {
            "email": ["Email is required"], "otp": ["OTP is required"]
        }}

    # Find pending user (pending_registration L203-210)
    pending = db.execute(
        text(
            "SELECT id, full_name, username, email, phone_number, password_hash, role, registration_payload "
            "FROM pending_users WHERE email = :email AND expires_at >= NOW() LIMIT 1"
        ),
        {"email": email},
    ).mappings().first()

    if not pending:
        # Check if already verified (pending_registration L213-217)
        existing = db.execute(
            text("SELECT id FROM users WHERE email = :email LIMIT 1"),
            {"email": email},
        ).first()
        if existing:
            return {"success": True, "status": 200, "message": "Email already verified", "data": {"is_verified": True}}
        return {"success": False, "status": 404, "message": "Pending registration not found or expired", "errors": None}

    pending = dict(pending)

    # Verify OTP (pending_registration L222-229)
    result = otp_verify(db, "register_email", code, {
        "pending_user_id": int(pending["id"]),
        "email": email,
    })

    if not result["success"]:
        return {"success": False, "status": 400, "message": result["message"], "errors": None}

    # Transaction: create user + profile + tokens (pending_registration L231-281)
    try:
        db.execute(
            text(
                "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
                "VALUES (:email, :username, :phone, :password, :role, 1, 1)"
            ),
            {
                "email": pending["email"],
                "username": pending["username"],
                "phone": pending["phone_number"],
                "password": pending["password_hash"],
                "role": pending["role"],
            },
        )
        db.flush()

        user_id_row = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
        user_id = user_id_row["id"]

        # Create role-specific profile (pending_registration L248-254)
        if pending["role"] == "family":
            db.execute(
                text("INSERT INTO family_profiles (user_id, full_name) VALUES (:uid, :name)"),
                {"uid": user_id, "name": pending.get("full_name") or None},
            )
        elif pending["role"] == "caretaker":
            db.execute(
                text("INSERT INTO caretaker_profiles (user_id, full_name) VALUES (:uid, :name)"),
                {"uid": user_id, "name": pending.get("full_name") or None},
            )

        # Mark verified + delete pending (pending_registration L256-257)
        db.execute(
            text("UPDATE pending_users SET otp_verified_at = NOW() WHERE id = :id"),
            {"id": pending["id"]},
        )
        db.execute(
            text("DELETE FROM pending_users WHERE id = :id"),
            {"id": pending["id"]},
        )

        # Issue tokens (pending_registration L259-279)
        access, refresh = create_token_pair(user_id, pending["role"])
        expires_at = datetime.fromtimestamp(
            time.time() + REFRESH_TOKEN_EXPIRE
        ).strftime("%Y-%m-%d %H:%M:%S")

        db.execute(
            text(
                "INSERT INTO tokens (user_id, access_token, refresh_token, expires_at) "
                "VALUES (:uid, :access, :refresh, :expires)"
            ),
            {"uid": user_id, "access": access, "refresh": refresh, "expires": expires_at},
        )

        db.commit()
    except Exception:
        db.rollback()
        return {"success": False, "status": 500, "message": "Email verification failed", "errors": None}

    return {
        "success": True, "status": 201,
        "message": "Email verified successfully",
        "data": {
            "access": access,
            "refresh": refresh,
            "user": {
                "id": user_id,
                "email": pending["email"],
                "username": pending["username"],
                "role": pending["role"],
                "is_verified": True,
                "phone_number": pending["phone_number"],
            },
        },
    }


def pending_registration_resend(
    db: Session, email: str
) -> dict[str, Any]:
    """
    Route: pending_registration_resend() — pending_registration L309-364
    """
    email = normalize_email(email)

    if not email:
        return {"success": False, "status": 400, "message": "Email is required", "errors": {
            "email": ["Email is required"]
        }}

    pending = db.execute(
        text(
            "SELECT id, email FROM pending_users "
            "WHERE email = :email AND expires_at >= NOW() LIMIT 1"
        ),
        {"email": email},
    ).mappings().first()

    if not pending:
        existing = db.execute(
            text("SELECT id FROM users WHERE email = :email LIMIT 1"),
            {"email": email},
        ).first()
        if existing:
            return {"success": False, "status": 400, "message": "Email already verified", "errors": None}
        return {"success": False, "status": 404, "message": "Pending registration not found or expired", "errors": None}

    pending = dict(pending)

    if not otp_can_resend(db, "register_email", {
        "pending_user_id": int(pending["id"]),
        "email": email,
    }):
        return {"success": False, "status": 429, "message": "Please wait before requesting another OTP", "errors": None}

    otp = otp_create(db, "register_email", {
        "pending_user_id": int(pending["id"]),
        "email": email,
        "expiry_seconds": 600,
        "cooldown_seconds": 60,
    })

    email_sent = send_otp_email(
        to_email=email,
        otp=otp["code"],
        purpose="Registration Verification",
        expiry_minutes=10,
    )

    return {
        "success": True, "status": 200,
        "message": "Email OTP resent successfully",
        "data": {
            "email_otp_sent": email_sent,
            "otp_expires_in": otp["expires_in"],
            "resend_cooldown": otp["resend_cooldown"],
        },
    }

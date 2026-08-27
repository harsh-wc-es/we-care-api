"""
WeCare — OTP Service (STEP 9)

Mirrors helpers/otp exactly.
Uses otp_codes table with bcrypt-hashed OTP codes.

OTP functions:
    otp_generate_code() → 6-digit random
    otp_create()        → invalidate old + insert new
    otp_latest()        → fetch latest active OTP
    otp_can_resend()    → check cooldown
    otp_verify()        → verify code + mark used
"""

import secrets
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password


def otp_generate_code() -> str:
    """
    Route: otp_generate_code() — otp L5-8
    Returns a 6-digit random string.
    """
    return str(secrets.randbelow(900000) + 100000)


def otp_create(
    db: Session,
    purpose: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Route: otp_create() — otp L10-59

    1. Invalidates all previous OTPs matching purpose+identifiers
    2. Creates new OTP with bcrypt hash
    3. Returns {id, code, expires_in, resend_cooldown}
    """
    options = options or {}
    code = otp_generate_code()
    code_hash = hash_password(code)

    user_id = options.get("user_id")
    pending_user_id = options.get("pending_user_id")
    booking_id = options.get("booking_id")
    email = options.get("email")
    expiry_seconds = options.get("expiry_seconds", 600)
    cooldown_seconds = options.get("cooldown_seconds", 60)
    max_attempts = options.get("max_attempts", 5)
    metadata = options.get("metadata")

    import json
    metadata_json = json.dumps(metadata) if metadata else None

    # Invalidate previous OTPs (otp L25-34)
    # uses <=> (NULL-safe equals) — in MySQL: col <=> value
    db.execute(
        text(
            "UPDATE otp_codes SET used_at = NOW() "
            "WHERE purpose = :purpose AND used_at IS NULL "
            "AND (user_id <=> :user_id) "
            "AND (pending_user_id <=> :pending_user_id) "
            "AND (booking_id <=> :booking_id) "
            "AND (email <=> :email)"
        ),
        {
            "purpose": purpose,
            "user_id": user_id,
            "pending_user_id": pending_user_id,
            "booking_id": booking_id,
            "email": email,
        },
    )

    # Insert new OTP (otp L36-52)
    db.execute(
        text(
            "INSERT INTO otp_codes "
            "(user_id, pending_user_id, booking_id, email, purpose, otp_hash, "
            "expires_at, resend_available_at, max_attempts, metadata) "
            "VALUES (:user_id, :pending_user_id, :booking_id, :email, :purpose, :otp_hash, "
            "DATE_ADD(NOW(), INTERVAL :expiry SECOND), "
            "DATE_ADD(NOW(), INTERVAL :cooldown SECOND), "
            ":max_attempts, :metadata)"
        ),
        {
            "user_id": user_id,
            "pending_user_id": pending_user_id,
            "booking_id": booking_id,
            "email": email,
            "purpose": purpose,
            "otp_hash": code_hash,
            "expiry": expiry_seconds,
            "cooldown": cooldown_seconds,
            "max_attempts": max_attempts,
            "metadata": metadata_json,
        },
    )
    db.commit()

    # Get the inserted ID
    result = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
    otp_id = result["id"] if result else 0

    return {
        "id": otp_id,
        "code": code,
        "expires_in": expiry_seconds,
        "resend_cooldown": cooldown_seconds,
    }


def otp_latest(
    db: Session,
    purpose: str,
    options: dict[str, Any] | None = None,
) -> Optional[dict]:
    """
    Route: otp_latest() — otp L62-89

    Fetches latest active OTP matching purpose + identifiers.
    """
    options = options or {}

    row = db.execute(
        text(
            "SELECT id, user_id, pending_user_id, booking_id, email, purpose, otp_hash, "
            "expires_at, resend_available_at, attempts, max_attempts, used_at, "
            "metadata, created_at, updated_at "
            "FROM otp_codes "
            "WHERE purpose = :purpose AND used_at IS NULL "
            "AND (user_id <=> :user_id) "
            "AND (pending_user_id <=> :pending_user_id) "
            "AND (booking_id <=> :booking_id) "
            "AND (email <=> :email) "
            "ORDER BY id DESC LIMIT 1"
        ),
        {
            "purpose": purpose,
            "user_id": options.get("user_id"),
            "pending_user_id": options.get("pending_user_id"),
            "booking_id": options.get("booking_id"),
            "email": options.get("email"),
        },
    ).mappings().first()

    return dict(row) if row else None


def otp_can_resend(
    db: Session,
    purpose: str,
    options: dict[str, Any] | None = None,
) -> bool:
    """
    Route: otp_can_resend() — otp L91-100

    Returns True if cooldown has passed or no OTP exists.
    """
    import time

    row = otp_latest(db, purpose, options)
    if not row or not row.get("resend_available_at"):
        return True

    resend_at = row["resend_available_at"]
    from datetime import datetime
    if isinstance(resend_at, datetime):
        return resend_at.timestamp() <= time.time()
    if isinstance(resend_at, str):
        return datetime.strptime(resend_at, "%Y-%m-%d %H:%M:%S").timestamp() <= time.time()

    return True


def otp_verify(
    db: Session,
    purpose: str,
    code: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Route: otp_verify() — otp L102-131

    Returns: {"success": bool, "message": str, "row": dict|None}
    """
    import time
    from datetime import datetime

    row = otp_latest(db, purpose, options)

    if not row:
        return {"success": False, "message": "OTP not found"}

    # Check expiry (otp L112-114)
    expires_at = row["expires_at"]
    if isinstance(expires_at, datetime):
        if expires_at.timestamp() < time.time():
            return {"success": False, "message": "OTP expired"}
    elif isinstance(expires_at, str):
        if datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S").timestamp() < time.time():
            return {"success": False, "message": "OTP expired"}

    # Check max attempts (otp L116-118)
    if int(row["attempts"]) >= int(row["max_attempts"]):
        return {"success": False, "message": "Maximum OTP attempts exceeded"}

    # Verify OTP hash (otp L120-124)
    if not verify_password(code, row["otp_hash"]):
        db.execute(
            text("UPDATE otp_codes SET attempts = attempts + 1 WHERE id = :id"),
            {"id": row["id"]},
        )
        db.commit()
        return {"success": False, "message": "Invalid OTP"}

    # Mark as used (otp L127-128)
    db.execute(
        text("UPDATE otp_codes SET used_at = NOW() WHERE id = :id"),
        {"id": row["id"]},
    )
    db.commit()

    return {"success": True, "message": "OTP verified", "row": row}

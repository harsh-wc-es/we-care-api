"""
WeCare — Password Routes (STEP 15)

POST /api/v1/auth/change-password              → change_password
POST /api/v1/auth/forgot-password              → forgot_password (legacy)
POST /api/v1/auth/reset-password               → reset_password (legacy)
POST /api/v1/auth/request-password-reset-otp   → request-password-reset-otp
POST /api/v1/auth/reset-password-with-otp      → reset-password-with-otp
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import success_response, error_response
from app.core.security import hash_password
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ResetPasswordWithOTPRequest,
)
from app.services.auth_service import change_password
from app.services.audit_service import audit_log
from app.services.email_service import send_otp_email
from app.services.otp_service import otp_create, otp_can_resend, otp_verify
from app.services.rate_limit_service import enforce_rate_limit, clear_rate_limit
from app.services.validation_service import validate_password_strength

router = APIRouter()


# ── Email masking — request-password-reset-otp L13-30 ──
def _mask_email(email: str) -> str:
    parts = email.split("@")
    if len(parts) != 2:
        return "***@***"
    local, domain = parts
    if len(local) <= 2:
        masked = local[0] + "***"
    else:
        masked = local[:2] + "*" * max(3, len(local) - 2)
    return masked + "@" + domain


@router.post("/change-password")
def change_password_route(
    body: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Route: change_password L1-45

    NOTE: has a bug where auth_user() doesn't return password.
    We fix this by fetching password hash separately in auth_service.change_password().
    """
    current = (body.current_password or "").strip()
    new_pwd = (body.new_password or "").strip()
    confirm = (body.new_password_confirm or "").strip()

    if not current or not new_pwd or not confirm:
        return error_response("All fields are required", {
            "current_password": ["Current password is required"],
            "new_password": ["New password is required"],
            "new_password_confirm": ["Password confirmation is required"],
        }, 400)

    # Validate new password strength (change_password L31-34)
    pwd_errors = validate_password_strength(new_pwd, confirm, "new_password", "new_password_confirm")
    if pwd_errors:
        return error_response("Validation failed", pwd_errors, 400)

    # Change password (change_password L27-42)
    new_hash = hash_password(new_pwd)
    success = change_password(db, user["id"], current, new_hash)

    if not success:
        return error_response("Current password is incorrect", status_code=401)

    return success_response("Password changed successfully. Please login again.")


@router.post("/forgot-password")
def forgot_password_legacy(
    body: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Route: forgot_password L1-67 (LEGACY — deprecated)

    Uses otp_codes table via otp_create().
    """
    email = (body.email or "").strip()

    if not email:
        return error_response("Email is required", {"email": ["Email is required"]}, 400)

    import re
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return error_response("Invalid email format", {
            "email": ["Please enter valid email address"],
        }, 400)

    enforce_rate_limit(db, "forgot_password", email, max_attempts=3, window_seconds=900, block_seconds=900)

    deprecated_data = {
        "deprecated": True,
        "use_endpoints": [
            "/api/v1/auth/forgot-password/request-otp",
            "/api/v1/auth/forgot-password/verify-otp",
            "/api/v1/auth/forgot-password/reset",
        ],
    }

    # Find user (forgot_password L42-48)
    row = db.execute(
        text(
            "SELECT id, email, username, role, is_verified, is_active "
            "FROM users WHERE email = :email"
        ),
        {"email": email},
    ).mappings().first()

    if not row or int(row.get("is_verified", 0)) != 1 or int(row.get("is_active", 0)) != 1:
        return success_response(
            "If this account exists, an OTP has been sent.", deprecated_data
        )

    user = dict(row)

    # Create OTP (forgot_password L50-55)
    otp = otp_create(db, "password_reset", {
        "user_id": user["id"],
        "email": email,
        "expiry_seconds": 900,
        "cooldown_seconds": 60,
    })

    # Dispatch OTP email via SMTP
    email_sent = send_otp_email(
        to_email=email,
        otp=otp["code"],
        purpose="Password Reset",
        expiry_minutes=15,
    )

    return success_response("Password reset OTP sent successfully", {
        "email_otp_sent": email_sent,
        "otp_expires_in": otp["expires_in"],
        "resend_cooldown": otp["resend_cooldown"],
        **deprecated_data,
    })


@router.post("/reset-password")
def reset_password_legacy(
    body: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Route: reset_password L1-70 (LEGACY — deprecated)

    Uses otp_codes table via otp_verify().
    """
    email = (body.email or "").strip()
    otp_code = body.otp or body.token or ""
    otp_code = str(otp_code).strip()
    new_pwd = (body.new_password or "")
    confirm = (body.new_password_confirm or "")

    errors = {}
    if not email:
        errors["email"] = ["Email is required"]
    if not otp_code:
        errors["otp"] = ["OTP is required"]

    pwd_errors = validate_password_strength(new_pwd, confirm, "new_password", "new_password_confirm")
    errors.update(pwd_errors)

    if errors:
        return error_response("Validation failed", errors, 400)

    # Find user (reset_password L33-39)
    row = db.execute(
        text("SELECT id, email FROM users WHERE email = :email"),
        {"email": email},
    ).mappings().first()

    if not row:
        return error_response("User not found", status_code=404)

    user = dict(row)

    # Verify OTP (reset_password L41-48)
    result = otp_verify(db, "password_reset", otp_code, {
        "user_id": user["id"],
        "email": email,
    })

    if not result["success"]:
        return error_response(result["message"], status_code=400)

    # Update password + blacklist tokens (reset_password L50-60)
    hashed = hash_password(new_pwd)
    db.execute(
        text(
            "UPDATE users SET password = :pwd, reset_token = NULL, reset_token_expiry = NULL "
            "WHERE id = :id"
        ),
        {"pwd": hashed, "id": user["id"]},
    )
    db.execute(
        text("UPDATE tokens SET is_blacklisted = 1 WHERE user_id = :id"),
        {"id": user["id"]},
    )
    db.commit()

    deprecated_data = {
        "deprecated": True,
        "use_endpoints": [
            "/api/v1/auth/forgot-password/request-otp",
            "/api/v1/auth/forgot-password/verify-otp",
            "/api/v1/auth/forgot-password/reset",
        ],
    }

    return success_response(
        "Password reset successful. Please login with new password.",
        deprecated_data,
    )


@router.post("/request-password-reset-otp")
def request_password_reset_otp(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Route: request-password-reset-otp L1-88

    Authenticated endpoint — sends OTP to user's email for password reset.
    """
    enforce_rate_limit(
        db, "password_reset_otp_request",
        f"user:{user['id']}", max_attempts=5, window_seconds=900, block_seconds=900,
    )

    # Fetch email (request-password-reset-otp L42-48)
    row = db.execute(
        text("SELECT email FROM users WHERE id = :id AND is_active = 1 LIMIT 1"),
        {"id": int(user["id"])},
    ).mappings().first()

    if not row or not row.get("email"):
        return error_response("Unable to send OTP", status_code=400)

    email = str(row["email"]).strip()

    # Cooldown check (request-password-reset-otp L53-55)
    if not otp_can_resend(db, "password_reset_authenticated", {"user_id": int(user["id"])}):
        return error_response("Please wait before requesting another OTP", status_code=429)

    # Create OTP (request-password-reset-otp L58-65)
    otp = otp_create(db, "password_reset_authenticated", {
        "user_id": int(user["id"]),
        "email": email,
        "expiry_seconds": 600,
        "cooldown_seconds": 60,
        "max_attempts": 5,
        "metadata": {"source": "profile_reset", "role": user.get("role")},
    })

    # Dispatch OTP email via SMTP
    send_otp_email(
        to_email=email,
        otp=otp["code"],
        purpose="Password Reset",
        expiry_minutes=10,
    )

    # Audit log (request-password-reset-otp L78-82)
    ip = request.client.host if request.client else None
    audit_log(
        db, int(user["id"]), "password_reset_otp_requested", "user", int(user["id"]),
        None,
        {"email_masked": _mask_email(email), "otp_id": int(otp["id"]), "role": user.get("role")},
        ip,
        request.headers.get("user-agent"),
    )

    return success_response("OTP sent successfully", {
        "email": _mask_email(email),
        "expires_in_seconds": 600,
    })


@router.post("/reset-password-with-otp")
def reset_password_with_otp(
    body: ResetPasswordWithOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Route: reset-password-with-otp L1-123

    Authenticated password reset via OTP.
    """
    enforce_rate_limit(
        db, "password_reset_otp_verify",
        f"user:{user['id']}", max_attempts=5, window_seconds=900, block_seconds=900,
    )

    otp_code = (body.otp or "").strip()
    new_pwd = body.new_password or ""
    confirm = body.new_password_confirm or ""

    # Input validation (reset-password-with-otp L26-45)
    errors = {}
    if otp_code == "":
        errors["otp"] = ["OTP is required"]

    pwd_errors = validate_password_strength(new_pwd, confirm, "new_password", "new_password_confirm")
    # Remap confirm_password → new_password_confirm (reset-password-with-otp L36-39)
    if "confirm_password" in pwd_errors:
        pwd_errors["new_password_confirm"] = pwd_errors.pop("confirm_password")
    errors.update(pwd_errors)

    if errors:
        return error_response("Validation failed", errors, 422)

    # Verify OTP (reset-password-with-otp L48-70)
    verification = otp_verify(db, "password_reset_authenticated", otp_code, {
        "user_id": int(user["id"]),
        "email": user.get("email"),
    })

    if not verification["success"]:
        msg = verification["message"]
        if "expired" in msg.lower():
            err_msgs = ["OTP has expired. Please request a new one"]
        elif "attempts" in msg.lower():
            err_msgs = ["Maximum OTP attempts exceeded. Please request a new OTP"]
        else:
            err_msgs = ["Invalid OTP"]
        return error_response("Validation failed", {"otp": err_msgs}, 422)

    # Transaction: update password + blacklist + invalidate OTPs (reset-password-with-otp L73-109)
    try:
        hashed = hash_password(new_pwd)
        db.execute(
            text(
                "UPDATE users SET password = :pwd, reset_token = NULL, "
                "reset_token_expiry = NULL, updated_at = NOW() WHERE id = :id"
            ),
            {"pwd": hashed, "id": int(user["id"])},
        )
        db.execute(
            text("UPDATE tokens SET is_blacklisted = 1 WHERE user_id = :id"),
            {"id": int(user["id"])},
        )
        db.execute(
            text(
                "UPDATE otp_codes SET used_at = NOW() "
                "WHERE user_id = :uid AND purpose = 'password_reset_authenticated' AND used_at IS NULL"
            ),
            {"uid": int(user["id"])},
        )
        db.commit()
    except Exception:
        db.rollback()
        return error_response("Password reset failed", status_code=500)

    # Clear rate limits (reset-password-with-otp L112-113)
    clear_rate_limit(db, "password_reset_otp_verify", f"user:{user['id']}")
    clear_rate_limit(db, "password_reset_otp_request", f"user:{user['id']}")

    # Audit log (reset-password-with-otp L116-120)
    ip = request.client.host if request.client else None
    audit_log(
        db, int(user["id"]), "password_reset_via_otp", "user", int(user["id"]),
        None,
        {"method": "authenticated_otp", "role": user.get("role"), "tokens_revoked": True},
        ip,
        request.headers.get("user-agent"),
    )

    return success_response("Password reset successfully")

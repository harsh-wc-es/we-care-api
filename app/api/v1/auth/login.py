"""
WeCare — Login Routes (STEP 10)

POST /api/v1/auth/login           → login
POST /api/v1/auth/verify-login-otp → verify_login_otp (STEP 14)
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.response import success_response, error_response
from app.db.session import get_db
from app.schemas.auth import LoginRequest, VerifyLoginOTPRequest
from app.services.auth_service import (
    authenticate_user,
    build_login_user_response,
    check_user_login_eligibility,
    create_and_persist_tokens,
)
from app.services.email_service import send_otp_email
from app.services.otp_service import otp_create, otp_verify
from app.services.rate_limit_service import enforce_rate_limit, clear_rate_limit

router = APIRouter()


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Route: login L1-128

    Supports login by email, phone_number, username, or generic 'login' field.
    Optionally requires OTP if require_otp != "0".
    """
    # Determine identifier (login L18-25)
    identifier = (
        body.login or body.email or body.phone_number or body.username or ""
    ).strip()
    password = (body.password or "").strip()

    if not identifier or not password:
        return error_response(
            "Login and password are required",
            {"login": ["Login is required"], "password": ["Password is required"]},
            400,
        )

    # Rate limit (login L30)
    enforce_rate_limit(db, "login", identifier, max_attempts=5, window_seconds=900, block_seconds=900)

    # Authenticate (login L36-51)
    user = authenticate_user(db, identifier, password)
    if not user:
        import logging
        logging.getLogger(__name__).warning(f"Login failed for identifier='{identifier}'")
        return error_response("Invalid credentials", status_code=401)

    # Eligibility checks (login L53-61)
    eligibility_error = check_user_login_eligibility(user)
    if eligibility_error:
        return error_response(
            eligibility_error["message"],
            eligibility_error.get("errors"),
            eligibility_error["status"],
        )

    # OTP flow (login L68-92)
    require_otp = str(body.require_otp or "1")
    if require_otp != "0":
        otp = otp_create(db, "login", {
            "user_id": user["id"],
            "email": user["email"],
            "expiry_seconds": 600,
            "cooldown_seconds": 60,
        })
        # Dispatch OTP email via SMTP
        if user.get("email"):
            send_otp_email(
                to_email=user["email"],
                otp=otp["code"],
                purpose="Login Verification",
                expiry_minutes=10,
            )
        return success_response("OTP sent to your email", {
            "otp_required": True,
            "email": user["email"],
            "otp_expires_in": otp["expires_in"],
        })

    # Direct login without OTP (login L95-127)
    access, refresh = create_and_persist_tokens(db, user["id"], user["role"])
    clear_rate_limit(db, "login", identifier)

    return success_response("Login successful", {
        "access": access,
        "refresh": refresh,
        "user": build_login_user_response(user),
    })


@router.post("/verify-login-otp")
def verify_login_otp(
    body: VerifyLoginOTPRequest, request: Request, db: Session = Depends(get_db)
):
    """
    Route: verify_login_otp L1-83
    """
    email = (body.email or "").strip()
    otp_code = (body.otp or "").strip()

    if not email or not otp_code:
        return error_response("Email and OTP are required", {
            "email": ["Email is required"],
            "otp": ["OTP is required"],
        }, 400)

    enforce_rate_limit(db, "verify_login_otp", email, max_attempts=5, window_seconds=900, block_seconds=900)

    # Find user (verify_login_otp L28-39)
    from sqlalchemy import text
    row = db.execute(
        text(
            "SELECT id, email, username, phone_number, role, is_verified, is_active "
            "FROM users WHERE email = :email AND is_active = 1 LIMIT 1"
        ),
        {"email": email},
    ).mappings().first()

    if not row:
        return error_response("User not found or inactive", status_code=404)

    user = dict(row)

    # Verify OTP (verify_login_otp L41-48)
    result = otp_verify(db, "login", otp_code, {
        "user_id": user["id"],
        "email": email,
    })

    if not result["success"]:
        return error_response(result["message"], status_code=400)

    # Issue tokens (verify_login_otp L50-68)
    access, refresh = create_and_persist_tokens(db, user["id"], user["role"])
    clear_rate_limit(db, "verify_login_otp", email)

    return success_response("Login successful", {
        "access": access,
        "refresh": refresh,
        "user": build_login_user_response(user),
    })

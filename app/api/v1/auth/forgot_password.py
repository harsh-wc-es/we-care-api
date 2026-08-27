"""
WeCare — Forgot Password 3-Step Flow Routes (STEP 15)

POST /api/v1/auth/forgot-password/request-otp  → forgot-password/request-otp
POST /api/v1/auth/forgot-password/verify-otp   → forgot-password/verify-otp
POST /api/v1/auth/forgot-password/reset        → forgot-password/reset

Uses helpers/forgot_password (otp_verifications table, NOT otp_codes).
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.response import success_response, error_response
from app.db.session import get_db
from app.schemas.auth import (
    ForgotPasswordOTPRequest,
    ForgotPasswordVerifyRequest,
    ForgotPasswordResetRequest,
)
from app.services.password_service import (
    forgot_password_request_otp,
    forgot_password_verify_otp,
    forgot_password_reset,
)
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter()


@router.post("/request-otp")
def request_otp(
    body: ForgotPasswordOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Route: forgot-password/request-otp L1-20"""
    login = (body.login or "").strip()
    ip = request.client.host if request.client else "unknown"

    enforce_rate_limit(
        db, "forgot_password_request", login or ip,
        max_attempts=5, window_seconds=900, block_seconds=900,
    )

    result = forgot_password_request_otp(db, login)

    if result["success"]:
        return success_response(result["message"], result.get("data"), result["status"])
    return error_response(result["message"], result.get("errors"), result["status"])


@router.post("/verify-otp")
def verify_otp(
    body: ForgotPasswordVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Route: forgot-password/verify-otp L1-21"""
    login = (body.login or "").strip()
    otp = (body.otp or "").strip()
    ip = request.client.host if request.client else "unknown"

    enforce_rate_limit(
        db, "forgot_password_verify", login or ip,
        max_attempts=10, window_seconds=900, block_seconds=900,
    )

    result = forgot_password_verify_otp(db, login, otp)

    if result["success"]:
        return success_response(result["message"], result.get("data"), result["status"])
    return error_response(result["message"], result.get("errors"), result["status"])


@router.post("/reset")
def reset(
    body: ForgotPasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Route: forgot-password/reset L1-22"""
    ip = request.client.host if request.client else "unknown"

    enforce_rate_limit(
        db, "forgot_password_reset", ip,
        max_attempts=10, window_seconds=900, block_seconds=900,
    )

    result = forgot_password_reset(
        db,
        body.password_reset_token or "",
        body.new_password or "",
        body.confirm_password or "",
    )

    if result["success"]:
        return success_response(result["message"], result.get("data"), result["status"])
    return error_response(result["message"], result.get("errors"), result["status"])

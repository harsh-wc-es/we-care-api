"""
WeCare — Registration Routes (STEP 13)

POST /api/v1/auth/register             → register
POST /api/v1/auth/register-caretaker   → register_caretaker
POST /api/v1/auth/register-patient     → register_patient
POST /api/v1/auth/verify-register-otp  → verify-register-otp
POST /api/v1/auth/verify-email         → verify_email
POST /api/v1/auth/resend-email-otp     → resend_email_otp
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.response import success_response, error_response
from app.db.session import get_db
from app.schemas.auth import (
    RegisterRequest,
    VerifyRegisterOTPRequest,
    ResendEmailOTPRequest,
)
from app.services.rate_limit_service import enforce_rate_limit, clear_rate_limit
from app.services.registration_service import (
    pending_registration_create,
    pending_registration_verify,
    pending_registration_resend,
)

router = APIRouter()


def _handle_register(body: RegisterRequest, db: Session, role: str, request: Request):
    """Common logic for all register endpoints."""
    enforce_rate_limit(db, "register", max_attempts=5, window_seconds=900, block_seconds=900)

    data = body.model_dump()
    result = pending_registration_create(db, data, role)

    if result["success"]:
        return success_response(
            result["message"], result.get("data"), result["status"]
        )
    return error_response(
        result["message"], result.get("errors"), result["status"]
    )


@router.post("/register")
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """
    Route: register L1-26

    Accepts optional role field (default: "family").
    """
    role = (body.role or "family").strip().lower()
    if role not in ("family", "caretaker"):
        return error_response("Invalid role", {
            "role": ["Allowed values are family and caretaker"],
        }, 400)

    return _handle_register(body, db, role, request)


@router.post("/register-caretaker")
def register_caretaker(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Route: register_caretaker — hardcoded role=caretaker."""
    return _handle_register(body, db, "caretaker", request)


@router.post("/register-patient")
def register_patient(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Route: register_patient — hardcoded role=family."""
    return _handle_register(body, db, "family", request)


@router.post("/verify-register-otp")
def verify_register_otp(
    body: VerifyRegisterOTPRequest, request: Request, db: Session = Depends(get_db)
):
    """Route: verify-register-otp L1-25."""
    email = (body.email or "").strip()
    otp = (body.otp or "").strip()

    enforce_rate_limit(db, "verify_email_otp", email or None, max_attempts=5, window_seconds=900, block_seconds=900)

    result = pending_registration_verify(db, email, otp)
    if result["success"]:
        clear_rate_limit(db, "verify_email_otp", email)
        return success_response(result["message"], result.get("data"), result["status"])

    return error_response(result["message"], result.get("errors"), result["status"])


@router.post("/verify-email")
def verify_email(
    body: VerifyRegisterOTPRequest, request: Request, db: Session = Depends(get_db)
):
    """
    Route: verify_email L1-33

    Same as verify-register-otp with slightly different response on success.
    """
    email = (body.email or "").strip()
    otp = (body.otp or "").strip()

    enforce_rate_limit(db, "verify_email_otp", email or None, max_attempts=5, window_seconds=900, block_seconds=900)

    if not email or not otp:
        return error_response("Email and OTP are required", {
            "email": ["Email is required"], "otp": ["OTP is required"],
        }, 400)

    result = pending_registration_verify(db, email, otp)
    if not result["success"]:
        return error_response(result["message"], result.get("errors"), result["status"])

    clear_rate_limit(db, "verify_email_otp", email)
    data = result.get("data", {"is_verified": True})
    return success_response(result["message"], data, result["status"])


@router.post("/resend-email-otp")
def resend_email_otp(
    body: ResendEmailOTPRequest, request: Request, db: Session = Depends(get_db)
):
    """Route: resend_email_otp L1-26."""
    email = (body.email or "").strip()

    enforce_rate_limit(db, "resend_email_otp", email or None, max_attempts=3, window_seconds=900, block_seconds=900)

    if not email:
        return error_response("Email is required", {"email": ["Email is required"]}, 400)

    result = pending_registration_resend(db, email)
    if result["success"]:
        return success_response(result["message"], result.get("data"), result["status"])

    return error_response(result["message"], result.get("errors"), result["status"])

"""
WeCare — Auth Schemas (Part 3)

Pydantic schemas for authentication endpoints.
Field names match request/response contracts exactly.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════
# Safe User — matches AUTH_USER_SAFE_COLUMNS
# ══════════════════════════════════════════════════════════

class SafeUserResponse(BaseModel):
    """10 safe fields from auth L8. Never exposes password."""
    id: int
    email: str
    username: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    is_verified: bool
    is_active: bool = True
    profile_picture: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LoginUserResponse(BaseModel):
    """Subset returned in login/refresh responses (login L119-126)."""
    id: int
    email: str
    username: Optional[str] = None
    role: str
    is_verified: bool
    phone_number: Optional[str] = None


# ══════════════════════════════════════════════════════════
# Login
# ══════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    """login L18-25 — supports multiple identifier fields."""
    login: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    username: Optional[str] = None
    password: str = ""
    require_otp: Optional[str] = None  # "0" or "1" (string comparison)


# ══════════════════════════════════════════════════════════
# Refresh
# ══════════════════════════════════════════════════════════

class RefreshRequest(BaseModel):
    """refresh_token L14 — accepts both field names."""
    refresh: Optional[str] = None
    refresh_token: Optional[str] = None


# ══════════════════════════════════════════════════════════
# Logout
# ══════════════════════════════════════════════════════════

class LogoutRequest(BaseModel):
    """logout L14."""
    refresh: str = ""


# ══════════════════════════════════════════════════════════
# Register
# ══════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    """pending_registration L66-76."""
    email: str = ""
    username: str = ""
    phone_number: str = ""
    password: str = ""
    password_confirm: str = ""
    full_name: Optional[str] = None
    role: Optional[str] = None  # Used by register, ignored by register_caretaker/patient


class VerifyRegisterOTPRequest(BaseModel):
    """verify-register-otp L14-15."""
    email: str = ""
    otp: str = ""


class ResendEmailOTPRequest(BaseModel):
    """resend_email_otp L14."""
    email: str = ""


# ══════════════════════════════════════════════════════════
# Login OTP
# ══════════════════════════════════════════════════════════

class VerifyLoginOTPRequest(BaseModel):
    """verify_login_otp L16-17."""
    email: str = ""
    otp: str = ""


# ══════════════════════════════════════════════════════════
# Change Password
# ══════════════════════════════════════════════════════════

class ChangePasswordRequest(BaseModel):
    """change_password L15-17."""
    current_password: str = ""
    new_password: str = ""
    new_password_confirm: str = ""


# ══════════════════════════════════════════════════════════
# Forgot Password (legacy)
# ══════════════════════════════════════════════════════════

class ForgotPasswordRequest(BaseModel):
    """forgot_password L16."""
    email: str = ""


class ResetPasswordRequest(BaseModel):
    """reset_password L13-18."""
    email: str = ""
    token: Optional[str] = None
    otp: Optional[str] = None
    new_password: str = ""
    new_password_confirm: str = ""


# ══════════════════════════════════════════════════════════
# Forgot Password (3-step flow)
# ══════════════════════════════════════════════════════════

class ForgotPasswordOTPRequest(BaseModel):
    """forgot-password/request-otp L14."""
    login: str = ""


class ForgotPasswordVerifyRequest(BaseModel):
    """forgot-password/verify-otp L14-15."""
    login: str = ""
    otp: str = ""


class ForgotPasswordResetRequest(BaseModel):
    """forgot-password/reset L14-16."""
    password_reset_token: str = ""
    new_password: str = ""
    confirm_password: str = ""


# ══════════════════════════════════════════════════════════
# Authenticated Password Reset with OTP
# ══════════════════════════════════════════════════════════

class ResetPasswordWithOTPRequest(BaseModel):
    """reset-password-with-otp L21-23."""
    otp: str = ""
    new_password: str = ""
    new_password_confirm: str = ""

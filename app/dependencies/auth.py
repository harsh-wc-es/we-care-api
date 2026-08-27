"""
WeCare — Authentication & Authorization Dependencies (STEPS 7-8)

Mirrors helpers/auth:
    auth_user()      → get_current_user
    admin_only()     → require_admin
    caretaker_only() → require_caretaker
    family_only()    → require_family

auth_user() check order (auth L32-77):
    1. Extract Bearer token from Authorization header
    2. verify_token() — JWT decode + signature + expiry
    3. Check type === "access"
    4. SELECT safe columns FROM users WHERE id = ? AND is_active = 1
    5. Check is_verified === 1 (returns 403)
    6. SELECT FROM tokens WHERE user_id = ? AND access_token = ? AND is_blacklisted = 0
    7. Return safe user dict
"""

from typing import Any

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.security import decode_jwt
from app.db.session import get_db


# ── AUTH_USER_SAFE_COLUMNS (auth L8) ──
AUTH_USER_SAFE_COLUMNS = (
    "id, email, username, phone_number, role, "
    "is_verified, is_active, profile_picture, created_at, updated_at"
)


def _extract_bearer_token(request: Request) -> str | None:
    """
    Route: get_bearer_token() — auth L10-30

    Extracts token from Authorization header using Bearer scheme.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]

    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Route: auth_user() — auth L32-77

    Reproduces the exact authentication check chain.
    Returns a dict with safe user columns (never password).
    """
    # Step 1: Extract bearer token (auth L36-39)
    token = _extract_bearer_token(request)
    if not token:
        raise APIException("Authentication required", status_code=401)

    # Step 2: Verify JWT signature + expiry (auth L42-46)
    payload = decode_jwt(token)
    if not payload:
        raise APIException("Invalid or expired token", status_code=401)

    # Step 3: Check token type (auth L48-50)
    if payload.get("type") != "access":
        raise APIException("Invalid token type", status_code=401)

    # Step 4: Fetch user with safe columns (auth L52-54)
    user_id = payload.get("user_id")
    stmt = text(
        f"SELECT {AUTH_USER_SAFE_COLUMNS} FROM users "
        f"WHERE id = :id AND is_active = 1"
    )
    row = db.execute(stmt, {"id": user_id}).mappings().first()

    if not row:
        raise APIException("User not found", status_code=401)

    user = dict(row)

    # Step 5: Check is_verified (auth L60-62)
    if int(user.get("is_verified", 0)) != 1:
        raise APIException("Email verification required", status_code=403)

    # Step 6: Check token exists in DB and not blacklisted (auth L64-75)
    token_stmt = text(
        "SELECT id FROM tokens "
        "WHERE user_id = :user_id "
        "AND access_token = :access_token "
        "AND is_blacklisted = 0 "
        "LIMIT 1"
    )
    token_row = db.execute(
        token_stmt, {"user_id": user_id, "access_token": token}
    ).first()

    if not token_row:
        raise APIException("Token is no longer active", status_code=401)

    # Step 7: Return safe user dict
    return user


# ══════════════════════════════════════════════════════════
# Role dependencies — auth L80-111
# ══════════════════════════════════════════════════════════

def require_admin(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Route: admin_only() — auth L80-89
    """
    if user.get("role") != "admin":
        raise APIException(
            "You do not have permission to perform this action.",
            status_code=403,
        )
    return user


def require_caretaker(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Route: caretaker_only() — auth L91-100
    """
    if user.get("role") != "caretaker":
        raise APIException(
            "Only caretaker can access this API",
            status_code=403,
        )
    return user


def require_family(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Route: family_only() — auth L102-111
    """
    if user.get("role") != "family":
        raise APIException(
            "Only family user can access this API",
            status_code=403,
        )
    return user

"""
WeCare — Auth Service (STEPS 10-12)

Core auth operations mirroring login, refresh_token, logout.
"""

import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import (
    create_jwt,
    create_token_pair,
    decode_jwt,
    hash_password,
    verify_password,
    ACCESS_TOKEN_EXPIRE,
    REFRESH_TOKEN_EXPIRE,
)
from app.services.validation_service import normalize_username


def authenticate_user(
    db: Session,
    identifier: str,
    password: str,
) -> dict[str, Any]:
    """
    Route: login L36-51

    Finds user by email/phone/username and verifies password.
    Returns user dict with password hash (for verify), or raises.
    """
    identifier = identifier.strip()
    password = password.strip()
    username_identifier = normalize_username(identifier)

    # login L36-43: lookup by email OR phone_number OR LOWER(username)
    row = db.execute(
        text(
            "SELECT id, email, username, phone_number, role, password, "
            "is_verified, is_active, profile_picture, created_at "
            "FROM users "
            "WHERE email = :id OR phone_number = :id OR LOWER(username) = :uname "
            "LIMIT 1"
        ),
        {"id": identifier, "uname": username_identifier},
    ).mappings().first()

    if not row:
        return None

    user = dict(row)

    # login L49-51: verify password
    if not verify_password(password, user["password"]):
        return None

    return user


def check_user_login_eligibility(user: dict) -> Optional[dict]:
    """
    Route: login L53-61

    Returns error dict if user cannot login, None if OK.
    """
    # is_active check (login L53-55)
    if user.get("is_active") != 1 and user.get("is_active") is not True:
        return {"message": "Account is inactive", "status": 403}

    # is_verified check (login L57-61)
    if int(user.get("is_verified", 0)) != 1:
        return {
            "message": "Email verification required",
            "errors": {"email": ["Please verify your email before login"]},
            "status": 403,
        }

    return None


def create_and_persist_tokens(
    db: Session,
    user_id: int,
    role: str,
) -> tuple[str, str]:
    """
    Route: login L95-113

    Creates JWT pair and inserts into tokens table.
    Returns (access_token, refresh_token).
    """
    access, refresh = create_token_pair(user_id, role)
    expires_at = datetime.fromtimestamp(
        time.time() + REFRESH_TOKEN_EXPIRE
    ).strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        text(
            "INSERT INTO tokens (user_id, access_token, refresh_token, expires_at) "
            "VALUES (:user_id, :access, :refresh, :expires_at)"
        ),
        {
            "user_id": user_id,
            "access": access,
            "refresh": refresh,
            "expires_at": expires_at,
        },
    )
    db.commit()

    return access, refresh


def refresh_access_token(
    db: Session,
    refresh_token: str,
) -> Optional[dict[str, Any]]:
    """
    Route: refresh_token L13-81

    Verifies refresh JWT → checks DB → creates new access token → updates DB.
    Returns response data dict or None.
    """
    refresh_token = refresh_token.strip()

    if not refresh_token:
        return None

    # Verify refresh JWT (refresh_token L20-28)
    payload = decode_jwt(refresh_token)
    if not payload:
        return {"error": "Invalid or expired refresh token", "status": 401}

    if payload.get("type") != "refresh":
        return {"error": "Invalid token type", "status": 401}

    user_id = payload.get("user_id")

    # Check DB token row (refresh_token L32-44)
    token_row = db.execute(
        text(
            "SELECT id, user_id, refresh_token, is_blacklisted, expires_at "
            "FROM tokens "
            "WHERE user_id = :user_id AND refresh_token = :refresh "
            "AND is_blacklisted = 0 LIMIT 1"
        ),
        {"user_id": user_id, "refresh": refresh_token},
    ).mappings().first()

    if not token_row:
        return {"error": "Refresh token not found or logged out", "status": 401}

    # Check user (refresh_token L46-57)
    user = db.execute(
        text(
            "SELECT id, email, username, phone_number, role, is_verified, is_active "
            "FROM users WHERE id = :id AND is_active = 1 LIMIT 1"
        ),
        {"id": user_id},
    ).mappings().first()

    if not user:
        return {"error": "User not found or inactive", "status": 401}

    user = dict(user)

    # Generate new access token (refresh_token L59-63)
    new_access = create_jwt(
        {"user_id": user["id"], "role": user["role"], "type": "access"},
        ACCESS_TOKEN_EXPIRE,
    )

    # Update DB (refresh_token L65-69)
    db.execute(
        text("UPDATE tokens SET access_token = :access WHERE id = :id"),
        {"access": new_access, "id": token_row["id"]},
    )
    db.commit()

    return {
        "access": new_access,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user.get("username"),
            "phone_number": user.get("phone_number"),
            "role": user["role"],
            "is_verified": bool(int(user.get("is_verified", 0))),
        },
    }


def logout_user(
    db: Session,
    user_id: int,
    refresh_token: str,
) -> bool:
    """
    Route: logout L20-29

    Blacklists the token row matching user_id + refresh_token.
    Returns True if a row was updated, False otherwise.
    """
    result = db.execute(
        text(
            "UPDATE tokens SET is_blacklisted = 1 "
            "WHERE user_id = :user_id AND refresh_token = :refresh"
        ),
        {"user_id": user_id, "refresh": refresh_token},
    )
    db.commit()
    return result.rowcount > 0


def change_password(
    db: Session,
    user_id: int,
    current_password: str,
    new_password_hash: str,
) -> bool:
    """
    Route: change_password L27-42

    NOTE: has a bug — auth_user() doesn't return password.
    We fix this by fetching password separately.
    """
    # Fetch current hash (fix for bug)
    row = db.execute(
        text("SELECT password FROM users WHERE id = :id"),
        {"id": user_id},
    ).mappings().first()

    if not row:
        return False

    if not verify_password(current_password, row["password"]):
        return False

    # Update password (change_password L38)
    db.execute(
        text("UPDATE users SET password = :pwd WHERE id = :id"),
        {"pwd": new_password_hash, "id": user_id},
    )

    # Blacklist all tokens (change_password L41-42)
    db.execute(
        text("UPDATE tokens SET is_blacklisted = 1 WHERE user_id = :id"),
        {"id": user_id},
    )
    db.commit()

    return True


def build_login_user_response(user: dict) -> dict:
    """
    Builds the login/refresh user response subset (login L119-126).
    """
    return {
        "id": user["id"],
        "email": user["email"],
        "username": user.get("username"),
        "role": user["role"],
        "is_verified": bool(int(user.get("is_verified", 0))),
        "phone_number": user.get("phone_number"),
    }

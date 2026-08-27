"""
WeCare — User Profile Routes

GET    /api/v1/auth/profile → api/v1/auth/profile (GET)
POST   /api/v1/auth/profile → api/v1/auth/profile (POST)
PATCH  /api/v1/auth/profile → api/v1/auth/profile (PATCH)
DELETE /api/v1/auth/profile → api/v1/auth/profile (DELETE)
"""

import os
import re
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.services.url_service import public_file_url
from app.services.validation_service import validate_username

router = APIRouter()


def remove_sensitive_user_fields(user_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route: remove_sensitive_user_fields() — api/v1/auth/profile L11-22
    """
    d = dict(user_dict)
    d.pop("password", None)
    d.pop("reset_token", None)
    d.pop("reset_token_expiry", None)
    d["profile_picture_url"] = public_file_url(d.get("profile_picture"))
    return d


def user_to_profile_dict(user: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Convert user dict to sanitized profile dict."""
    user_id = int(user["id"])
    role_str = str(user.get("role") or "")
    created_at = user.get("created_at")
    updated_at = user.get("updated_at")

    d: Dict[str, Any] = {
        "id": user_id,
        "email": user.get("email"),
        "username": user.get("username"),
        "phone_number": user.get("phone_number"),
        "role": role_str,
        "is_verified": int(user.get("is_verified") or 0),
        "profile_picture": user.get("profile_picture"),
        "profile_picture_url": public_file_url(user.get("profile_picture")),
        "is_active": int(user.get("is_active") or 1),
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else (str(created_at) if created_at else None),
        "updated_at": updated_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(updated_at, "strftime") else (str(updated_at) if updated_at else None),
    }

    if role_str == "caretaker":
        row = db.execute(
            text("SELECT is_available, availability_updated_at FROM caretaker_profiles WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if row:
            m = row._mapping
            av_up = m.get("availability_updated_at")
            d["is_available"] = int(m.get("is_available") or 0) == 1
            d["availability_updated_at"] = av_up.strftime("%Y-%m-%d %H:%M:%S") if hasattr(av_up, "strftime") else (str(av_up) if av_up else None)

    return remove_sensitive_user_fields(d)


@router.get("/profile")
def get_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/auth/profile (GET)
    """
    profile_data = user_to_profile_dict(current_user, db)
    return success_response(data=profile_data, message="Profile retrieved")


async def handle_profile_update(
    request: Request,
    current_user: Dict[str, Any],
    db: Session,
    username: Optional[str] = None,
    phone_number: Optional[str] = None,
    profile_picture: Optional[UploadFile] = None,
) -> Dict[str, Any]:
    """Shared handler for POST and PATCH /api/v1/auth/profile."""
    user_id = int(current_user["id"])
    content_type = request.headers.get("content-type", "")

    # If application/json, read json body
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            body = {}
        username_input = body.get("username", current_user.get("username"))
        phone_number_input = body.get("phone_number", current_user.get("phone_number"))
    else:
        username_input = username if username is not None else current_user.get("username")
        phone_number_input = phone_number if phone_number is not None else current_user.get("phone_number")

    # Validate username
    u_val = validate_username(username_input)
    if not u_val["valid"]:
        raise APIException(
            message=u_val["message"],
            status_code=400,
            errors={"username": [u_val["message"]]},
        )

    valid_username = u_val["username"]

    # Check username uniqueness
    existing_u = db.execute(
        text("SELECT id FROM users WHERE username = :u AND id <> :id LIMIT 1"),
        {"u": valid_username, "id": user_id},
    ).fetchone()
    if existing_u:
        raise APIException(
            message="Username already taken",
            status_code=400,
            errors={"username": ["Username is already taken"]},
        )

    db_profile_picture = current_user.get("profile_picture")

    # Handle profile picture upload if provided
    if profile_picture and profile_picture.filename:
        file_bytes = await profile_picture.read()
        file_size = len(file_bytes)

        if file_size > 2 * 1024 * 1024:
            raise APIException(
                message="Profile picture is too large",
                status_code=400,
                errors={"profile_picture": ["Maximum file size is 2MB"]},
            )

        # Detect MIME type
        allowed_types = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }

        mime_type = profile_picture.content_type or ""
        if file_bytes.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        elif file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]:
            mime_type = "image/webp"

        if mime_type not in allowed_types:
            raise APIException(
                message="Invalid profile picture type",
                status_code=400,
                errors={"profile_picture": ["Allowed file types are jpg, png and webp"]},
            )

        ext = allowed_types[mime_type]
        upload_dir = os.path.join(os.getcwd(), "uploads", "profiles")
        os.makedirs(upload_dir, exist_ok=True)

        orig_name = os.path.splitext(os.path.basename(profile_picture.filename or "avatar"))[0]
        safe_base = re.sub(r"[^A-Za-z0-9_.-]", "_", orig_name)
        file_name = f"{secrets.token_hex(12)}_{safe_base}.{ext}"
        target_path = os.path.join(upload_dir, file_name)

        with open(target_path, "wb") as f:
            f.write(file_bytes)

        db_profile_picture = f"uploads/profiles/{file_name}"

    # Update users table
    db.execute(
        text(
            "UPDATE users "
            "SET username = :username, phone_number = :phone_number, profile_picture = :profile_picture, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {
            "username": valid_username,
            "phone_number": phone_number_input,
            "profile_picture": db_profile_picture,
            "id": user_id,
        },
    )
    db.commit()

    # Fetch updated user
    updated_row = db.execute(
        text(
            "SELECT id, email, username, phone_number, role, is_verified, is_active, profile_picture, created_at, updated_at "
            "FROM users WHERE id = :id"
        ),
        {"id": user_id},
    ).mappings().first()

    profile_data = user_to_profile_dict(dict(updated_row), db)

    return success_response(data=profile_data, message="Profile updated successfully")


@router.post("/profile")
async def update_profile_post(
    request: Request,
    username: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/auth/profile (POST)
    """
    return await handle_profile_update(
        request=request,
        current_user=current_user,
        db=db,
        username=username,
        phone_number=phone_number,
        profile_picture=profile_picture,
    )


@router.patch("/profile")
async def update_profile_patch(
    request: Request,
    username: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/auth/profile (PATCH)
    """
    return await handle_profile_update(
        request=request,
        current_user=current_user,
        db=db,
        username=username,
        phone_number=phone_number,
        profile_picture=profile_picture,
    )


@router.delete("/profile")
def deactivate_account(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/auth/profile (DELETE)
    """
    user_id = int(current_user["id"])
    role_str = str(current_user.get("role") or "")

    try:
        db.execute(
            text("UPDATE users SET is_active = 0, updated_at = NOW() WHERE id = :id"),
            {"id": user_id},
        )

        if role_str == "caretaker":
            db.execute(
                text(
                    "UPDATE caretaker_profiles "
                    "SET is_available = 0, availability_updated_at = NOW(), updated_at = NOW() "
                    "WHERE user_id = :id"
                ),
                {"id": user_id},
            )

        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException(message="Account deactivation failed", status_code=500)

    return success_response(message="Account deactivated successfully")

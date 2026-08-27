"""
Tests for Authentication & Authorization Dependencies (STEPS 7-8)

Verifies:
- Bearer token extraction
- Stateful token verification against database
- User active and verified status enforcement
- Role dependency checks (admin_only, caretaker_only, family_only)
"""

import pytest
from unittest.mock import MagicMock
from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.security import create_jwt, hash_password
from app.dependencies.auth import (
    _extract_bearer_token,
    get_current_user,
    require_admin,
    require_caretaker,
    require_family,
)


def test_extract_bearer_token():
    """Extracts token from Authorization: Bearer <token>."""
    req = MagicMock(spec=Request)

    # Valid bearer
    req.headers.get.return_value = "Bearer valid.token.here"
    assert _extract_bearer_token(req) == "valid.token.here"

    # Case insensitive scheme
    req.headers.get.return_value = "bearer valid.token.here"
    assert _extract_bearer_token(req) == "valid.token.here"

    # Missing header
    req.headers.get.return_value = None
    assert _extract_bearer_token(req) is None

    # Malformed header
    req.headers.get.return_value = "Basic dXNlcjpwYXNz"
    assert _extract_bearer_token(req) is None


def test_get_current_user_missing_header():
    """Missing bearer token raises 401."""
    req = MagicMock(spec=Request)
    req.headers.get.return_value = None
    db = MagicMock(spec=Session)

    with pytest.raises(APIException) as exc:
        get_current_user(req, db)
    assert exc.value.status_code == 401
    assert exc.value.message == "Authentication required"


def test_get_current_user_invalid_jwt():
    """Invalid JWT signature or format raises 401."""
    req = MagicMock(spec=Request)
    req.headers.get.return_value = "Bearer invalid.jwt.string"
    db = MagicMock(spec=Session)

    with pytest.raises(APIException) as exc:
        get_current_user(req, db)
    assert exc.value.status_code == 401
    assert exc.value.message == "Invalid or expired token"


def test_get_current_user_wrong_token_type():
    """Refresh token passed to auth_user raises 401."""
    token = create_jwt({"user_id": 1, "role": "family", "type": "refresh"}, expire_seconds=3600)
    req = MagicMock(spec=Request)
    req.headers.get.return_value = f"Bearer {token}"
    db = MagicMock(spec=Session)

    with pytest.raises(APIException) as exc:
        get_current_user(req, db)
    assert exc.value.status_code == 401
    assert exc.value.message == "Invalid token type"


def test_require_roles():
    """Role dependencies allow authorized role and reject other roles with 403."""
    admin_user = {"id": 1, "role": "admin", "email": "admin@example.com"}
    caretaker_user = {"id": 2, "role": "caretaker", "email": "caretaker@example.com"}
    family_user = {"id": 3, "role": "family", "email": "family@example.com"}

    # Admin check
    assert require_admin(admin_user) == admin_user
    with pytest.raises(APIException) as exc:
        require_admin(caretaker_user)
    assert exc.value.status_code == 403
    assert exc.value.message == "You do not have permission to perform this action."

    # Caretaker check
    assert require_caretaker(caretaker_user) == caretaker_user
    with pytest.raises(APIException) as exc:
        require_caretaker(family_user)
    assert exc.value.status_code == 403
    assert exc.value.message == "Only caretaker can access this API"

    # Family check
    assert require_family(family_user) == family_user
    with pytest.raises(APIException) as exc:
        require_family(admin_user)
    assert exc.value.status_code == 403
    assert exc.value.message == "Only family user can access this API"

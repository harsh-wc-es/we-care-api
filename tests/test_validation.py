"""
Tests for Validation Service (STEP 9)

Verifies:
- Username normalization (lowercase, trim, whitespace collapse)
- Username validation (min 3, max 30, characters, empty)
- Password strength and confirmation validation
"""

import pytest

from app.services.validation_service import (
    normalize_username,
    validate_username,
    username_error_response,
    validate_password_strength,
)


def test_normalize_username():
    """normalize_username trims, lowercases, and collapses internal spaces."""
    assert normalize_username("  JohnDoe  ") == "johndoe"
    assert normalize_username("Admin  User") == "admin user"
    assert normalize_username("TEST_USER.1") == "test_user.1"
    assert normalize_username("") == ""


def test_validate_username_valid():
    """Valid usernames meet 3-30 chars and allowed charset."""
    valid_names = ["john_doe", "jane.doe", "user123", "a_b_c", "min"]
    for name in valid_names:
        result = validate_username(name)
        assert result["valid"] is True
        assert result["message"] is None
        assert result["username"] == name.lower()


def test_validate_username_empty():
    """Empty username is invalid."""
    result = validate_username("")
    assert result["valid"] is False
    assert result["message"] == "Username is required"


def test_validate_username_too_short():
    """Less than 3 characters is invalid."""
    result = validate_username("ab")
    assert result["valid"] is False
    assert result["message"] == "Username must be at least 3 characters"


def test_validate_username_too_long():
    """More than 30 characters is invalid."""
    result = validate_username("a" * 31)
    assert result["valid"] is False
    assert result["message"] == "Username must not exceed 30 characters"


def test_validate_username_invalid_characters():
    """Characters outside [a-z0-9_.] are invalid."""
    invalid_names = ["user@name", "user-name", "user name", "user#1", "user!"]
    for name in invalid_names:
        result = validate_username(name)
        assert result["valid"] is False
        assert result["message"] == "Username may only contain letters, numbers, underscore and dot"


def test_username_error_response():
    """Helper generates exact error structure."""
    res = username_error_response("Custom error")
    assert res == {"username": ["Custom error"]}


def test_validate_password_strength_valid():
    """Password with >= 8 characters and matching confirm is valid."""
    errors = validate_password_strength("Password123", "Password123", "new_password", "confirm_password")
    assert errors == {}


def test_validate_password_strength_empty():
    """Empty password produces required error."""
    errors = validate_password_strength("", None, "password")
    assert "password" in errors
    assert errors["password"] == ["Password is required"]


def test_validate_password_strength_too_short():
    """Less than 8 chars produces min length error."""
    errors = validate_password_strength("short", None, "password")
    assert "password" in errors
    assert errors["password"] == ["Password must be at least 8 characters."]


def test_validate_password_strength_confirm_mismatch():
    """Mismatched confirmation produces confirmation error."""
    errors = validate_password_strength("Password123", "DifferentPass", "password", "password_confirm")
    assert "password_confirm" in errors
    assert errors["password_confirm"] == ["Password confirmation does not match"]


def test_validate_password_strength_confirm_empty():
    """Empty confirmation when field expected produces confirmation error."""
    errors = validate_password_strength("Password123", "", "password", "password_confirm")
    assert "password_confirm" in errors
    assert errors["password_confirm"] == ["Password confirmation is required"]

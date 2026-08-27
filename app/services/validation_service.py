"""
WeCare — Validation Service (STEP 9)

Mirrors helpers/validation:
    normalize_username()
    validate_username()
    validate_password_strength()
"""

import re
from typing import Optional


def normalize_username(username: str) -> str:
    """
    Route: normalize_username() — validation L3-9
    """
    username = username.strip()
    username = re.sub(r'\s+', ' ', username)
    return username.lower()


def validate_username(username: str) -> dict:
    """
    Route: validate_username() — validation L11-51

    Returns: {"valid": bool, "username": str, "message": str|None}
    """
    username = normalize_username(username)

    if username == '':
        return {"valid": False, "username": username, "message": "Username is required"}

    if len(username) < 3:
        return {"valid": False, "username": username, "message": "Username must be at least 3 characters"}

    if len(username) > 30:
        return {"valid": False, "username": username, "message": "Username must not exceed 30 characters"}

    if not re.match(r'^[a-z0-9_.]+$', username):
        return {"valid": False, "username": username, "message": "Username may only contain letters, numbers, underscore and dot"}

    return {"valid": True, "username": username, "message": None}


def username_error_response(message: str = "This username is already in use") -> dict:
    """
    Route: username_error_response() — validation L87-92
    """
    return {"username": [message]}


def validate_password_strength(
    password: str,
    confirm: Optional[str] = None,
    password_field: str = "password",
    confirm_field: Optional[str] = None,
) -> dict:
    """
    Route: validate_password_strength() — validation L94-116

    Returns error dict (empty = valid).
    """
    password = str(password)
    errors: dict = {}

    if password == "":
        errors[password_field] = ["Password is required"]
    elif len(password) < 8:
        errors[password_field] = ["Password must be at least 8 characters."]

    if confirm_field is not None:
        confirm = str(confirm or "")
        if confirm == "":
            errors[confirm_field] = ["Password confirmation is required"]
        elif password != confirm:
            errors[confirm_field] = ["Password confirmation does not match"]

    return errors

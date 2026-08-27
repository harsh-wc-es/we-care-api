"""
WeCare — User Profile Endpoint Tests

Tests GET/POST/PATCH/DELETE /api/v1/auth/profile.
"""

import io
import pytest
from tests.conftest import make_auth_headers


def test_get_profile_family(client, test_user):
    headers = make_auth_headers(test_user)
    res = client.get("/api/v1/auth/profile", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == "Profile retrieved"
    assert body["data"]["email"] == test_user["email"]
    assert body["data"]["role"] == "family"
    assert "password" not in body["data"]
    assert "reset_token" not in body["data"]


def test_get_profile_caretaker(client, caretaker_user):
    headers = make_auth_headers(caretaker_user)
    res = client.get("/api/v1/auth/profile", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["role"] == "caretaker"
    assert body["data"]["is_available"] is True


def test_update_profile_json(client, test_user):
    headers = make_auth_headers(test_user)
    new_username = f"upd_{test_user['username']}"[:25]
    res = client.post(
        "/api/v1/auth/profile",
        json={"username": new_username, "phone_number": "9123456789"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == "Profile updated successfully"
    assert body["data"]["username"] == new_username
    assert body["data"]["phone_number"] == "9123456789"


def test_update_profile_with_avatar_upload(client, test_user):
    headers = make_auth_headers(test_user)
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    files = {"profile_picture": ("avatar.png", io.BytesIO(fake_png), "image/png")}
    data = {"username": f"img_{test_user['username']}"[:25]}

    res = client.post("/api/v1/auth/profile", data=data, files=files, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "uploads/profiles/" in body["data"]["profile_picture"]
    assert "uploads/profiles/" in body["data"]["profile_picture_url"]


def test_deactivate_profile(client, test_user):
    headers = make_auth_headers(test_user)
    res = client.delete("/api/v1/auth/profile", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == "Account deactivated successfully"

    # Subsequent profile call should fail with 401/403 or inactive
    res2 = client.get("/api/v1/auth/profile", headers=headers)
    assert res2.status_code in [401, 403]

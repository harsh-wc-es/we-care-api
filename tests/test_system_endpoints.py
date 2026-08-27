"""
WeCare — System Diagnostics Endpoints Test Suite (Part 11)

Tests System diagnostics endpoint:
- GET /api/v1/system/db_diagnostics (+  alias)
  - Strict APP_DEBUG gate (404 when False, 200 when True)
  - Database connectivity probe
  - users table and admin user probe
  - Zero raw credential leakage
"""

import pytest
from app.core.config import get_settings


def test_db_diagnostics_debug_disabled_returns_404(client, monkeypatch):
    # Ensure APP_DEBUG is False
    settings = get_settings()
    monkeypatch.setattr(settings, "APP_DEBUG", False)

    # Canonical route
    resp = client.get("/api/v1/system/db_diagnostics")
    assert resp.status_code == 404
    assert resp.json()["message"] == "Not found"

    # Legacy  alias
    resp_php = client.get("/api/v1/system/db_diagnostics")
    assert resp_php.status_code == 404
    assert resp_php.json()["message"] == "Not found"


def test_db_diagnostics_debug_enabled_success(client, monkeypatch, db):
    # Enable APP_DEBUG
    settings = get_settings()
    monkeypatch.setattr(settings, "APP_DEBUG", True)

    resp = client.get("/api/v1/system/db_diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]

    # Verify DB section
    assert "db" in data
    assert data["db"]["host"] != ""
    assert data["db"]["port"] != ""
    assert "name" in data["db"]
    assert "user" in data["db"]
    assert "password_configured" in data["db"]
    assert isinstance(data["db"]["password_configured"], bool)
    assert "connected" in data["db"]

    # Verify no raw password in response body
    resp_text = resp.text
    if settings.DB_PASS:
        assert settings.DB_PASS not in resp_text

    # Verify schema section
    assert "schema" in data
    assert "users_table_exists" in data["schema"]
    assert "admin_user_exists" in data["schema"]

    # Verify legacy  alias
    resp_php = client.get("/api/v1/system/db_diagnostics")
    assert resp_php.status_code == 200
    assert resp_php.json()["success"] is True

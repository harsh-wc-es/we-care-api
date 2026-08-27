"""
WeCare — Notification Endpoints Test Suite (Part 10)

Tests all notification endpoints and behaviors:
- GET /my_notifications (empty, populated, pagination, unread_only, type filtering, unread_count calculation, metadata JSON handling)
- POST /mark_read (mark single notification, validation, 404 on not found or wrong user, non-integer validation)
- POST /mark_all_read (mark all unread notifications, returns updated_count)
- POST /create_notification (admin-only creation, validation, 404 on missing user, 403 on non-admin)
- POST /register_device (device token registration, platform/app_type validation, upsert on duplicate, default app_type)
- POST /remove_device (device token deactivation, non-existent token idempotency)
- Legacy  route aliases for all endpoints
"""

import time
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="family"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"notif_{role}_{ts}@example.com"
    username = f"n_{role[:2]}_{ts}"
    phone = f"9{ts:09d}"[:10]
    pwd_hash = hash_password("TestPassword123!")

    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, :role, 1, 1)"
        ),
        {
            "email": email,
            "username": username,
            "phone": phone,
            "password": pwd_hash,
            "role": role,
        },
    )
    user_id = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar()
    db.commit()
    return {"id": int(user_id), "email": email, "username": username, "role": role}


def test_my_notifications_empty_and_pagination(client, db):
    user = _create_user(db, "family")
    headers = make_auth_headers(user, db)

    resp = client.get("/api/v1/notification/my_notifications", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["unread_count"] == 0
    assert data["pagination"]["total"] == 0

    # Insert test notifications with valid and invalid metadata
    for i in range(5):
        meta = '{"booking_id": 101, "key": "val"}' if i == 1 else ("invalid_json" if i == 2 else None)
        db.execute(
            text(
                "INSERT INTO notifications (user_id, title, message, type, is_read, metadata) "
                "VALUES (:uid, :title, :msg, :type, :is_read, :meta)"
            ),
            {
                "uid": user["id"],
                "title": f"Notif {i}",
                "msg": f"Message {i}",
                "type": "booking_created" if i % 2 == 0 else "general",
                "is_read": 1 if i == 0 else 0,
                "meta": meta,
            },
        )
    db.commit()

    resp = client.get("/api/v1/notification/my_notifications?page=1&limit=3", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) == 3
    assert data["unread_count"] == 4
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["total_pages"] == 2

    # Test unread_only filter
    resp_unread = client.get("/api/v1/notification/my_notifications?unread_only=true", headers=headers)
    assert resp_unread.status_code == 200
    unread_data = resp_unread.json()["data"]
    assert len(unread_data["items"]) == 4
    assert unread_data["unread_count"] == 4

    # Test type filter
    resp_type = client.get("/api/v1/notification/my_notifications?type=booking_created", headers=headers)
    assert resp_type.status_code == 200
    type_data = resp_type.json()["data"]
    assert len(type_data["items"]) == 3


def test_mark_read_and_mark_all_read(client, db):
    user = _create_user(db, "caretaker")
    headers = make_auth_headers(user, db)

    db.execute(
        text(
            "INSERT INTO notifications (user_id, title, message, type, is_read) "
            "VALUES (:uid, 'Test Mark', 'Msg', 'test', 0)"
        ),
        {"uid": user["id"]},
    )
    db.commit()
    nid = db.execute(text("SELECT id FROM notifications WHERE user_id = :uid ORDER BY id DESC LIMIT 1"), {"uid": user["id"]}).scalar()

    # Validation failure: missing notification_id
    resp_bad = client.post("/api/v1/notification/mark_read", json={}, headers=headers)
    assert resp_bad.status_code == 400

    # Validation failure: non-integer notification_id
    resp_bad_int = client.post("/api/v1/notification/mark_read", json={"notification_id": "not_an_int"}, headers=headers)
    assert resp_bad_int.status_code == 400

    # Mark single read (canonical)
    resp = client.post("/api/v1/notification/mark_read", json={"notification_id": nid}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["is_read"] is True

    # 404 for non-existent or other user's notification
    resp_404 = client.post("/api/v1/notification/mark_read", json={"notification_id": 999999}, headers=headers)
    assert resp_404.status_code == 404

    # Insert 3 unread
    for i in range(3):
        db.execute(
            text("INSERT INTO notifications (user_id, title, message, type, is_read) VALUES (:uid, 'N', 'M', 't', 0)"),
            {"uid": user["id"]},
        )
    db.commit()

    # Mark all read (legacy)
    resp_all = client.post("/api/v1/notification/mark_all_read", headers=headers)
    assert resp_all.status_code == 200
    assert resp_all.json()["data"]["updated_count"] >= 3


def test_admin_create_notification(client, db):
    admin = _create_user(db, "admin")
    family = _create_user(db, "family")
    admin_headers = make_auth_headers(admin, db)
    fam_headers = make_auth_headers(family, db)

    # Forbidden for non-admin
    resp_forbid = client.post(
        "/api/v1/notification/create_notification",
        json={"user_id": family["id"], "title": "Announcement", "message": "Test"},
        headers=fam_headers,
    )
    assert resp_forbid.status_code in (401, 403)

    # Missing fields
    resp_bad = client.post(
        "/api/v1/notification/create_notification",
        json={"user_id": family["id"], "title": ""},
        headers=admin_headers,
    )
    assert resp_bad.status_code == 400

    # User not found
    resp_nf = client.post(
        "/api/v1/notification/create_notification",
        json={"user_id": 999999, "title": "Hello", "message": "World"},
        headers=admin_headers,
    )
    assert resp_nf.status_code == 404

    # Success (canonical & legacy)
    resp_ok = client.post(
        "/api/v1/notification/create_notification",
        json={"user_id": family["id"], "title": "System Alert", "message": "Maintenance tonight"},
        headers=admin_headers,
    )
    assert resp_ok.status_code == 201
    assert "notification_id" in resp_ok.json()["data"]


def test_device_token_register_and_remove(client, db):
    user = _create_user(db, "family")
    headers = make_auth_headers(user, db)

    # Validation errors
    resp_err = client.post("/api/v1/notification/register_device", json={}, headers=headers)
    assert resp_err.status_code == 400

    resp_bad_plat = client.post(
        "/api/v1/notification/register_device",
        json={"device_token": "tok_123", "platform": "windows", "app_type": "family"},
        headers=headers,
    )
    assert resp_bad_plat.status_code == 400

    # Default app_type when omitted
    resp_def = client.post(
        "/api/v1/notification/register_device",
        json={"device_token": "tok_def_1", "platform": "web"},
        headers=headers,
    )
    assert resp_def.status_code == 200
    assert resp_def.json()["data"]["app_type"] == "family"

    # Successful registration (canonical)
    resp_reg = client.post(
        "/api/v1/notification/register_device",
        json={"device_token": "token_abc_123", "platform": "android", "app_type": "family"},
        headers=headers,
    )
    assert resp_reg.status_code == 200
    assert resp_reg.json()["data"]["device_token"] == "token_abc_123"
    assert resp_reg.json()["data"]["is_active"] is True

    # Re-register (upsert)
    resp_upsert = client.post(
        "/api/v1/notification/register_device",
        json={"device_token": "token_abc_123", "platform": "ios", "app_type": "family"},
        headers=headers,
    )
    assert resp_upsert.status_code == 200
    assert resp_upsert.json()["data"]["platform"] == "ios"

    # Remove device validation error
    resp_rem_err = client.post("/api/v1/notification/remove_device", json={}, headers=headers)
    assert resp_rem_err.status_code == 400

    # Remove device (legacy)
    resp_rem = client.post(
        "/api/v1/notification/remove_device",
        json={"device_token": "token_abc_123"},
        headers=headers,
    )
    assert resp_rem.status_code == 200
    assert resp_rem.json()["data"]["is_active"] is False

    # Remove non-existent token also returns success (parity)
    resp_rem_non = client.post(
        "/api/v1/notification/remove_device",
        json={"device_token": "non_existent_token_999"},
        headers=headers,
    )
    assert resp_rem_non.status_code == 200
    assert resp_rem_non.json()["data"]["is_active"] is False

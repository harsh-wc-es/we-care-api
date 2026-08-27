"""
WeCare — Part 12D Admin Audit Logs & Notification Dispatch Test Suite

Tests all 5 Admin Part 12D endpoints and business rules:
1. GET  /api/v1/admin/audit_logs (+  alias)
2. GET  /api/v1/admin/notification_history (+  alias)
3. GET  /api/v1/admin/notifications/logs (+  alias)
4. GET  /api/v1/admin/notifications/targets (+  alias)
5. POST /api/v1/admin/notifications/send (+  alias)
"""

import json
import time
import pytest
from datetime import datetime
from sqlalchemy import text
from unittest.mock import patch

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="family", is_active=1):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"adm12d_{role}_{ts}@example.com"
    username = f"u12d_{role[:2]}_{ts}"
    phone = f"9{ts:09d}"[:10]
    pwd_hash = hash_password("TestPassword123!")

    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, :role, 1, :is_active)"
        ),
        {
            "email": email,
            "username": username,
            "phone": phone,
            "password": pwd_hash,
            "role": role,
            "is_active": is_active,
        },
    )
    user_id = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar()
    db.commit()
    return {"id": int(user_id), "email": email, "username": username, "phone": phone, "role": role}


def _create_device_token(db, user_id, device_token, is_active=1, platform="android", app_type="family"):
    db.execute(
        text(
            "INSERT INTO notification_device_tokens (user_id, device_token, platform, app_type, is_active, last_used_at) "
            "VALUES (:uid, :token, :platform, :app_type, :active, NOW())"
        ),
        {
            "uid": user_id,
            "token": device_token,
            "platform": platform,
            "app_type": app_type,
            "active": is_active,
        },
    )
    db.commit()


# ============================================================================
# 1. AUTH & RBAC MATRIX
# ============================================================================

def test_admin_part12d_auth_and_rbac(client, db):
    admin = _create_user(db, "admin")
    family = _create_user(db, "family")
    caretaker = _create_user(db, "caretaker")

    admin_h = make_auth_headers(admin, db)
    fam_h = make_auth_headers(family, db)
    car_h = make_auth_headers(caretaker, db)

    endpoints = [
        ("GET", "/api/v1/admin/audit_logs", {}),
        ("GET", "/api/v1/admin/audit_logs", {}),
        ("GET", "/api/v1/admin/notification_history", {}),
        ("GET", "/api/v1/admin/notification_history", {}),
        ("GET", "/api/v1/admin/notifications/logs", {}),
        ("GET", "/api/v1/admin/notifications/logs", {}),
        ("GET", "/api/v1/admin/notifications/targets?role=family", {}),
        ("GET", "/api/v1/admin/notifications/targets?role=family", {}),
        ("POST", "/api/v1/admin/notifications/send", {"send_type": "all_users", "title": "T", "body": "B"}),
        ("POST", "/api/v1/admin/notifications/send", {"send_type": "all_users", "title": "T", "body": "B"}),
    ]

    for method, path, payload in endpoints:
        # 1. No auth -> 401
        if method == "GET":
            r_no_auth = client.get(path)
        else:
            r_no_auth = client.post(path, json=payload)
        assert r_no_auth.status_code == 401, f"{path} without auth must return 401"

        # 2. Family token -> 403
        if method == "GET":
            r_fam = client.get(path, headers=fam_h)
        else:
            r_fam = client.post(path, json=payload, headers=fam_h)
        assert r_fam.status_code == 403, f"{path} with family token must return 403"

        # 3. Caretaker token -> 403
        if method == "GET":
            r_car = client.get(path, headers=car_h)
        else:
            r_car = client.post(path, json=payload, headers=car_h)
        assert r_car.status_code == 403, f"{path} with caretaker token must return 403"

        # 4. Admin token -> Authorized (200 OK)
        if method == "GET":
            r_adm = client.get(path, headers=admin_h)
        else:
            r_adm = client.post(path, json=payload, headers=admin_h)
        assert r_adm.status_code == 200, f"{path} with admin token must return 200, got {r_adm.status_code}: {r_adm.text}"


# ============================================================================
# 2. AUDIT LOGS PAGINATION & DATA
# ============================================================================

def test_admin_audit_logs_pagination_and_data(client, db):
    admin = _create_user(db, "admin")
    admin_h = make_auth_headers(admin, db)

    # Insert 3 test audit logs
    for i in range(3):
        db.execute(
            text(
                "INSERT INTO admin_audit_logs (admin_user_id, action, entity_type, entity_id, old_values, new_values, ip_address, user_agent) "
                "VALUES (:uid, :act, 'test_entity', :eid, '{\"k\": \"v1\"}', '{\"k\": \"v2\"}', '127.0.0.1', 'pytest')"
            ),
            {"uid": admin["id"], "act": f"test_action_{i}", "eid": 100 + i},
        )
    db.commit()

    # 1. Default pagination (page=1, limit=50)
    r = client.get("/api/v1/admin/audit_logs", headers=admin_h)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["message"] == "Audit logs retrieved"
    data = body["data"]
    assert "page" in data and data["page"] == 1
    assert "limit" in data and data["limit"] == 50
    assert "total" in data and data["total"] >= 3
    assert "total_pages" in data
    assert "items" in data and len(data["items"]) >= 3

    # Check fields in first item
    first = data["items"][0]
    assert "id" in first
    assert "admin_user_id" in first
    assert "action" in first
    assert "target_type" in first
    assert "target_id" in first
    assert "entity_type" in first
    assert "entity_id" in first
    assert "old_values" in first
    assert "new_values" in first
    assert "ip_address" in first
    assert "user_agent" in first
    assert "created_at" in first
    assert "admin_username" in first
    assert first["admin_username"] == admin["username"]

    # 2. Custom page and limit
    r_custom = client.get("/api/v1/admin/audit_logs?page=1&limit=2", headers=admin_h)
    assert r_custom.status_code == 200
    assert len(r_custom.json()["data"]["items"]) == 2
    assert r_custom.json()["data"]["limit"] == 2

    # 3. Descending ID ordering
    items = r.json()["data"]["items"]
    ids = [item["id"] for item in items]
    assert ids == sorted(ids, reverse=True)


# ============================================================================
# 3. NOTIFICATION HISTORY FILTERS
# ============================================================================

def test_admin_notification_history_filters(client, db):
    admin = _create_user(db, "admin")
    family = _create_user(db, "family")
    caretaker = _create_user(db, "caretaker")
    admin_h = make_auth_headers(admin, db)

    # Insert notifications for family and caretaker
    db.execute(
        text(
            "INSERT INTO notifications (user_id, title, message, type, related_type, is_read) "
            "VALUES (:uid, 'Family Notif', 'Hello Family', 'family_test', 'test', 0)"
        ),
        {"uid": family["id"]},
    )
    db.execute(
        text(
            "INSERT INTO notifications (user_id, title, message, type, related_type, is_read) "
            "VALUES (:uid, 'Caretaker Notif', 'Hello Caretaker', 'caretaker_test', 'test', 0)"
        ),
        {"uid": caretaker["id"]},
    )
    db.commit()

    # 1. Default history (no filters)
    r = client.get("/api/v1/admin/notification_history", headers=admin_h)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["message"] == "Notification history retrieved"
    assert len(body["data"]["items"]) >= 2

    # 2. Target role filter = family
    r_fam = client.get("/api/v1/admin/notification_history?target_role=family", headers=admin_h)
    assert r_fam.status_code == 200
    for item in r_fam.json()["data"]["items"]:
        assert item["recipient_role"] == "family"

    # 3. Target role filter = caretaker
    r_car = client.get("/api/v1/admin/notification_history?target_role=caretaker", headers=admin_h)
    assert r_car.status_code == 200
    for item in r_car.json()["data"]["items"]:
        assert item["recipient_role"] == "caretaker"

    # 4. Invalid target_role -> 400
    r_inv_role = client.get("/api/v1/admin/notification_history?target_role=invalid_role", headers=admin_h)
    assert r_inv_role.status_code == 400
    assert r_inv_role.json()["message"] == "Invalid target_role"

    # 5. Type filter -> 400 with exact legacy error
    r_type = client.get("/api/v1/admin/notification_history?type=booking_created", headers=admin_h)
    assert r_type.status_code == 400
    assert r_type.json()["message"] == "Notification type filter is not available in the current schema"
    assert r_type.json()["errors"] == {"type": ["Remove type filter or add a notifications.type column"]}


# ============================================================================
# 4. ADMIN NOTIFICATION LOGS & METADATA UNPACKING
# ============================================================================

def test_admin_notifications_logs_metadata_unpacking(client, db):
    admin = _create_user(db, "admin")
    family = _create_user(db, "family")
    caretaker = _create_user(db, "caretaker")
    admin_h = make_auth_headers(admin, db)

    # 1. Insert admin_push with valid json metadata
    meta1 = {"send_type": "single_user", "push_status": "sent", "sent_count": 1}
    db.execute(
        text(
            "INSERT INTO notifications (user_id, title, message, type, metadata, is_read) "
            "VALUES (:uid, 'Push Title 1', 'Push Body 1', 'admin_push', :meta, 0)"
        ),
        {"uid": family["id"], "meta": json.dumps(meta1)},
    )

    # 2. Insert admin_push with non-dict / invalid metadata
    db.execute(
        text(
            "INSERT INTO notifications (user_id, title, message, type, metadata, is_read) "
            "VALUES (:uid, 'Push Title 2', 'Push Body 2', 'admin_push', 'invalid json string', 0)"
        ),
        {"uid": caretaker["id"]},
    )

    # 3. Insert ordinary user notification (type != 'admin_push') - must NOT be returned
    db.execute(
        text(
            "INSERT INTO notifications (user_id, title, message, type, metadata, is_read) "
            "VALUES (:uid, 'Ordinary Title', 'Ordinary Body', 'booking_reminder', NULL, 0)"
        ),
        {"uid": family["id"]},
    )
    db.commit()

    # Query logs
    r = client.get("/api/v1/admin/notifications/logs", headers=admin_h)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["message"] == "Notification logs fetched successfully"
    data = body["data"]

    # Quirk check: items and logs must both be present and identical
    assert "items" in data and "logs" in data
    assert data["items"] == data["logs"]

    # Verify admin_push only
    for item in data["items"]:
        assert item["type"] == "admin_push"
        assert "sent_status" in item

    # Check first item sent_status and metadata
    push_items = [it for it in data["items"] if it["user_id"] == family["id"] and it["title"] == "Push Title 1"]
    assert len(push_items) >= 1
    assert push_items[0]["sent_status"] == "sent"
    assert push_items[0]["metadata"] == meta1

    # Check invalid metadata item fallback
    invalid_meta_items = [it for it in data["items"] if it["user_id"] == caretaker["id"] and it["title"] == "Push Title 2"]
    assert len(invalid_meta_items) >= 1
    assert invalid_meta_items[0]["sent_status"] == "saved"
    assert invalid_meta_items[0]["metadata"] is None

    # Role filter 'user' alias to 'family'
    r_user_alias = client.get("/api/v1/admin/notifications/logs?target_role=user", headers=admin_h)
    assert r_user_alias.status_code == 200
    for item in r_user_alias.json()["data"]["items"]:
        assert item["recipient_role"] == "family"

    # Invalid target role -> 400
    r_inv = client.get("/api/v1/admin/notifications/logs?target_role=invalid_role", headers=admin_h)
    assert r_inv.status_code == 400
    assert r_inv.json()["message"] == "Invalid target_role"


# ============================================================================
# 5. NOTIFICATION TARGETS SEARCH
# ============================================================================

def test_admin_notifications_targets_search(client, db):
    admin = _create_user(db, "admin")
    family = _create_user(db, "family")
    inactive_family = _create_user(db, "family", is_active=0)
    caretaker = _create_user(db, "caretaker")
    admin_h = make_auth_headers(admin, db)

    # 1. Missing role -> 400
    r_missing_role = client.get("/api/v1/admin/notifications/targets", headers=admin_h)
    assert r_missing_role.status_code == 400
    assert r_missing_role.json()["message"] == "Role must be family, user, or caretaker"
    assert r_missing_role.json()["errors"] == {"role": ["Supported values are family, user, and caretaker"]}

    # 2. Invalid role -> 400
    r_inv_role = client.get("/api/v1/admin/notifications/targets?role=admin", headers=admin_h)
    assert r_inv_role.status_code == 400

    # 3. Query role=family (data is top-level raw array - legacy quirk)
    r_fam = client.get(f"/api/v1/admin/notifications/targets?role=family&search={family['username']}", headers=admin_h)
    assert r_fam.status_code == 200
    body_fam = r_fam.json()
    assert body_fam["success"] is True
    assert body_fam["message"] == "Notification targets fetched successfully"
    assert isinstance(body_fam["data"], list)
    fam_ids = [t["id"] for t in body_fam["data"]]
    assert family["id"] in fam_ids

    # Verify inactive family is not found even with direct search
    r_inact = client.get(f"/api/v1/admin/notifications/targets?role=family&search={inactive_family['username']}", headers=admin_h)
    assert r_inact.status_code == 200
    assert len(r_inact.json()["data"]) == 0

    # 4. Role 'user' aliases to 'family'
    r_user = client.get(f"/api/v1/admin/notifications/targets?role=user&search={family['username']}", headers=admin_h)
    assert r_user.status_code == 200
    assert isinstance(r_user.json()["data"], list)
    user_ids = [t["id"] for t in r_user.json()["data"]]
    assert family["id"] in user_ids

    # 5. Search by username
    r_search = client.get(f"/api/v1/admin/notifications/targets?role=family&search={family['username']}", headers=admin_h)
    assert r_search.status_code == 200
    search_ids = [t["id"] for t in r_search.json()["data"]]
    assert family["id"] in search_ids

    # 6. Search by email
    r_email = client.get(f"/api/v1/admin/notifications/targets?role=family&search={family['email']}", headers=admin_h)
    assert r_email.status_code == 200
    email_ids = [t["id"] for t in r_email.json()["data"]]
    assert family["id"] in email_ids


# ============================================================================
# 6. ADMIN NOTIFICATIONS SEND VALIDATION & LIFECYCLE
# ============================================================================

def test_admin_notifications_send_validation_and_lifecycle(client, db):
    admin = _create_user(db, "admin")
    family = _create_user(db, "family")
    caretaker = _create_user(db, "caretaker")
    admin_h = make_auth_headers(admin, db)

    # Register device tokens
    _create_device_token(db, family["id"], f"dtoken_fam_{int(time.time())}")
    _create_device_token(db, caretaker["id"], f"dtoken_car_{int(time.time())}")

    # ── VALIDATION TESTS (Must return HTTP 422 - Legacy quirk) ──
    # 1. Invalid send_type
    r1 = client.post("/api/v1/admin/notifications/send", json={"send_type": "unknown", "title": "T", "body": "B"}, headers=admin_h)
    assert r1.status_code == 422
    assert "send_type" in r1.json()["errors"]

    # 2. Empty title
    r2 = client.post("/api/v1/admin/notifications/send", json={"send_type": "all_users", "title": "", "body": "B"}, headers=admin_h)
    assert r2.status_code == 422
    assert "title" in r2.json()["errors"]

    # 3. Title > 120 chars
    r3 = client.post("/api/v1/admin/notifications/send", json={"send_type": "all_users", "title": "A" * 121, "body": "B"}, headers=admin_h)
    assert r3.status_code == 422
    assert "title" in r3.json()["errors"]

    # 4. Empty body/message
    r4 = client.post("/api/v1/admin/notifications/send", json={"send_type": "all_users", "title": "Title", "body": ""}, headers=admin_h)
    assert r4.status_code == 422
    assert "body" in r4.json()["errors"]

    # 5. Body > 500 chars
    r5 = client.post("/api/v1/admin/notifications/send", json={"send_type": "all_users", "title": "Title", "body": "M" * 501}, headers=admin_h)
    assert r5.status_code == 422
    assert "body" in r5.json()["errors"]

    # 6. Single send without target_user_id
    r6 = client.post("/api/v1/admin/notifications/send", json={"send_type": "single_user", "title": "Title", "body": "Message"}, headers=admin_h)
    assert r6.status_code == 422
    assert "target_user_id" in r6.json()["errors"]

    # 7. Invalid type (> 60 chars)
    r7 = client.post("/api/v1/admin/notifications/send", json={"send_type": "all_users", "title": "Title", "body": "Message", "type": "X" * 61}, headers=admin_h)
    assert r7.status_code == 422
    assert "type" in r7.json()["errors"]

    # 8. Single target not found / wrong role -> 404
    r8 = client.post("/api/v1/admin/notifications/send", json={"send_type": "single_user", "target_user_id": 99999999, "title": "Title", "body": "Message"}, headers=admin_h)
    assert r8.status_code == 404
    assert r8.json()["message"] == "Target user was not found for this send type"

    # ── LIFECYCLE & DISPATCH MODES ──
    # 9. single_user dispatch (FCM simulated / unconfigured)
    with patch("app.services.admin_system_service.fcm_http_v1_is_configured", return_value=True), \
         patch("app.services.admin_system_service.fcm_http_v1_send", return_value={"success": True, "message_id": "msg-123"}):
        r_single = client.post(
            "/api/v1/admin/notifications/send",
            json={"send_type": "single_user", "target_user_id": family["id"], "title": "Important Update", "body": "Your appointment is confirmed"},
            headers=admin_h,
        )
        assert r_single.status_code == 200
        b_single = r_single.json()
        assert b_single["success"] is True
        assert b_single["message"] == "Notification processed successfully"
        data_s = b_single["data"]
        assert data_s["send_type"] == "single_user"
        assert data_s["total_targets"] == 1
        assert data_s["sent_count"] == 1
        assert len(data_s["notification_ids"]) == 1

        # Check DB notification record and metadata
        nid = data_s["notification_ids"][0]
        n_row = db.execute(text("SELECT * FROM notifications WHERE id = :id"), {"id": nid}).mappings().first()
        assert n_row is not None
        assert n_row["user_id"] == family["id"]
        assert n_row["title"] == "Important Update"
        assert n_row["message"] == "Your appointment is confirmed"
        assert n_row["type"] == "admin_push"
        meta = json.loads(n_row["metadata"])
        assert meta["push_status"] == "sent"
        assert meta["sent_count"] == 1

    # 10. single_caretaker dispatch with invalid token handling
    with patch("app.services.admin_system_service.fcm_http_v1_is_configured", return_value=True), \
         patch("app.services.admin_system_service.fcm_http_v1_send", return_value={"success": False, "invalid_token": True, "message": "Unregistered token"}):
        r_car_send = client.post(
            "/api/v1/admin/notifications/send",
            json={"send_type": "single_caretaker", "target_user_id": caretaker["id"], "title": "Shift Alert", "message": "New shift available"},
            headers=admin_h,
        )
        assert r_car_send.status_code == 200
        data_c = r_car_send.json()["data"]
        assert data_c["failed_count"] == 1
        assert data_c["invalid_tokens_removed"] == 1

        # Verify token was deactivated in DB
        db.commit()
        t_row = db.execute(text("SELECT is_active FROM notification_device_tokens WHERE user_id = :uid"), {"uid": caretaker["id"]}).scalar()
        assert t_row == 0

    # 11. broadcast dispatch (Firebase unconfigured fallback)
    with patch("app.services.admin_system_service.fcm_http_v1_is_configured", return_value=False):
        r_bcast = client.post(
            "/api/v1/admin/notifications/send",
            json={"send_type": "broadcast", "title": "System Notice", "body": "Scheduled maintenance tonight"},
            headers=admin_h,
        )
        assert r_bcast.status_code == 200
        data_b = r_bcast.json()["data"]
        assert data_b["send_type"] == "broadcast"
        assert data_b["total_targets"] >= 2
        assert len(data_b["errors"]) >= 1
        assert "Firebase HTTP v1 service account is not configured on the backend" in data_b["errors"][0]["message"]


# ============================================================================
# 7. CANONICAL VS .ALIAS PARITY
# ============================================================================

def test_admin_part12d_canonical_vs_alias_parity(client, db):
    admin = _create_user(db, "admin")
    admin_h = make_auth_headers(admin, db)

    pairs = [
        ("GET", "/api/v1/admin/audit_logs", "/api/v1/admin/audit_logs", None),
        ("GET", "/api/v1/admin/notification_history", "/api/v1/admin/notification_history", None),
        ("GET", "/api/v1/admin/notifications/logs", "/api/v1/admin/notifications/logs", None),
        ("GET", "/api/v1/admin/notifications/targets?role=family", "/api/v1/admin/notifications/targets?role=family", None),
        ("POST", "/api/v1/admin/notifications/send", "/api/v1/admin/notifications/send", {"send_type": "all_users", "title": "Parity Test", "body": "Checking parity"}),
    ]

    for method, can_url, alias_url, payload in pairs:
        if method == "GET":
            r_can = client.get(can_url, headers=admin_h)
            r_alias = client.get(alias_url, headers=admin_h)
        else:
            r_can = client.post(can_url, json=payload, headers=admin_h)
            r_alias = client.post(alias_url, json=payload, headers=admin_h)

        assert r_can.status_code == r_alias.status_code == 200, f"{can_url} vs {alias_url} status code mismatch"
        b_can = r_can.json()
        b_alias = r_alias.json()
        assert b_can["success"] == b_alias["success"]
        assert b_can["message"] == b_alias["message"]

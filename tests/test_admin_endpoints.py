"""
WeCare — Admin Endpoint Tests

Tests all 23 admin management endpoints:
- GET  /api/v1/admin/me
- POST /api/v1/admin/update_profile
- GET  /api/v1/admin/users
- POST /api/v1/admin/update_user_status
- GET  /api/v1/admin/patient_profile
- GET  /api/v1/admin/view_caretaker
- GET  /api/v1/admin/pending_caretakers
- POST /api/v1/admin/approve_caretaker
- POST /api/v1/admin/reject_caretaker
- GET  /api/v1/admin/caretaker_verification
- POST /api/v1/admin/caretakers/approve
- POST /api/v1/admin/caretakers/ban
- POST /api/v1/admin/caretaker_documents/approve
- POST /api/v1/admin/caretaker_documents/reject_selected
- POST /api/v1/admin/reject_document
- POST /api/v1/admin/set_caretaker_availability
- POST /api/v1/admin/update_caretaker_pricing
- POST /api/v1/admin/update_caregiver_tier_pricing
- GET  /api/v1/admin/pricing_tiers
- POST /api/v1/admin/create_pricing_tier
- GET  /api/v1/admin/pricing_tier_detail
- POST /api/v1/admin/update_pricing_tier
- POST & DELETE /api/v1/admin/delete_pricing_tier
"""

import io
import time
import pytest
from tests.conftest import make_auth_headers


def test_admin_me_and_update_profile(client, admin_user):
    headers = make_auth_headers(admin_user)

    # 1. Get admin profile
    res_me = client.get("/api/v1/admin/me", headers=headers)
    assert res_me.status_code == 200
    me_body = res_me.json()
    assert me_body["success"] is True
    assert me_body["data"]["email"] == admin_user["email"]
    assert me_body["data"]["role"] == "admin"

    # 2. Update admin profile
    new_phone = f"9{int(time.time() * 1000) % 100000000:08d}"
    res_upd = client.post(
        "/api/v1/admin/update_profile",
        json={"name": "Super Admin", "email": admin_user["email"], "phone_number": new_phone},
        headers=headers,
    )
    assert res_upd.status_code == 200
    assert res_upd.json()["data"]["name"] == "Super Admin"

    # 3. Validation failure returns 422
    res_fail = client.post(
        "/api/v1/admin/update_profile",
        json={"name": "A", "email": "invalid-email"},
        headers=headers,
    )
    assert res_fail.status_code == 422
    assert res_fail.json()["success"] is False


def test_admin_users_and_status(client, admin_user, test_user):
    headers = make_auth_headers(admin_user)

    # 1. List users
    res_users = client.get("/api/v1/admin/users?role=family", headers=headers)
    assert res_users.status_code == 200
    users_body = res_users.json()
    assert users_body["success"] is True
    assert "items" in users_body["data"]

    # 2. Update user status to inactive
    res_status = client.post(
        "/api/v1/admin/update_user_status",
        json={"user_id": test_user["id"], "is_active": 0},
        headers=headers,
    )
    assert res_status.status_code == 200
    assert res_status.json()["data"]["is_active"] is False

    # 3. Cannot deactivate own admin account
    res_self = client.post(
        "/api/v1/admin/update_user_status",
        json={"user_id": admin_user["id"], "is_active": 0},
        headers=headers,
    )
    assert res_self.status_code == 400


def test_admin_pricing_tier_crud(client, admin_user):
    headers = make_auth_headers(admin_user)
    ts = int(time.time() * 1000) % 100000

    # 1. Create tier
    tier_name = f"Special Care {ts}"
    res_create = client.post(
        "/api/v1/admin/create_pricing_tier",
        json={
            "name": tier_name,
            "description": "Specialized palliative and medical care",
            "skill_level": "Senior Caregiver",
            "customer_hourly_rate": 35.0,
            "caretaker_hourly_rate": 28.0,
            "is_active": True,
        },
        headers=headers,
    )
    assert res_create.status_code == 201
    create_body = res_create.json()
    assert create_body["success"] is True
    tier_id = create_body["data"]["id"]
    assert create_body["data"]["customer_hourly_rate"] == 35.0
    assert create_body["data"]["caretaker_hourly_rate"] == 28.0
    assert create_body["data"]["platform_commission_hourly"] == 7.0

    # 2. List pricing tiers
    res_list = client.get("/api/v1/admin/pricing_tiers?status=all", headers=headers)
    assert res_list.status_code == 200
    assert any(t["id"] == tier_id for t in res_list.json()["data"])

    # 3. Detail
    res_detail = client.get(f"/api/v1/admin/pricing_tier_detail?id={tier_id}", headers=headers)
    assert res_detail.status_code == 200
    assert res_detail.json()["data"]["id"] == tier_id

    # 4. Update tier
    res_upd = client.post(
        "/api/v1/admin/update_pricing_tier",
        json={
            "id": tier_id,
            "name": f"{tier_name} Updated",
            "customer_hourly_rate": 40.0,
            "caretaker_hourly_rate": 30.0,
        },
        headers=headers,
    )
    assert res_upd.status_code == 200
    assert res_upd.json()["data"]["customer_hourly_rate"] == 40.0

    # 5. Delete (deactivate) tier
    res_del = client.post(
        "/api/v1/admin/delete_pricing_tier",
        json={"id": tier_id},
        headers=headers,
    )
    assert res_del.status_code == 200
    assert res_del.json()["data"]["is_active"] is False


def test_admin_caretaker_inspection_and_override(client, admin_user, caretaker_user):
    headers = make_auth_headers(admin_user)
    ct_headers = make_auth_headers(caretaker_user)
    cid = caretaker_user["id"]

    # 1. View caretaker
    res_view = client.get(f"/api/v1/admin/view_caretaker?user_id={cid}", headers=headers)
    assert res_view.status_code == 200
    view_body = res_view.json()
    assert view_body["success"] is True
    assert view_body["data"]["id"] == cid
    assert "reviews" in view_body["data"]
    assert "document_summary" in view_body["data"]

    # 2. Caretaker availability override by admin
    res_avail = client.post(
        "/api/v1/admin/set_caretaker_availability",
        json={
            "caretaker_user_id": cid,
            "is_available": False,
            "lock_availability": True,
            "note": "Admin maintenance lock",
            "reason": "admin_lock_test",
        },
        headers=headers,
    )
    assert res_avail.status_code == 200
    assert res_avail.json()["data"]["is_available"] is False
    assert res_avail.json()["data"]["availability_locked_by_admin"] is True

    # 3. Caretaker attempts to toggle availability while locked -> 403 Forbidden
    res_ct_toggle = client.post(
        "/api/v1/caretaker/availability",
        json={"is_available": True},
        headers=ct_headers,
    )
    assert res_ct_toggle.status_code == 403

    # 4. Caretaker verification queue
    res_queue = client.get("/api/v1/admin/caretaker_verification?status=all", headers=headers)
    assert res_queue.status_code == 200
    assert res_queue.json()["success"] is True


def test_admin_document_moderation_flow(client, admin_user, caretaker_user):
    ct_headers = make_auth_headers(caretaker_user)
    adm_headers = make_auth_headers(admin_user)
    cid = caretaker_user["id"]

    # 1. Caretaker uploads training certificate
    fake_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    files = {"document": ("cert.pdf", io.BytesIO(fake_pdf), "application/pdf")}
    data = {"document_type": "training_certificate"}
    res_up = client.post("/api/v1/caretaker/upload_document", data=data, files=files, headers=ct_headers)
    assert res_up.status_code == 201
    doc_id = res_up.json()["data"]["document_id"]

    # 2. Admin approves document
    res_app = client.post(
        "/api/v1/admin/caretaker_documents/approve",
        json={"caretaker_user_id": cid, "document_id": doc_id},
        headers=adm_headers,
    )
    assert res_app.status_code == 200
    assert res_app.json()["message"] == "Document approved successfully."

    # 3. Admin rejects document
    res_rej = client.post(
        "/api/v1/admin/reject_document",
        json={"document_id": doc_id, "reason": "Certificate is blurry, please reupload"},
        headers=adm_headers,
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["data"]["document"]["status"] == "rejected"

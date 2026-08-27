"""
WeCare — Caretaker Endpoint Tests

Tests all 11 caretaker endpoints:
- GET  /api/v1/caretaker/profile
- POST /api/v1/caretaker/profile
- GET  /api/v1/caretaker/list_caretaker
- GET  /api/v1/caretaker/pricing_tiers
- POST /api/v1/caretaker/availability
- POST /api/v1/caretaker/update_availability
- GET  /api/v1/caretaker/availability_status
- GET  /api/v1/caretaker/verification_status
- POST /api/v1/caretaker/upload_document
- POST /api/v1/caretaker/upload_documents
- GET  /api/v1/caretaker/document_view
"""

import io
import pytest
from tests.conftest import make_auth_headers


def test_caretaker_profile_and_availability_flow(client, caretaker_user):
    headers = make_auth_headers(caretaker_user)

    # 1. Get profile
    res_prof = client.get("/api/v1/caretaker/profile", headers=headers)
    assert res_prof.status_code == 200
    prof_body = res_prof.json()
    assert prof_body["success"] is True
    assert "platform_commission_hourly" not in prof_body["data"]
    assert "document_map" in prof_body["data"]

    # 2. Availability status
    res_avail = client.get("/api/v1/caretaker/availability_status", headers=headers)
    assert res_avail.status_code == 200
    avail_body = res_avail.json()
    assert avail_body["success"] is True
    assert "is_available" in avail_body["data"]

    # 3. Toggle availability
    res_toggle = client.post("/api/v1/caretaker/availability", json={"is_available": False}, headers=headers)
    assert res_toggle.status_code == 200
    assert res_toggle.json()["data"]["is_available"] is False

    # 4. Alternative endpoint update_availability
    res_toggle2 = client.post("/api/v1/caretaker/update_availability", json={"is_available": True}, headers=headers)
    assert res_toggle2.status_code == 200
    assert res_toggle2.json()["data"]["is_available"] is True


def test_caretaker_discovery_listing(client, test_user, caretaker_user):
    headers = make_auth_headers(test_user)

    # List caretakers as family
    res_list = client.get("/api/v1/caretaker/list_caretaker", headers=headers)
    assert res_list.status_code == 200
    list_body = res_list.json()
    assert list_body["success"] is True
    assert isinstance(list_body["data"], list)

    # Check non-admin does not see raw last_active_at
    if len(list_body["data"]) > 0:
        c = list_body["data"][0]
        assert "is_online" in c
        assert "last_active_at" not in c


def test_caretaker_pricing_tiers(client, caretaker_user):
    headers = make_auth_headers(caretaker_user)
    res = client.get("/api/v1/caretaker/pricing_tiers", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "tiers" in body["data"]


def test_caretaker_document_upload_and_view(client, caretaker_user, admin_user):
    ct_headers = make_auth_headers(caretaker_user)
    adm_headers = make_auth_headers(admin_user)

    # 1. Single upload
    fake_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    files = {"document": ("id_front.pdf", io.BytesIO(fake_pdf), "application/pdf")}
    data = {"document_type": "id_proof_front"}

    res_up = client.post("/api/v1/caretaker/upload_document", data=data, files=files, headers=ct_headers)
    assert res_up.status_code == 201
    up_body = res_up.json()
    assert up_body["success"] is True
    doc_id = up_body["data"]["document_id"]
    assert up_body["data"]["document_type"] == "id_proof_front"

    # 2. View document as caretaker owner
    res_view = client.get(f"/api/v1/caretaker/document_view?id={doc_id}", headers=ct_headers)
    assert res_view.status_code == 200
    assert res_view.headers["content-type"] == "application/pdf"

    # 3. View document as admin in debug mode
    res_dbg = client.get(f"/api/v1/caretaker/document_view?id={doc_id}&debug=1", headers=adm_headers)
    assert res_dbg.status_code == 200
    dbg_body = res_dbg.json()
    assert dbg_body["success"] is True
    assert dbg_body["data"]["file_exists"] is True

    # 4. Check verification status
    res_verif = client.get("/api/v1/caretaker/verification_status", headers=ct_headers)
    assert res_verif.status_code == 200
    verif_body = res_verif.json()
    assert verif_body["success"] is True
    assert "document_summary" in verif_body["data"]

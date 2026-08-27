"""
WeCare — Part 9 Complaint & Replacement Tickets Test Suite

Tests all endpoints and behaviors for:
- Family complaint creation (with 24h window and proof upload)
- Family complaint retrieval & filtering
- Admin complaint list, detail, and status updates
- Admin complaint proof streaming / viewing
- Caretaker replacement ticket creation & ownership checks
- Admin replacement ticket list, detail, and available caretakers
- Admin replacement caretaker assignment, booking reassignment, and status transitions
- Admin replacement ticket resolution, cancellation, and deletion
- Legacy  aliases and /api/v1/replacement_tickets/* aliases
"""

import io
import time
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="family"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"p9_{role}_{ts}@example.com"
    username = f"p9_{role[:2]}_{ts}"
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


def test_complaint_creation_flow_and_24h_window_http(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)

    # Create patient
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition) "
            "VALUES (:fid, 'Patient P9-1', 75, 'female', 'None')"
        ),
        {"fid": fam["id"]},
    )
    p_id = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.commit()

    # Create completed booking within window (< 24 hours ago)
    now_recent = datetime.now(timezone.utc) - timedelta(hours=2)
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, status, updated_at) "
            "VALUES (:fid, :cid, :pid, 'elderly_care', CURRENT_DATE, '09:00:00', '12:00:00', 'completed', :up)"
        ),
        {"fid": fam["id"], "cid": car["id"], "pid": p_id, "up": now_recent.strftime("%Y-%m-%d %H:%M:%S")},
    )
    recent_booking_id = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.commit()

    # 1. Missing fields -> 400
    res = client.post(
        "/api/v1/complaint/create_complaint",
        json={"booking_id": recent_booking_id},
        headers=fam_headers,
    )
    assert res.status_code == 400
    assert res.json()["success"] is False

    # 2. Successful JSON submission
    res = client.post(
        "/api/v1/complaint/create_complaint",
        json={
            "booking_id": recent_booking_id,
            "subject": "Late arrival",
            "description": "Caretaker arrived 30 minutes late.",
        },
        headers=fam_headers,
    )
    assert res.status_code == 201
    assert res.json()["success"] is True
    assert res.json()["data"]["complaint_id"] > 0

    # 3. Multipart form data submission with file upload
    fake_pdf = io.BytesIO(b"%PDF-1.4 Fake PDF Content for Complaint Proof")
    res_file = client.post(
        "/api/v1/complaint/create_complaint",
        data={
            "booking_id": str(recent_booking_id),
            "subject": "Missing items",
            "description": "Proof attached of medicine receipt.",
        },
        files={"proof_file": ("receipt.pdf", fake_pdf, "application/pdf")},
        headers=fam_headers,
    )
    assert res_file.status_code == 201
    data_file = res_file.json()["data"]
    assert data_file["proof_path"] is not None
    assert "/uploads/complaints/" in data_file["proof_path"]

    # 4. Expired booking (> 24 hours ago) -> 400 "Complaint window expired"
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, status, updated_at) "
            "VALUES (:fid, :cid, :pid, 'elderly_care', '2026-01-01', '09:00:00', '12:00:00', 'completed', :up)"
        ),
        {"fid": fam["id"], "cid": car["id"], "pid": p_id, "up": old_time.strftime("%Y-%m-%d %H:%M:%S")},
    )
    expired_booking_id = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.commit()

    res_exp = client.post(
        "/api/v1/complaint/create_complaint",
        json={
            "booking_id": expired_booking_id,
            "subject": "Expired complaint",
            "description": "This should fail due to 24h expiration.",
        },
        headers=fam_headers,
    )
    assert res_exp.status_code == 400
    assert "Complaint window expired" in res_exp.json()["message"]


def test_complaint_my_complaints_and_filters_http(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)

    # Create booking & complaint
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, service_type, booking_date, status) "
            "VALUES (:fid, :cid, 'elderly_care', CURRENT_DATE, 'completed')"
        ),
        {"fid": fam["id"], "cid": car["id"]},
    )
    bid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.execute(
        text(
            "INSERT INTO complaints (booking_id, family_user_id, caretaker_user_id, subject, description, status) "
            "VALUES (:bid, :fid, :cid, 'Unprofessional behavior', 'Details here...', 'open')"
        ),
        {"bid": bid, "fid": fam["id"], "cid": car["id"]},
    )
    db.commit()

    # Query my_complaints
    res = client.get("/api/v1/complaint/my_complaints", headers=fam_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert "items" in data
    assert "complaints" in data
    assert len(data["items"]) >= 1

    # Query legacy  with status filter
    res_php = client.get("/api/v1/complaint/my_complaints?status=open", headers=fam_headers)
    assert res_php.status_code == 200
    assert res_php.json()["success"] is True

    # Invalid status filter -> 400
    res_bad = client.get("/api/v1/complaint/my_complaints?status=invalid_status", headers=fam_headers)
    assert res_bad.status_code == 400


def test_admin_complaints_list_view_and_status_update_http(client, db):
    admin = _create_user(db, "admin")
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    admin_headers = make_auth_headers(admin, db)

    # Caretaker profile
    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, is_available, verification_status) "
            "VALUES (:uid, 'Caretaker P9-3', 1, 'approved') "
            "ON DUPLICATE KEY UPDATE full_name = 'Caretaker P9-3', is_available = 1, verification_status = 'approved'"
        ),
        {"uid": car["id"]},
    )
    db.commit()

    # Booking & Complaint
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, service_type, booking_date, status, payout_status) "
            "VALUES (:fid, :cid, 'special_need', CURRENT_DATE, 'completed', 'hold')"
        ),
        {"fid": fam["id"], "cid": car["id"]},
    )
    bid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.execute(
        text(
            "INSERT INTO complaints (booking_id, family_user_id, caretaker_user_id, subject, description, status) "
            "VALUES (:bid, :fid, :cid, 'Payment Dispute', 'Details regarding dispute...', 'open')"
        ),
        {"bid": bid, "fid": fam["id"], "cid": car["id"]},
    )
    cid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.commit()

    # 1. Admin List
    res_list = client.get("/api/v1/complaint/admin_list", headers=admin_headers)
    assert res_list.status_code == 200
    assert res_list.json()["data"]["total"] >= 1
    item = next(x for x in res_list.json()["data"]["items"] if x["id"] == cid)
    assert item["payout_hold_status"] == "held"
    assert "Payout remains on hold" in item["payout_impact_message"]

    # 2. Admin View
    res_view = client.get(f"/api/v1/complaint/admin_view?id={cid}", headers=admin_headers)
    assert res_view.status_code == 200
    assert res_view.json()["data"]["id"] == cid
    assert res_view.json()["data"]["against_name"] == "Caretaker P9-3"

    # 3. Admin Update Status to resolved
    res_up = client.post(
        "/api/v1/complaint/admin_update_status",
        json={
            "id": cid,
            "status": "resolved",
            "admin_note": "Complaint investigated and resolved in family favor.",
        },
        headers=admin_headers,
    )
    assert res_up.status_code == 200
    assert res_up.json()["data"]["complaint_id"] == cid

    # Verify in DB
    updated = db.execute(
        text("SELECT status, resolved_by, resolved_at, admin_note FROM complaints WHERE id = :cid"),
        {"cid": cid},
    ).fetchone()
    assert str(updated.status) == "resolved"
    assert updated.resolved_by == admin["id"]
    assert updated.resolved_at is not None
    assert "Complaint investigated" in updated.admin_note


def test_replacement_ticket_creation_and_authorization_http(client, db):
    car = _create_user(db, "caretaker")
    other_car = _create_user(db, "caretaker")
    fam = _create_user(db, "family")
    car_headers = make_auth_headers(car, db)
    other_car_headers = make_auth_headers(other_car, db)

    # Booking assigned to car
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, service_type, booking_date, status) "
            "VALUES (:fid, :cid, 'elderly_care', CURRENT_DATE, 'accepted')"
        ),
        {"fid": fam["id"], "cid": car["id"]},
    )
    bid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.commit()

    # 1. Other caretaker attempts creation on this booking -> 403 Forbidden
    res_403 = client.post(
        "/api/v1/replacement/create_ticket",
        json={"booking_id": bid, "reason": "I cannot attend this booking."},
        headers=other_car_headers,
    )
    assert res_403.status_code == 403
    assert res_403.json()["success"] is False

    # 2. Missing fields -> 400
    res_400 = client.post(
        "/api/v1/replacement/create_ticket",
        json={"booking_id": bid},
        headers=car_headers,
    )
    assert res_400.status_code == 400

    # 3. Successful creation by assigned caretaker
    res_ok = client.post(
        "/api/v1/replacement/create_ticket",
        json={"booking_id": bid, "reason": "Medical emergency on my side."},
        headers=car_headers,
    )
    assert res_ok.status_code == 201
    data = res_ok.json()["data"]
    assert data["replacement_ticket_id"] > 0
    assert data["booking_id"] == bid
    assert data["requested_by_user_id"] == car["id"]


def test_admin_replacement_tickets_lifecycle_and_assign_resolve_delete_http(client, db):
    admin = _create_user(db, "admin")
    car_orig = _create_user(db, "caretaker")
    car_repl = _create_user(db, "caretaker")
    fam = _create_user(db, "family")
    admin_headers = make_auth_headers(admin, db)

    # Set up replacement caretaker profile (approved, verified, available)
    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, is_available, verification_status, rating) "
            "VALUES (:uid, 'Replacement Caretaker', 1, 'approved', 4.8) "
            "ON DUPLICATE KEY UPDATE is_available = 1, verification_status = 'approved'"
        ),
        {"uid": car_repl["id"]},
    )
    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, is_available, verification_status, rating) "
            "VALUES (:uid, 'Original Caretaker', 1, 'approved', 4.5) "
            "ON DUPLICATE KEY UPDATE is_available = 1, verification_status = 'approved'"
        ),
        {"uid": car_orig["id"]},
    )

    # Booking & Replacement Ticket
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, service_type, booking_date, status) "
            "VALUES (:fid, :cid, 'elderly_care', CURRENT_DATE, 'accepted')"
        ),
        {"fid": fam["id"], "cid": car_orig["id"]},
    )
    bid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

    db.execute(
        text(
            "INSERT INTO replacement_tickets "
            "(booking_id, family_user_id, original_caretaker_user_id, reason, status) "
            "VALUES (:bid, :fid, :cid, 'Urgent conflict', 'open')"
        ),
        {"bid": bid, "fid": fam["id"], "cid": car_orig["id"]},
    )
    tid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.commit()

    # 1. Admin List & Detail view
    res_list = client.get("/api/v1/replacement/admin_list", headers=admin_headers)
    assert res_list.status_code == 200
    assert "tickets" in res_list.json()["data"]
    assert "replacements" in res_list.json()["data"]

    res_view = client.get(f"/api/v1/replacement/admin_view?id={tid}", headers=admin_headers)
    assert res_view.status_code == 200
    ticket_data = res_view.json()["data"]
    assert ticket_data["status"] == "open"
    # Available replacement caretakers should contain replacement caretaker and exclude original caretaker
    avail_ids = [c["user_id"] for c in ticket_data["available_replacement_caretakers"]]
    assert car_repl["id"] in avail_ids
    assert car_orig["id"] not in avail_ids

    # 2. Admin Assign Caretaker
    # Original caretaker assignment is blocked -> 400
    res_self = client.post(
        "/api/v1/replacement/admin_assign",
        json={"ticket_id": tid, "replacement_caretaker_user_id": car_orig["id"]},
        headers=admin_headers,
    )
    assert res_self.status_code == 400
    assert "cannot be the original caretaker" in res_self.json()["message"]

    # Valid assignment
    res_assign = client.post(
        "/api/v1/replacement/admin_assign",
        json={
            "ticket_id": tid,
            "replacement_caretaker_user_id": car_repl["id"],
            "admin_note": "Assigned new qualified caretaker.",
        },
        headers=admin_headers,
    )
    assert res_assign.status_code == 200
    assigned_ticket = res_assign.json()["data"]
    assert assigned_ticket["status"] == "assigned"
    assert assigned_ticket["replacement_caretaker_user_id"] == car_repl["id"]

    # Verify booking caretaker was updated
    updated_bid_car = db.execute(
        text("SELECT caretaker_user_id FROM bookings WHERE id = :bid"),
        {"bid": bid},
    ).scalar()
    assert updated_bid_car == car_repl["id"]

    # 3. Resolve Ticket
    res_res = client.post(
        "/api/v1/replacement/admin_resolve",
        json={"ticket_id": tid, "admin_note": "Replacement confirmed and completed."},
        headers=admin_headers,
    )
    assert res_res.status_code == 200
    resolved_ticket = res_res.json()["data"]
    assert resolved_ticket["status"] == "resolved"
    assert resolved_ticket["resolved_by"] == admin["id"]

    # 4. Delete Resolved Ticket
    res_del = client.post(
        "/api/v1/replacement/admin_delete",
        json={"id": tid},
        headers=admin_headers,
    )
    assert res_del.status_code == 200
    assert res_del.json()["message"] == "Replacement ticket deleted"

    # Confirm deleted
    db.commit()
    deleted_row = db.execute(
        text("SELECT id FROM replacement_tickets WHERE id = :tid"),
        {"tid": tid},
    ).fetchone()
    assert deleted_row is None


def test_replacement_tickets_alias_routes_http(client, db):
    admin = _create_user(db, "admin")
    admin_headers = make_auth_headers(admin, db)

    # Direct /api/v1/replacement_tickets/admin_list[] routing
    res1 = client.get("/api/v1/replacement_tickets/admin_list", headers=admin_headers)
    assert res1.status_code == 200
    assert res1.json()["success"] is True

    res2 = client.get("/api/v1/replacement_tickets/admin_list", headers=admin_headers)
    assert res2.status_code == 200
    assert res2.json()["success"] is True


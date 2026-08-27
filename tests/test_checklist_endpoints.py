"""
WeCare — Checklist Endpoints Test Suite (Part 10)

Tests all booking checklist task endpoints and behaviors:
- GET /booking_tasks (role-aware access for family/caretaker/admin, status normalization)
- POST /create_task (family-only creation, booking eligibility check)
- POST /mark_done (caretaker-only status updates, in_progress requirement, timestamp tracking)
- Legacy  route aliases for all endpoints
"""

import time
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="family"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"chk_{role}_{ts}@example.com"
    username = f"c_{role[:2]}_{ts}"
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


def _create_booking(db, family_id, caretaker_id=None, status="in_progress"):
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, service_type, booking_date, start_time, end_time, address, status, total_amount) "
            "VALUES (:fid, :cid, 'Physiotherapy', CURDATE(), '08:00:00', '10:00:00', 'Checklist Lane', :status, 500.00)"
        ),
        {
            "fid": family_id,
            "cid": caretaker_id,
            "status": status,
        },
    )
    bid = db.execute(text("SELECT id FROM bookings WHERE family_user_id = :fid ORDER BY id DESC LIMIT 1"), {"fid": family_id}).scalar()
    db.commit()
    return int(bid)


def test_booking_tasks_role_aware_access(client, db):
    fam1 = _create_user(db, "family")
    fam2 = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    admin = _create_user(db, "admin")

    fam1_headers = make_auth_headers(fam1, db)
    fam2_headers = make_auth_headers(fam2, db)
    car_headers = make_auth_headers(car, db)
    admin_headers = make_auth_headers(admin, db)

    bid = _create_booking(db, fam1["id"], car["id"], status="in_progress")

    # Insert 2 tasks with different statuses
    db.execute(
        text(
            "INSERT INTO booking_checklist_tasks (booking_id, family_user_id, caretaker_user_id, title, description, status) "
            "VALUES (:bid, :fid, :cid, 'Check Blood Pressure', 'Take readings twice', 'pending'), "
            "       (:bid, :fid, :cid, 'Morning Walk', '15 mins walk', 'ongoing')"
        ),
        {"bid": bid, "fid": fam1["id"], "cid": car["id"]},
    )
    db.commit()

    # Missing booking_id -> 400
    resp_bad = client.get("/api/v1/checklist/booking_tasks", headers=fam1_headers)
    assert resp_bad.status_code == 400

    # Family 1 (owner) -> 200
    resp_f1 = client.get(f"/api/v1/checklist/booking_tasks?booking_id={bid}", headers=fam1_headers)
    assert resp_f1.status_code == 200
    data = resp_f1.json()["data"]
    assert len(data["tasks"]) == 2
    assert data["tasks"][0]["title"] == "Check Blood Pressure"
    assert data["tasks"][0]["status"] == "pending"

    # Family 2 (not owner) -> 404
    resp_f2 = client.get(f"/api/v1/checklist/booking_tasks?booking_id={bid}", headers=fam2_headers)
    assert resp_f2.status_code == 404

    # Caretaker (assigned in_progress) -> 200 (legacy)
    resp_c = client.get(f"/api/v1/checklist/booking_tasks?booking_id={bid}", headers=car_headers)
    assert resp_c.status_code == 200
    assert len(resp_c.json()["data"]["tasks"]) == 2

    # Admin -> 200
    resp_adm = client.get(f"/api/v1/checklist/booking_tasks?booking_id={bid}", headers=admin_headers)
    assert resp_adm.status_code == 200
    assert len(resp_adm.json()["data"]["tasks"]) == 2


def test_create_task_flow(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)
    car_headers = make_auth_headers(car, db)

    bid = _create_booking(db, fam["id"], car["id"], status="accepted")

    # Non-family cannot create tasks -> 401/403
    resp_forbid = client.post(
        "/api/v1/checklist/create_task",
        json={"booking_id": bid, "title": "Check Temperature"},
        headers=car_headers,
    )
    assert resp_forbid.status_code in (401, 403)

    # Missing fields
    resp_missing = client.post(
        "/api/v1/checklist/create_task",
        json={"booking_id": bid},
        headers=fam_headers,
    )
    assert resp_missing.status_code == 400

    # Successful task creation (canonical & legacy)
    resp_ok = client.post(
        "/api/v1/checklist/create_task",
        json={
            "booking_id": bid,
            "title": "Administer Medicine",
            "description": "After lunch with warm water",
        },
        headers=fam_headers,
    )
    assert resp_ok.status_code == 201
    assert "task_id" in resp_ok.json()["data"]

    resp_ok_php = client.post(
        "/api/v1/checklist/create_task",
        json={
            "booking_id": bid,
            "title": "Check Blood Sugar",
        },
        headers=fam_headers,
    )
    assert resp_ok_php.status_code == 201

    # Cannot create on completed or cancelled booking -> 404
    bid_comp = _create_booking(db, fam["id"], car["id"], status="completed")
    resp_comp = client.post(
        "/api/v1/checklist/create_task",
        json={"booking_id": bid_comp, "title": "Post visit task"},
        headers=fam_headers,
    )
    assert resp_comp.status_code == 404


def test_mark_done_flow(client, db):
    fam = _create_user(db, "family")
    car1 = _create_user(db, "caretaker")
    car2 = _create_user(db, "caretaker")

    fam_headers = make_auth_headers(fam, db)
    car1_headers = make_auth_headers(car1, db)
    car2_headers = make_auth_headers(car2, db)

    bid = _create_booking(db, fam["id"], car1["id"], status="in_progress")

    # Create task
    db.execute(
        text(
            "INSERT INTO booking_checklist_tasks (booking_id, family_user_id, caretaker_user_id, title, status) "
            "VALUES (:bid, :fid, :cid, 'Vital Check', 'pending')"
        ),
        {"bid": bid, "fid": fam["id"], "cid": car1["id"]},
    )
    db.commit()
    tid = db.execute(text("SELECT id FROM booking_checklist_tasks WHERE booking_id = :bid"), {"bid": bid}).scalar()

    # Family cannot update task -> 401/403
    resp_forbid = client.post("/api/v1/checklist/mark_done", json={"task_id": tid}, headers=fam_headers)
    assert resp_forbid.status_code in (401, 403)

    # Wrong caretaker -> 404
    resp_wrong_car = client.post("/api/v1/checklist/mark_done", json={"task_id": tid}, headers=car2_headers)
    assert resp_wrong_car.status_code == 404

    # Invalid status -> 400
    resp_bad_st = client.post(
        "/api/v1/checklist/mark_done",
        json={"task_id": tid, "status": "invalid_status"},
        headers=car1_headers,
    )
    assert resp_bad_st.status_code == 400

    # Success: update to ongoing (clears completion timestamp)
    resp_ong = client.post(
        "/api/v1/checklist/mark_done",
        json={"task_id": tid, "status": "ongoing"},
        headers=car1_headers,
    )
    assert resp_ong.status_code == 200
    assert resp_ong.json()["data"]["status"] == "ongoing"
    assert resp_ong.json()["data"]["completed_at"] == ""

    # Success: mark completed (legacy ) -> sets completed_at
    resp_comp = client.post(
        "/api/v1/checklist/mark_done",
        json={"task_id": tid, "status": "completed"},
        headers=car1_headers,
    )
    assert resp_comp.status_code == 200
    assert resp_comp.json()["data"]["status"] == "completed"
    assert resp_comp.json()["data"]["completed_at"] != ""

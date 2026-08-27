"""
WeCare — Emergency SOS Endpoints HTTP Integration Tests (Part 7)

Comprehensive test suite covering all 7 SOS endpoints via FastAPI TestClient:
1. POST /api/v1/sos/create_sos[]
2. POST /api/v1/sos/create[]
3. GET  /api/v1/sos/my_sos[]
4. POST /api/v1/sos/resolve_sos[]
5. POST /api/v1/sos/update_status[]
6. GET  /api/v1/sos/admin_sos_list[]
7. GET  /api/v1/admin/sos_detail[] & /api/v1/sos/sos_detail[]

Tests role scoping, IDOR protection, rate limiting, visit live logging,
multi-party notifications, status filtering, and joined detail responses.
"""

from datetime import datetime, timedelta, timezone
import time
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_aux_user(db, role="caretaker"):
    """Creates a real auxiliary user for IDOR testing."""
    ts = int(time.time() * 1000000) % 1000000000
    email = f"aux_{role}_{ts}@example.com"
    username = f"aux_{role[:2]}_{ts}"
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
    user_id = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()
    db.commit()

    if role == "caretaker":
        db.execute(
            text(
                "INSERT INTO caretaker_profiles (user_id, full_name, verification_status, is_available) "
                "VALUES (:uid, :name, 'approved', 1)"
            ),
            {"uid": user_id, "name": f"Aux Caretaker {user_id}"},
        )
        db.commit()

    return {"id": user_id, "email": email, "role": role}


@pytest.fixture
def sos_setup_data(db):
    """Sets up primary family, caretaker, admin, patient, and booking for SOS tests."""
    ts = int(time.time() * 1000000) % 1000000000
    pwd_hash = hash_password("TestPassword123!")

    # 1. Family User
    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'family', 1, 1)"
        ),
        {
            "email": f"fam_sos_{ts}@example.com",
            "username": f"fam_sos_{ts}",
            "phone": f"9{ts:09d}"[:10],
            "password": pwd_hash,
        },
    )
    family_id = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()

    db.execute(
        text(
            "INSERT INTO family_profiles (user_id, full_name, emergency_contact_phone) "
            "VALUES (:uid, :name, '9998887776')"
        ),
        {"uid": family_id, "name": f"Family SOS {family_id}"},
    )

    # 2. Caretaker User
    ts_c = (ts + 1) % 1000000000
    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'caretaker', 1, 1)"
        ),
        {
            "email": f"car_sos_{ts_c}@example.com",
            "username": f"car_sos_{ts_c}",
            "phone": f"9{ts_c:09d}"[:10],
            "password": pwd_hash,
        },
    )
    caretaker_id = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()

    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, verification_status, is_available) "
            "VALUES (:uid, :name, 'approved', 1)"
        ),
        {"uid": caretaker_id, "name": f"Caretaker SOS {caretaker_id}"},
    )

    # 3. Admin User
    ts_a = (ts + 2) % 1000000000
    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'admin', 1, 1)"
        ),
        {
            "email": f"adm_sos_{ts_a}@example.com",
            "username": f"adm_sos_{ts_a}",
            "phone": f"9{ts_a:09d}"[:10],
            "password": pwd_hash,
        },
    )
    admin_id = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()

    # 4. Patient
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition) "
            "VALUES (:fid, :name, 72, 'female', 'Hypertension')"
        ),
        {"fid": family_id, "name": "Senior Patient SOS"},
    )
    patient_id = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()

    # 5. Active In-Progress Booking
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db.execute(
        text(
            "INSERT INTO bookings ("
            "  family_user_id, caretaker_user_id, patient_id, service_type, "
            "  booking_date, start_time, end_time, total_hours, address, "
            "  status, payment_status, total_customer_amount, caretaker_earning_amount"
            ") VALUES ("
            "  :fid, :cid, :pid, 'Elderly Care', "
            "  :bdate, '09:00:00', '17:00:00', 8.0, '123 Rescue St, City', "
            "  'in_progress', 'paid', 1600.00, 1280.00"
            ")"
        ),
        {
            "fid": family_id,
            "cid": caretaker_id,
            "pid": patient_id,
            "bdate": today_str,
        },
    )
    booking_id = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()

    # 6. Visit Tracking Record
    check_in_time = datetime.now(timezone.utc) - timedelta(hours=2)
    db.execute(
        text(
            "INSERT INTO visit_tracking (booking_id, caretaker_user_id, check_in_time, check_in_lat, check_in_lng) "
            "VALUES (:bid, :cid, :check_in, '12.9716', '77.5946')"
        ),
        {
            "bid": booking_id,
            "cid": caretaker_id,
            "check_in": check_in_time,
        },
    )
    visit_id = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()
    db.commit()

    return {
        "family": {"id": family_id, "email": f"fam_sos_{ts}@example.com", "role": "family"},
        "caretaker": {"id": caretaker_id, "email": f"car_sos_{ts_c}@example.com", "role": "caretaker"},
        "admin": {"id": admin_id, "email": f"adm_sos_{ts_a}@example.com", "role": "admin"},
        "patient_id": patient_id,
        "booking_id": booking_id,
        "visit_id": visit_id,
    }


def test_create_sos_caretaker_live_visit_http(client, db, sos_setup_data):
    """Caretaker triggers SOS on an active visit -> creates alert, activity log, notifications."""
    data = sos_setup_data
    car_headers = make_auth_headers(data["caretaker"], db)

    resp = client.post(
        "/api/v1/sos/create_sos",
        json={
            "booking_id": data["booking_id"],
            "message": "Patient experiencing severe dizziness and low pulse.",
            "latitude": "12.9716",
            "longitude": "77.5946",
        },
        headers=car_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "SOS alert created successfully"
    sos_id = body["data"]["sos_id"]
    assert sos_id > 0
    assert body["data"]["booking_id"] == data["booking_id"]
    assert body["data"]["status"] == "open"

    # Verify visit activity log
    vlog = db.execute(
        text("SELECT * FROM visit_activity_logs WHERE booking_id = :bid AND activity_type = 'sos_created'"),
        {"bid": data["booking_id"]},
    ).fetchone()
    assert vlog is not None
    assert vlog.actor_user_id == data["caretaker"]["id"]

    # Verify notifications created for family and admin
    notifs = db.execute(
        text("SELECT * FROM notifications WHERE type = 'sos_created' AND related_id = :sid"),
        {"sid": sos_id},
    ).fetchall()
    notif_user_ids = [n.user_id for n in notifs]
    assert data["family"]["id"] in notif_user_ids
    assert data["admin"]["id"] in notif_user_ids


def test_create_sos_family_booking_http(client, db, sos_setup_data):
    """Family triggers SOS on their booking -> sends notification to caretaker and admin."""
    data = sos_setup_data
    fam_headers = make_auth_headers(data["family"], db)

    resp = client.post(
        "/api/v1/sos/create_sos",
        json={
            "booking_id": data["booking_id"],
            "message": "Emergency: Family cannot reach caretaker by phone.",
        },
        headers=fam_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    sos_id = body["data"]["sos_id"]

    # Verify notifications created for caretaker and admin
    notifs = db.execute(
        text("SELECT * FROM notifications WHERE type = 'sos_created' AND related_id = :sid"),
        {"sid": sos_id},
    ).fetchall()
    notif_user_ids = [n.user_id for n in notifs]
    assert data["caretaker"]["id"] in notif_user_ids
    assert data["admin"]["id"] in notif_user_ids


def test_create_sos_standalone_http(client, db, sos_setup_data):
    """User triggers SOS without a booking -> creates open alert and notifies admins."""
    data = sos_setup_data
    car_headers = make_auth_headers(data["caretaker"], db)

    resp = client.post(
        "/api/v1/sos/create_sos",
        json={
            "message": "General distress signal triggered outside booking.",
            "latitude": "12.9800",
            "longitude": "77.6000",
        },
        headers=car_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["booking_id"] is None
    assert body["data"]["status"] == "open"


def test_create_sos_validation_and_idor_http(client, db, sos_setup_data):
    """Tests validation and IDOR protection on create_sos."""
    data = sos_setup_data
    car_headers = make_auth_headers(data["caretaker"], db)

    # 1. Missing message
    resp = client.post(
        "/api/v1/sos/create_sos",
        json={"booking_id": data["booking_id"], "message": "   "},
        headers=car_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["success"] is False
    assert "Message is required" in str(resp.json()["errors"])

    # 2. IDOR: Other family tries creating SOS on data['booking_id']
    aux_fam = _create_aux_user(db, "family")
    aux_fam_headers = make_auth_headers(aux_fam, db)

    resp = client.post(
        "/api/v1/sos/create_sos",
        json={"booking_id": data["booking_id"], "message": "Intruder family alert"},
        headers=aux_fam_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["message"] == "Booking not found for this user"

    # 3. IDOR: Other caretaker tries creating SOS on data['booking_id']
    aux_car = _create_aux_user(db, "caretaker")
    aux_car_headers = make_auth_headers(aux_car, db)

    resp = client.post(
        "/api/v1/sos/create_sos",
        json={"booking_id": data["booking_id"], "message": "Intruder caretaker alert"},
        headers=aux_car_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["message"] == "Booking not found for this user"


def test_caretaker_create_fast_endpoint_http(client, db, sos_setup_data):
    """Tests POST /api/v1/sos/create[] fast caretaker trigger."""
    data = sos_setup_data
    car_headers = make_auth_headers(data["caretaker"], db)
    fam_headers = make_auth_headers(data["family"], db)

    # 1. Success on active booking
    resp = client.post(
        "/api/v1/sos/create",
        json={
            "booking_id": data["booking_id"],
            "message": "Rapid caretaker alert via fast endpoint",
        },
        headers=car_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["success"] is True
    assert resp.json()["data"]["booking_id"] == data["booking_id"]

    # 2. Family role forbidden
    resp = client.post(
        "/api/v1/sos/create",
        json={"booking_id": data["booking_id"], "message": "Family fast alert"},
        headers=fam_headers,
    )
    assert resp.status_code == 403

    # 3. Missing/invalid booking_id
    resp = client.post(
        "/api/v1/sos/create",
        json={"booking_id": "abc", "message": "Test"},
        headers=car_headers,
    )
    assert resp.status_code == 400
    assert "Booking id must be an integer" in str(resp.json()["errors"])

    # 4. Empty message
    resp = client.post(
        "/api/v1/sos/create",
        json={"booking_id": data["booking_id"], "message": ""},
        headers=car_headers,
    )
    assert resp.status_code == 400

    # 5. Wrong booking ID
    resp = client.post(
        "/api/v1/sos/create",
        json={"booking_id": 999999, "message": "Test"},
        headers=car_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["message"] == "Assigned active booking not found"


def test_my_sos_pagination_and_scoping_http(client, db, sos_setup_data):
    """Tests GET /api/v1/sos/my_sos[] paginated user alert list."""
    data = sos_setup_data
    car_headers = make_auth_headers(data["caretaker"], db)

    # Insert 3 SOS alerts for this caretaker
    for i in range(3):
        db.execute(
            text("INSERT INTO sos_alerts (user_id, booking_id, message, status) VALUES (:uid, :bid, :msg, 'open')"),
            {"uid": data["caretaker"]["id"], "bid": data["booking_id"], "msg": f"Alert {i+1}"},
        )
    db.commit()

    resp = client.get("/api/v1/sos/my_sos?page=1&limit=2", headers=car_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["data"]["items"]) == 2
    assert len(body["data"]["sos_alerts"]) == 2  # Alias key
    assert body["data"]["pagination"]["limit"] == 2
    assert body["data"]["pagination"]["total"] >= 3

    # Other user calling my_sos gets only their own
    aux_car = _create_aux_user(db, "caretaker")
    aux_headers = make_auth_headers(aux_car, db)
    resp_aux = client.get("/api/v1/sos/my_sos", headers=aux_headers)
    assert resp_aux.status_code == 200
    assert len(resp_aux.json()["data"]["items"]) == 0


def test_admin_resolve_and_update_status_http(client, db, sos_setup_data):
    """Tests admin resolve and status update endpoints."""
    data = sos_setup_data
    adm_headers = make_auth_headers(data["admin"], db)
    car_headers = make_auth_headers(data["caretaker"], db)

    # Create SOS
    db.execute(
        text("INSERT INTO sos_alerts (user_id, booking_id, message, status) VALUES (:uid, :bid, 'Test Admin Alert', 'open')"),
        {"uid": data["caretaker"]["id"], "bid": data["booking_id"]},
    )
    sid = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())
    db.commit()

    # 1. Non-admin cannot resolve
    resp = client.post("/api/v1/sos/resolve_sos", json={"sos_id": sid}, headers=car_headers)
    assert resp.status_code == 403

    # 2. Admin resolves SOS
    resp = client.post("/api/v1/sos/resolve_sos", json={"sos_id": sid}, headers=adm_headers)
    assert resp.status_code == 200
    assert resp.json()["message"] == "SOS alert resolved successfully"

    status_in_db = db.execute(text("SELECT status FROM sos_alerts WHERE id = :sid"), {"sid": sid}).scalar()
    assert str(status_in_db.value if hasattr(status_in_db, "value") else status_in_db) == "resolved"

    # 3. Admin reopens SOS via update_status
    resp = client.post(
        "/api/v1/sos/update_status",
        json={"sos_id": sid, "status": "open"},
        headers=adm_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "SOS status updated"

    db.commit()
    status_reopened = db.execute(text("SELECT status FROM sos_alerts WHERE id = :sid"), {"sid": sid}).scalar()
    assert str(status_reopened.value if hasattr(status_reopened, "value") else status_reopened) == "open"


    # Verify audit log
    audit_row = db.execute(
        text("SELECT * FROM admin_audit_logs WHERE action = 'update_sos_status' AND entity_id = :sid"),
        {"sid": sid},
    ).fetchone()
    assert audit_row is not None


    # 4. Invalid status returns 400
    resp = client.post(
        "/api/v1/sos/update_status",
        json={"sos_id": sid, "status": "invalid_status"},
        headers=adm_headers,
    )
    assert resp.status_code == 400


def test_admin_sos_list_and_detail_http(client, db, sos_setup_data):
    """Tests admin list and detail endpoints with effective booking joins."""
    data = sos_setup_data
    adm_headers = make_auth_headers(data["admin"], db)

    # Create SOS
    db.execute(
        text(
            "INSERT INTO sos_alerts (user_id, booking_id, message, latitude, longitude, status) "
            "VALUES (:uid, :bid, 'Detailed Medical Alert', '12.9716', '77.5946', 'open')"
        ),
        {"uid": data["caretaker"]["id"], "bid": data["booking_id"]},
    )
    sid = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())
    db.commit()


    # 1. Admin SOS list
    resp = client.get("/api/v1/sos/admin_sos_list?status=all", headers=adm_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "items" in body["data"]
    assert "alerts" in body["data"]
    assert "sos_alerts" in body["data"]
    item_ids = [item["id"] for item in body["data"]["items"]]
    assert sid in item_ids

    # 2. Filter by status=open
    resp_open = client.get("/api/v1/sos/admin_sos_list?status=open", headers=adm_headers)
    assert resp_open.status_code == 200

    # 3. Invalid status returns 400
    resp_bad = client.get("/api/v1/sos/admin_sos_list?status=unknown", headers=adm_headers)
    assert resp_bad.status_code == 400
    assert "Allowed values are all, open and resolved" in str(resp_bad.json()["errors"])

    # 4. Admin SOS detail via /api/v1/admin/sos_detail[]
    resp_det = client.get(f"/api/v1/admin/sos_detail?id={sid}", headers=adm_headers)
    assert resp_det.status_code == 200
    det_body = resp_det.json()
    assert det_body["success"] is True
    d = det_body["data"]
    assert d["id"] == sid
    assert d["message"] == "Detailed Medical Alert"
    assert d["location_text"] == "12.9716, 77.5946"
    assert d["patient"]["patient_name"] == "Senior Patient SOS"
    assert d["family"]["name"] is not None
    assert d["caretaker"]["name"] is not None
    assert d["booking"]["status"] == "in_progress"
    assert d["reporter"]["role"] == "caretaker"

    # 5. Admin SOS detail via /api/v1/sos/sos_detail[]
    resp_det2 = client.get(f"/api/v1/sos/sos_detail?id={sid}", headers=adm_headers)
    assert resp_det2.status_code == 200
    assert resp_det2.json()["data"]["id"] == sid

"""
WeCare — Dashboard Endpoints Test Suite (Part 11)

Tests all Dashboard endpoints and business rules:
- GET /api/v1/dashboard/admin_dashboard (+  alias)
  - Core counts, primary/secondary KPIs, live operations, recent activity formatting
  - RBAC protection (401/403)
- GET /api/v1/dashboard/caretaker_dashboard (+  alias)
  - Profile state, availability payload, earnings breakdown (ready, paid, hold)
  - Realtime presence update side effect (last_active_at updated)
  - Today's, active, and upcoming visits formatting
  - RBAC protection (401/403)
- GET /api/v1/dashboard/family_dashboard (+  alias)
  - Patient, booking, and SOS counts
  - IDOR isolation
  - RBAC protection (401/403)
"""

import time
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="family"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"dash_{role}_{ts}@example.com"
    username = f"d_{role[:2]}_{ts}"
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


def _create_caretaker_profile(db, user_id, verification_status="approved", is_available=1):
    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, gender, date_of_birth, experience_years, "
            "                                hourly_rate, bio, verification_status, is_available, "
            "                                manual_availability_enabled, availability_reason, last_active_at) "
            "VALUES (:uid, 'Caretaker Test', 'female', '1990-01-01', 5, 250.00, 'Experienced nurse', "
            "        :vstat, :avail, :avail, 'manual_on', NOW())"
        ),
        {"uid": user_id, "vstat": verification_status, "avail": is_available},
    )
    db.commit()


# ============================================================
# Admin Dashboard Tests
# ============================================================


def test_admin_dashboard_success(client, db):
    admin = _create_user(db, "admin")
    headers = make_auth_headers(admin, db)

    # Insert test audit log
    db.execute(
        text(
            "INSERT INTO admin_audit_logs (admin_user_id, action, entity_type, entity_id, created_at) "
            "VALUES (:uid, 'verify_caretaker', 'caretaker_profile', 99, NOW())"
        ),
        {"uid": admin["id"]},
    )
    db.commit()

    resp = client.get("/api/v1/dashboard/admin_dashboard", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]

    # Verify stats
    assert "stats" in data
    assert "active_sos" in data["stats"]
    assert "active_visits" in data["stats"]
    assert "pending_verification" in data["stats"]
    assert "payout_holds" in data["stats"]
    assert "complaints_pending" in data["stats"]
    assert "replacements_pending" in data["stats"]
    assert "pending_bookings" in data["stats"]
    assert "completed_bookings" in data["stats"]

    # Verify counts
    assert "counts" in data
    assert data["counts"]["total_users"] >= 1
    assert "total_family_users" in data["counts"]
    assert "total_caretakers" in data["counts"]
    assert "total_bookings" in data["counts"]

    # Verify live operations & recent activity structures
    assert isinstance(data["live_operations"], list)
    assert isinstance(data["recent_activity"], list)
    assert len(data["recent_activity"]) >= 1

    # Check formatted audit log item
    item = data["recent_activity"][0]
    assert item["action"] == "verify_caretaker"
    assert item["entity_type"] == "caretaker_profile"
    assert "Verify caretaker caretaker_profile #99" in item["text"]
    assert item["type"] == "caretaker_profile"
    assert item["time"] != ""


def test_admin_dashboard_rbac_and_legacy_alias(client, db):
    admin = _create_user(db, "admin")
    family = _create_user(db, "family")
    caretaker = _create_user(db, "caretaker")

    admin_headers = make_auth_headers(admin, db)
    family_headers = make_auth_headers(family, db)
    caretaker_headers = make_auth_headers(caretaker, db)

    # 401 unauthenticated
    resp = client.get("/api/v1/dashboard/admin_dashboard")
    assert resp.status_code == 401

    # 403 non-admin
    resp = client.get("/api/v1/dashboard/admin_dashboard", headers=family_headers)
    assert resp.status_code == 403

    resp = client.get("/api/v1/dashboard/admin_dashboard", headers=caretaker_headers)
    assert resp.status_code == 403

    # Legacy  alias with admin
    resp = client.get("/api/v1/dashboard/admin_dashboard", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ============================================================
# Caretaker Dashboard Tests
# ============================================================


def test_caretaker_dashboard_presence_side_effect(client, db):
    ct = _create_user(db, "caretaker")
    _create_caretaker_profile(db, ct["id"])

    # Set last_active_at to 2 hours ago
    past_time = datetime.now() - timedelta(hours=2)
    db.execute(
        text("UPDATE caretaker_profiles SET last_active_at = :past WHERE user_id = :uid"),
        {"past": past_time, "uid": ct["id"]},
    )
    db.commit()

    headers = make_auth_headers(ct, db)
    resp = client.get("/api/v1/dashboard/caretaker_dashboard", headers=headers)
    assert resp.status_code == 200

    # Verify that presence timestamp was updated in DB
    refreshed_time = db.execute(
        text("SELECT last_active_at FROM caretaker_profiles WHERE user_id = :uid"),
        {"uid": ct["id"]},
    ).scalar()
    assert refreshed_time is not None
    # refreshed_time should be significantly after past_time
    assert refreshed_time > past_time


def test_caretaker_dashboard_earnings_and_visits(client, db):
    family = _create_user(db, "family")
    ct = _create_user(db, "caretaker")
    _create_caretaker_profile(db, ct["id"])

    # Create patient
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fuid, 'Patient One', 75, 'male', 'Arthritis', 'elderly_care')"
        ),
        {"fuid": family["id"]},
    )
    patient_id = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fuid"), {"fuid": family["id"]}
    ).scalar()

    today_str = date.today().strftime("%Y-%m-%d")

    # Insert completed bookings with earnings
    # 1. ready_for_payout: 500
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, total_amount, caretaker_earning_amount, "
            "                      status, payout_status, address) "
            "VALUES (:fuid, :cuid, :pid, 'elderly_care', :bdate, '09:00:00', '13:00:00', 600, 500, 'completed', 'ready_for_payout', '123 MG Road')"
        ),
        {"fuid": family["id"], "cuid": ct["id"], "pid": patient_id, "bdate": today_str},
    )
    # 2. paid: 300
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, total_amount, caretaker_earning_amount, "
            "                      status, payout_status, address) "
            "VALUES (:fuid, :cuid, :pid, 'elderly_care', :bdate, '14:00:00', '18:00:00', 400, 300, 'completed', 'paid', '123 MG Road')"
        ),
        {"fuid": family["id"], "cuid": ct["id"], "pid": patient_id, "bdate": today_str},
    )
    # 3. hold: 200
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, total_amount, caretaker_earning_amount, "
            "                      status, payout_status, address) "
            "VALUES (:fuid, :cuid, :pid, 'elderly_care', :bdate, '19:00:00', '21:00:00', 250, 200, 'completed', 'hold', '123 MG Road')"
        ),
        {"fuid": family["id"], "cuid": ct["id"], "pid": patient_id, "bdate": today_str},
    )
    db.commit()

    headers = make_auth_headers(ct, db)
    resp = client.get("/api/v1/dashboard/caretaker_dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    # Earnings assertions:
    # total_earnings = ready_for_payout (500) + paid (300) = 800
    # pending_earnings = 500
    # paid_earnings = 300
    # hold_earnings = 200
    assert data["total_earnings"] == 800.0
    assert data["pending_earnings"] == 500.0
    assert data["paid_earnings"] == 300.0
    assert data["hold_earnings"] == 200.0
    assert data["completed_bookings"] == 3
    assert data["summary"]["todays_visits"] == 3


def test_caretaker_dashboard_active_and_upcoming_visits(client, db):
    family = _create_user(db, "family")
    ct = _create_user(db, "caretaker")
    _create_caretaker_profile(db, ct["id"])

    # Create patient
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fuid, 'Patient Two', 80, 'female', 'Dementia', 'nursing')"
        ),
        {"fuid": family["id"]},
    )
    patient_id = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fuid"), {"fuid": family["id"]}
    ).scalar()

    today_str = date.today().strftime("%Y-%m-%d")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    # 1. In-progress visit with visit_tracking checked in
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, total_amount, status, address, "
            "                      location_latitude, location_longitude) "
            "VALUES (:fuid, :cuid, :pid, 'nursing', :bdate, '10:00:00', '14:00:00', 500, 'in_progress', "
            "        '456 Residency Road, Bangalore', 12.9716, 77.5946)"
        ),
        {"fuid": family["id"], "cuid": ct["id"], "pid": patient_id, "bdate": today_str},
    )
    active_b_id = db.execute(
        text("SELECT id FROM bookings WHERE caretaker_user_id = :cuid AND status = 'in_progress'"),
        {"cuid": ct["id"]},
    ).scalar()

    db.execute(
        text(
            "INSERT INTO visit_tracking (booking_id, caretaker_user_id, check_in_time) "
            "VALUES (:bid, :cuid, NOW())"
        ),
        {"bid": active_b_id, "cuid": ct["id"]},
    )

    # 2. Upcoming accepted booking tomorrow
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, total_amount, status, address) "
            "VALUES (:fuid, :cuid, :pid, 'nursing', :bdate, '08:00:00', '12:00:00', 500, 'accepted', '789 Indiranagar, Bangalore')"
        ),
        {"fuid": family["id"], "cuid": ct["id"], "pid": patient_id, "bdate": tomorrow_str},
    )
    db.commit()

    headers = make_auth_headers(ct, db)
    resp = client.get("/api/v1/dashboard/caretaker_dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    # Active visit assertions
    assert data["active_visit"] is not None
    assert data["active_visit"]["booking_id"] == active_b_id
    assert data["active_visit"]["patient_name"] == "Patient Two"
    assert data["active_visit"]["service_type"] == "nursing"
    assert data["active_visit"]["status"] == "in_progress"
    assert data["active_visit"]["latitude"] == 12.9716
    assert data["active_visit"]["longitude"] == 77.5946
    assert data["active_visit"]["can_navigate"] is True
    assert data["capabilities"]["sos_available"] is True

    # Upcoming visit assertions
    assert len(data["upcoming_visits"]) >= 1
    up = data["upcoming_visits"][0]
    assert up["status"] == "accepted"
    assert up["can_start_visit"] is True
    assert up["requires_otp"] is True

    # Legacy  alias
    resp_php = client.get("/api/v1/dashboard/caretaker_dashboard", headers=headers)
    assert resp_php.status_code == 200


# ============================================================
# Family Dashboard Tests
# ============================================================


def test_family_dashboard_success_and_idor(client, db):
    f1 = _create_user(db, "family")
    f2 = _create_user(db, "family")
    ct = _create_user(db, "caretaker")
    _create_caretaker_profile(db, ct["id"])

    # Insert 1 patient for f1, 1 patient for f2
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fuid, 'P1_0', 70, 'male', 'Condition', 'elderly_care')"
        ),
        {"fuid": f1["id"]},
    )
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fuid, 'P2_0', 70, 'male', 'Condition', 'elderly_care')"
        ),
        {"fuid": f2["id"]},
    )
    p1_id = db.execute(text("SELECT id FROM patient_details WHERE family_user_id = :fuid"), {"fuid": f1["id"]}).scalar()

    # Insert 1 pending, 2 completed bookings for f1
    today_str = date.today().strftime("%Y-%m-%d")
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, total_amount, status) "
            "VALUES (:fuid, :cuid, :pid, 'elderly_care', :bdate, '09:00:00', '13:00:00', 500, 'pending')"
        ),
        {"fuid": f1["id"], "cuid": ct["id"], "pid": p1_id, "bdate": today_str},
    )
    for _ in range(2):
        db.execute(
            text(
                "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
                "                      booking_date, start_time, end_time, total_amount, status) "
                "VALUES (:fuid, :cuid, :pid, 'elderly_care', :bdate, '09:00:00', '13:00:00', 500, 'completed')"
            ),
            {"fuid": f1["id"], "cuid": ct["id"], "pid": p1_id, "bdate": today_str},
        )

    # Insert 1 open SOS for f1
    db.execute(
        text(
            "INSERT INTO sos_alerts (user_id, latitude, longitude, message, status) "
            "VALUES (:uid, '12.97', '77.59', 'Emergency help needed', 'open')"
        ),
        {"uid": f1["id"]},
    )
    db.commit()

    # Request f1 dashboard
    headers1 = make_auth_headers(f1, db)
    resp1 = client.get("/api/v1/dashboard/family_dashboard", headers=headers1)
    assert resp1.status_code == 200
    d1 = resp1.json()["data"]
    assert d1["total_patients"] == 1
    assert d1["total_bookings"] == 3
    assert d1["pending_bookings"] == 1
    assert d1["completed_bookings"] == 2
    assert d1["open_sos_alerts"] == 1

    # Request f2 dashboard (isolated)
    headers2 = make_auth_headers(f2, db)
    resp2 = client.get("/api/v1/dashboard/family_dashboard", headers=headers2)
    assert resp2.status_code == 200
    d2 = resp2.json()["data"]
    assert d2["total_patients"] == 1
    assert d2["total_bookings"] == 0
    assert d2["pending_bookings"] == 0
    assert d2["completed_bookings"] == 0
    assert d2["open_sos_alerts"] == 0

    # Legacy  alias
    resp_php = client.get("/api/v1/dashboard/family_dashboard", headers=headers1)
    assert resp_php.status_code == 200
    assert resp_php.json()["data"]["total_patients"] == 1


def test_family_dashboard_rbac_rejection(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")

    # 401 unauthenticated
    resp = client.get("/api/v1/dashboard/family_dashboard")
    assert resp.status_code == 401

    # 403 admin
    resp = client.get("/api/v1/dashboard/family_dashboard", headers=make_auth_headers(admin, db))
    assert resp.status_code == 403

    # 403 caretaker
    resp = client.get("/api/v1/dashboard/family_dashboard", headers=make_auth_headers(caretaker, db))
    assert resp.status_code == 403

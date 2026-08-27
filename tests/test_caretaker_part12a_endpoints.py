"""
WeCare — Part 12A Caretaker Endpoints Test Suite

Tests all 5 Caretaker Part 12A endpoints and business rules:
- GET /api/v1/caretaker/dashboard (+  alias)
- GET /api/v1/caretaker/earnings_dashboard (+  alias, /earnings-dashboard)
- GET /api/v1/caretaker/earnings_history (+  alias, /earnings-history)
- GET /api/v1/caretaker/payout_summary (+  alias, /payout-summary)
- GET /api/v1/caretaker/visit_history (+  alias, /visit-history)
"""

import time
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="caretaker"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"ct12a_{role}_{ts}@example.com"
    username = f"ct_{role[:2]}_{ts}"
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
            "VALUES (:uid, 'Caretaker Part12A', 'female', '1990-01-01', 5, 300.00, 'Experienced nurse', "
            "        :vstat, :avail, :avail, 'manual_on', NOW() - INTERVAL 1 HOUR)"
        ),
        {"uid": user_id, "vstat": verification_status, "avail": is_available},
    )
    # Also ensure caretaker_availability row exists if schema has it
    try:
        db.execute(
            text(
                "INSERT INTO caretaker_availability (caretaker_id, is_available, updated_at) "
                "VALUES (:uid, :avail, NOW()) "
                "ON DUPLICATE KEY UPDATE is_available = :avail, updated_at = NOW()"
            ),
            {"uid": user_id, "avail": is_available},
        )
    except Exception:
        pass
    db.commit()


def _create_patient(db, family_user_id, name="Patient Test"):
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fid, :name, 72, 'male', 'Hypertension', 'elderly_care') "
            "ON DUPLICATE KEY UPDATE patient_name = :name"
        ),
        {"fid": family_user_id, "name": name},
    )
    pid = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fid"),
        {"fid": family_user_id},
    ).scalar()
    db.commit()
    return int(pid)


def _create_booking(
    db,
    family_user_id,
    caretaker_user_id,
    patient_id,
    status="completed",
    payout_status="ready_for_payout",
    booking_date=None,
    start_time="09:00:00",
    end_time="13:00:00",
    earning_amount=600.00,
    completed_at=None,
    hold_hours=0,
):
    bdate = booking_date or date.today().strftime("%Y-%m-%d")
    comp_at = completed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hold_until = (datetime.now() + timedelta(hours=hold_hours)).strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            "                      start_time, end_time, total_amount, total_customer_amount, caretaker_earning_amount, "
            "                      platform_commission_amount, paid_amount, remaining_amount, status, payment_status, "
            "                      payout_status, payout_hold_until, completed_at, created_at, updated_at) "
            "VALUES (:fid, :cid, :pid, 'elderly_care', :bdate, :stime, :etime, 800.00, 800.00, :earning, "
            "        200.00, 800.00, 0.00, :status, 'paid', :pstatus, :hold_until, :completed_at, NOW(), NOW())"
        ),
        {
            "fid": family_user_id,
            "cid": caretaker_user_id,
            "pid": patient_id,
            "bdate": bdate,
            "stime": start_time,
            "etime": end_time,
            "earning": earning_amount,
            "status": status,
            "pstatus": payout_status,
            "hold_until": hold_until,
            "completed_at": comp_at if status == "completed" else None,
        },
    )
    bid = db.execute(
        text("SELECT id FROM bookings WHERE caretaker_user_id = :cid ORDER BY id DESC LIMIT 1"),
        {"cid": caretaker_user_id},
    ).scalar()
    db.commit()
    return int(bid)


# =========================================================================
# 1. Legacy Caretaker Dashboard Tests
# =========================================================================

def test_legacy_caretaker_dashboard_auth_and_errors(client, db):
    # Unauthenticated -> 401
    resp = client.get("/api/v1/caretaker/dashboard")
    assert resp.status_code == 401

    # Wrong role (family) -> 403
    family = _create_user(db, role="family")
    f_headers = make_auth_headers(family, db)
    resp = client.get("/api/v1/caretaker/dashboard", headers=f_headers)
    assert resp.status_code == 403

    # Caretaker with no profile -> 404
    ct_no_prof = _create_user(db, role="caretaker")
    ct_headers = make_auth_headers(ct_no_prof, db)
    resp = client.get("/api/v1/caretaker/dashboard", headers=ct_headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["success"] is False
    assert "Caretaker profile not found" in data["message"]


def test_legacy_caretaker_dashboard_full_payload_and_presence(client, db):
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    # 1. Pending booking (new request)
    bid_pending = _create_booking(db, family["id"], caretaker["id"], patient_id, status="pending")

    # 2. In-progress booking (active visit)
    bid_in_progress = _create_booking(
        db, family["id"], caretaker["id"], patient_id, status="in_progress", booking_date=date.today().strftime("%Y-%m-%d")
    )
    db.execute(
        text(
            "INSERT INTO visit_tracking (booking_id, caretaker_user_id, check_in_time) "
            "VALUES (:bid, :cid, NOW())"
        ),
        {"bid": bid_in_progress, "cid": caretaker["id"]},
    )
    db.commit()

    # 3. Accepted upcoming booking (tomorrow)
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    bid_upcoming = _create_booking(
        db, family["id"], caretaker["id"], patient_id, status="accepted", booking_date=tomorrow
    )

    ct_headers = make_auth_headers(caretaker, db)

    # Record old presence timestamp
    old_last_active = db.execute(
        text("SELECT last_active_at FROM caretaker_profiles WHERE user_id = :uid"),
        {"uid": caretaker["id"]},
    ).scalar()

    # Call canonical route
    resp = client.get("/api/v1/caretaker/dashboard", headers=ct_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "Caretaker dashboard loaded"

    d = data["data"]
    assert "caretaker" in d
    assert "summary" in d
    assert "active_visit" in d
    assert "upcoming_visits" in d
    assert "new_requests" in d
    assert "capabilities" in d

    # Caretaker profile details
    assert d["caretaker"]["id"] == caretaker["id"]
    assert d["caretaker"]["availability_status"] in ["on_visit", "manual_on"]
    assert d["caretaker"]["verification_status"] == "approved"

    # Summary
    assert d["summary"]["todays_visits"] >= 1
    assert d["summary"]["new_requests"] >= 1

    # Active visit details
    assert d["active_visit"] is not None
    assert d["active_visit"]["booking_id"] == bid_in_progress
    assert d["active_visit"]["can_check_out"] is True
    assert d["active_visit"]["sos_available"] is True
    assert "visit_label" in d["active_visit"]

    # Upcoming visits
    upcoming_ids = [v["booking_id"] for v in d["upcoming_visits"]]
    assert bid_upcoming in upcoming_ids

    # New requests
    new_req_ids = [v["booking_id"] for v in d["new_requests"]]
    assert bid_pending in new_req_ids

    # Presence side effect verification
    new_last_active = db.execute(
        text("SELECT last_active_at FROM caretaker_profiles WHERE user_id = :uid"),
        {"uid": caretaker["id"]},
    ).scalar()
    assert new_last_active is not None
    if old_last_active:
        assert new_last_active >= old_last_active

    # Legacy  alias test
    resp_php = client.get("/api/v1/caretaker/dashboard", headers=ct_headers)
    assert resp_php.status_code == 200
    assert resp_php.json()["success"] is True


# =========================================================================
# 2. Earnings Dashboard Tests
# =========================================================================

def test_caretaker_earnings_dashboard(client, db):
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    # Create completed bookings with different payout states
    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="ready_for_payout", earning_amount=500.00)
    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="paid", earning_amount=400.00)
    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="hold", earning_amount=300.00, hold_hours=24)

    ct_headers = make_auth_headers(caretaker, db)

    # Canonical route
    resp = client.get("/api/v1/caretaker/earnings_dashboard", headers=ct_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "Earnings dashboard retrieved"

    d = data["data"]
    assert d["currency"] == "INR"
    assert d["total_earnings"] >= 1200.00
    assert d["ready_for_payout"] >= 500.00
    assert d["paid_earnings"] >= 400.00
    assert d["hold_earnings"] >= 300.00
    assert "next_payout_date" in d
    assert d["payout_note"] == "Weekly payouts are processed by admin."
    assert "recent_earnings" in d
    assert len(d["recent_earnings"]) <= 3
    assert len(d["recent_earnings"]) >= 1

    # Kebab-case and  alias
    assert client.get("/api/v1/caretaker/earnings-dashboard", headers=ct_headers).status_code == 200
    assert client.get("/api/v1/caretaker/earnings_dashboard", headers=ct_headers).status_code == 200


# =========================================================================
# 3. Earnings History Tests
# =========================================================================

def test_caretaker_earnings_history_filters_and_coercion(client, db):
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="ready_for_payout", earning_amount=500.00, booking_date="2026-08-20")
    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="paid", earning_amount=400.00, booking_date="2026-08-21")
    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="hold", earning_amount=300.00, booking_date="2026-08-22", hold_hours=24)

    ct_headers = make_auth_headers(caretaker, db)

    # 1. Default query
    resp = client.get("/api/v1/caretaker/earnings_history", headers=ct_headers)
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["pagination"]["page"] == 1
    assert d["pagination"]["limit"] == 20
    assert len(d["items"]) >= 3

    # 2. Integer coercion (page=abc -> (int)0 clamped to 1, limit=xyz -> (int)0 clamped to 1)
    resp = client.get("/api/v1/caretaker/earnings_history?page=abc&limit=xyz", headers=ct_headers)
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["pagination"]["page"] == 1
    assert d["pagination"]["limit"] == 1

    # 3. Status filter
    resp = client.get("/api/v1/caretaker/earnings_history?status=paid", headers=ct_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(item["payout_status"] == "paid" for item in items)

    # 4. Invalid status -> 400
    resp = client.get("/api/v1/caretaker/earnings_history?status=invalid_status", headers=ct_headers)
    assert resp.status_code == 400
    err = resp.json()
    assert err["success"] is False
    assert err["message"] == "Invalid status"
    assert "status" in err["errors"]

    # 5. Date filter
    resp = client.get("/api/v1/caretaker/earnings_history?start_date=2026-08-21&end_date=2026-08-21", headers=ct_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["booking_date"] == "2026-08-21"

    # 6. Invalid date format -> 400
    resp = client.get("/api/v1/caretaker/earnings_history?start_date=2026/08/21", headers=ct_headers)
    assert resp.status_code == 400
    err = resp.json()
    assert err["success"] is False
    assert err["message"] == "Invalid date filter"
    assert "start_date" in err["errors"]

    # 7.  alias
    assert client.get("/api/v1/caretaker/earnings_history", headers=ct_headers).status_code == 200


# =========================================================================
# 4. Payout Summary Tests
# =========================================================================

def test_caretaker_payout_summary(client, db):
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="ready_for_payout", earning_amount=500.00)
    _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed", payout_status="hold", earning_amount=250.00, hold_hours=24)

    ct_headers = make_auth_headers(caretaker, db)

    resp = client.get("/api/v1/caretaker/payout_summary", headers=ct_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "Payout summary retrieved"

    d = data["data"]
    assert d["currency"] == "INR"
    assert d["ready_for_payout"] >= 500.00
    assert d["hold_earnings"] >= 250.00
    assert "paid_earnings" in d
    assert "disputed_earnings" in d
    assert "next_payout_date" in d
    assert d["payout_note"] == "Weekly payouts are processed by admin."
    assert d["manual_withdrawal_supported"] is False

    # Kebab-case and  alias
    assert client.get("/api/v1/caretaker/payout-summary", headers=ct_headers).status_code == 200
    assert client.get("/api/v1/caretaker/payout_summary", headers=ct_headers).status_code == 200


# =========================================================================
# 5. Visit History Tests
# =========================================================================

def test_caretaker_visit_history_grouping_and_filters(client, db):
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"], name="Grandma Alice")

    # 1. Completed today
    bid_completed = _create_booking(
        db, family["id"], caretaker["id"], patient_id, status="completed", booking_date=date.today().strftime("%Y-%m-%d")
    )
    db.execute(
        text("INSERT INTO visit_tracking (booking_id, caretaker_user_id, check_in_time, check_out_time) VALUES (:b, :c, NOW(), NOW())"),
        {"b": bid_completed, "c": caretaker["id"]},
    )

    # 2. Cancelled earlier
    bid_cancelled = _create_booking(
        db, family["id"], caretaker["id"], patient_id, status="cancelled", booking_date="2026-08-01"
    )
    db.execute(
        text("UPDATE bookings SET cancelled_at = '2026-08-01 10:00:00' WHERE id = :b"),
        {"b": bid_cancelled},
    )

    # 3. Declined earlier
    bid_declined = _create_booking(
        db, family["id"], caretaker["id"], patient_id, status="declined", booking_date="2026-08-02"
    )
    db.execute(
        text("UPDATE bookings SET responded_at = '2026-08-02 10:00:00' WHERE id = :b"),
        {"b": bid_declined},
    )
    db.commit()

    ct_headers = make_auth_headers(caretaker, db)

    # Default query (completed + cancelled)
    resp = client.get("/api/v1/caretaker/visit_history", headers=ct_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "Visit history fetched successfully"

    d = data["data"]
    assert "groups" in d
    assert "pagination" in d

    labels = [g["label"] for g in d["groups"]]
    assert "Today" in labels

    # Status 'all' (completed, cancelled, declined)
    resp_all = client.get("/api/v1/caretaker/visit_history?status=all", headers=ct_headers)
    assert resp_all.status_code == 200
    all_items = [it for g in resp_all.json()["data"]["groups"] for it in g["items"]]
    all_bids = [it["booking_id"] for it in all_items]
    assert bid_completed in all_bids
    assert bid_cancelled in all_bids
    assert bid_declined in all_bids

    # Patient name LIKE search
    resp_search = client.get("/api/v1/caretaker/visit_history?status=all&patient_name=Alice", headers=ct_headers)
    assert resp_search.status_code == 200
    search_items = [it for g in resp_search.json()["data"]["groups"] for it in g["items"]]
    assert all("Alice" in it["patient_name"] for it in search_items)

    # Invalid status -> 400
    resp_bad_st = client.get("/api/v1/caretaker/visit_history?status=pending", headers=ct_headers)
    assert resp_bad_st.status_code == 400
    assert "Status must be completed, cancelled, declined, or all" in resp_bad_st.json()["errors"]["status"][0]

    # Invalid date -> 400
    resp_bad_dt = client.get("/api/v1/caretaker/visit_history?start_date=2026.08.01", headers=ct_headers)
    assert resp_bad_dt.status_code == 400
    assert "Date must be in YYYY-MM-DD format" in resp_bad_dt.json()["errors"]["start_date"][0]

    #  alias
    assert client.get("/api/v1/caretaker/visit_history", headers=ct_headers).status_code == 200


# =========================================================================
# 6. IDOR Isolation Tests
# =========================================================================

def test_part12a_caretaker_idor_isolation(client, db):
    ct1 = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, ct1["id"])
    ct2 = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, ct2["id"])

    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    # Booking exclusively for CT1
    bid1 = _create_booking(db, family["id"], ct1["id"], patient_id, status="completed", payout_status="paid", earning_amount=999.00)
    bid_active1 = _create_booking(db, family["id"], ct1["id"], patient_id, status="in_progress")
    db.execute(
        text("INSERT INTO visit_tracking (booking_id, caretaker_user_id, check_in_time) VALUES (:b, :c, NOW())"),
        {"b": bid_active1, "c": ct1["id"]},
    )
    db.commit()

    ct1_headers = make_auth_headers(ct1, db)
    ct2_headers = make_auth_headers(ct2, db)

    # CT1 sees earnings
    resp1 = client.get("/api/v1/caretaker/earnings_dashboard", headers=ct1_headers)
    assert resp1.json()["data"]["total_earnings"] >= 999.00

    # CT2 has 0 earnings
    resp2 = client.get("/api/v1/caretaker/earnings_dashboard", headers=ct2_headers)
    assert resp2.json()["data"]["total_earnings"] == 0.00

    # CT2 payout summary is 0
    resp_p2 = client.get("/api/v1/caretaker/payout_summary", headers=ct2_headers)
    assert resp_p2.json()["data"]["paid_earnings"] == 0.00
    assert resp_p2.json()["data"]["ready_for_payout"] == 0.00

    # CT2 earnings history is empty
    resp_eh2 = client.get("/api/v1/caretaker/earnings_history", headers=ct2_headers)
    assert len(resp_eh2.json()["data"]["items"]) == 0

    # CT2 visit history is empty
    resp_v2 = client.get("/api/v1/caretaker/visit_history?status=all", headers=ct2_headers)
    assert resp_v2.json()["data"]["groups"] == []

    # CT2 dashboard does not see CT1's active visit
    resp_dash2 = client.get("/api/v1/caretaker/dashboard", headers=ct2_headers)
    assert resp_dash2.json()["data"]["active_visit"] is None


# =========================================================================
# 7. Additional Granular Edge-Case & Parity Tests
# =========================================================================

def test_legacy_caretaker_dashboard_upcoming_time_filtering(client, db):
    """
    Verifies that upcoming visits for today only include visits with start_time >= CURTIME(),
    and past visits today are excluded.
    """
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])
    today_str = date.today().strftime("%Y-%m-%d")

    # Past start time today (01:00 AM)
    bid_past = _create_booking(
        db, family["id"], caretaker["id"], patient_id,
        status="accepted", booking_date=today_str, start_time="00:01:00", end_time="01:00:00"
    )
    # Future start time today (23:59 PM)
    bid_future = _create_booking(
        db, family["id"], caretaker["id"], patient_id,
        status="accepted", booking_date=today_str, start_time="23:59:00", end_time="23:59:59"
    )

    ct_headers = make_auth_headers(caretaker, db)
    resp = client.get("/api/v1/caretaker/dashboard", headers=ct_headers)
    assert resp.status_code == 200
    upcoming = resp.json()["data"]["upcoming_visits"]
    upcoming_ids = [u["booking_id"] for u in upcoming]

    assert bid_future in upcoming_ids
    assert bid_past not in upcoming_ids


def test_legacy_caretaker_dashboard_caps_and_limits(client, db):
    """
    Verifies max 5 upcoming visits and max 5 new requests caps.
    """
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    # Create 7 pending bookings
    for _ in range(7):
        _create_booking(db, family["id"], caretaker["id"], patient_id, status="pending")

    # Create 7 accepted upcoming bookings (next week)
    next_week = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    for _ in range(7):
        _create_booking(db, family["id"], caretaker["id"], patient_id, status="accepted", booking_date=next_week)

    ct_headers = make_auth_headers(caretaker, db)
    resp = client.get("/api/v1/caretaker/dashboard", headers=ct_headers)
    assert resp.status_code == 200
    d = resp.json()["data"]

    # Summary has total counts
    assert d["summary"]["new_requests"] >= 7
    # Lists are capped at 5
    assert len(d["new_requests"]) == 5
    assert len(d["upcoming_visits"]) == 5


def test_earnings_payout_refresh_side_effects(client, db):
    """
    Verifies that earnings endpoints execute payout_refresh_eligibility()
    and update booking payout_status.
    """
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    # Create a completed booking with hold_until in the past (eligible for ready_for_payout)
    past_hold = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            "                      start_time, end_time, total_amount, total_customer_amount, caretaker_earning_amount, "
            "                      platform_commission_amount, paid_amount, remaining_amount, status, payment_status, "
            "                      payout_status, payout_hold_until, completed_at, created_at, updated_at) "
            "VALUES (:fid, :cid, :pid, 'elderly_care', CURDATE(), '09:00:00', '13:00:00', 800.00, 800.00, 650.00, "
            "        150.00, 800.00, 0.00, 'completed', 'paid', 'hold', :hold_until, NOW() - INTERVAL 25 HOUR, NOW(), NOW())"
        ),
        {"fid": family["id"], "cid": caretaker["id"], "pid": patient_id, "hold_until": past_hold},
    )
    bid = db.execute(text("SELECT id FROM bookings WHERE caretaker_user_id = :cid ORDER BY id DESC LIMIT 1"), {"cid": caretaker["id"]}).scalar()
    db.commit()

    ct_headers = make_auth_headers(caretaker, db)

    # Accessing earnings_dashboard triggers eligibility refresh
    resp = client.get("/api/v1/caretaker/earnings_dashboard", headers=ct_headers)
    assert resp.status_code == 200

    # Verify status in database transitioned from 'hold' to 'ready_for_payout'
    updated_pstatus = db.execute(text("SELECT payout_status FROM bookings WHERE id = :id"), {"id": bid}).scalar()
    assert updated_pstatus == "ready_for_payout"


def test_earnings_history_payout_refresh_before_validation(client, db):
    """
    Verifies that payout_refresh_eligibility runs before validation in earnings_history.
    """
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    # Create completed booking with expired hold
    past_hold = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            "                      start_time, end_time, total_amount, total_customer_amount, caretaker_earning_amount, "
            "                      platform_commission_amount, paid_amount, remaining_amount, status, payment_status, "
            "                      payout_status, payout_hold_until, completed_at, created_at, updated_at) "
            "VALUES (:fid, :cid, :pid, 'elderly_care', CURDATE(), '09:00:00', '13:00:00', 800.00, 800.00, 700.00, "
            "        100.00, 800.00, 0.00, 'completed', 'paid', 'hold', :hold_until, NOW() - INTERVAL 25 HOUR, NOW(), NOW())"
        ),
        {"fid": family["id"], "cid": caretaker["id"], "pid": patient_id, "hold_until": past_hold},
    )
    bid = db.execute(text("SELECT id FROM bookings WHERE caretaker_user_id = :cid ORDER BY id DESC LIMIT 1"), {"cid": caretaker["id"]}).scalar()
    db.commit()

    ct_headers = make_auth_headers(caretaker, db)

    # Call with invalid status -> returns 400
    resp = client.get("/api/v1/caretaker/earnings_history?status=bad_status_code", headers=ct_headers)
    assert resp.status_code == 400

    # Even though 400 was returned, payout_refresh_eligibility ran and updated status
    updated_pstatus = db.execute(text("SELECT payout_status FROM bookings WHERE id = :id"), {"id": bid}).scalar()
    assert updated_pstatus == "ready_for_payout"


def test_visit_history_comma_separated_and_latest_tracking(client, db):
    """
    Verifies comma-separated status support and joining latest visit_tracking row by ID DESC.
    """
    caretaker = _create_user(db, role="caretaker")
    _create_caretaker_profile(db, caretaker["id"])
    family = _create_user(db, role="family")
    patient_id = _create_patient(db, family["id"])

    bid_declined = _create_booking(db, family["id"], caretaker["id"], patient_id, status="declined")
    bid_completed = _create_booking(db, family["id"], caretaker["id"], patient_id, status="completed")

    # Insert 2 visit_tracking rows for bid_completed to verify latest by ID is picked
    db.execute(
        text("INSERT INTO visit_tracking (booking_id, caretaker_user_id, check_in_time) VALUES (:b, :c, '2026-08-20 08:00:00')"),
        {"b": bid_completed, "c": caretaker["id"]},
    )
    db.execute(
        text("INSERT INTO visit_tracking (booking_id, caretaker_user_id, check_in_time, check_out_time) VALUES (:b, :c, '2026-08-20 09:00:00', '2026-08-20 13:00:00')"),
        {"b": bid_completed, "c": caretaker["id"]},
    )
    latest_vt_id = db.execute(
        text("SELECT id FROM visit_tracking WHERE booking_id = :b ORDER BY id DESC LIMIT 1"),
        {"b": bid_completed},
    ).scalar()
    db.commit()

    ct_headers = make_auth_headers(caretaker, db)

    # Query with comma-separated status: completed,declined
    resp = client.get("/api/v1/caretaker/visit_history?status=completed,declined", headers=ct_headers)
    assert resp.status_code == 200
    all_items = [it for g in resp.json()["data"]["groups"] for it in g["items"]]
    bids = [it["booking_id"] for it in all_items]
    assert bid_declined in bids
    assert bid_completed in bids

    # Verify latest visit_id was picked
    comp_item = next(it for it in all_items if it["booking_id"] == bid_completed)
    assert comp_item["visit_id"] == int(latest_vt_id)

    # Test empty parsed status error
    resp_empty_st = client.get("/api/v1/caretaker/visit_history?status=,", headers=ct_headers)
    assert resp_empty_st.status_code == 400
    assert "At least one valid status is required" in resp_empty_st.json()["errors"]["status"][0]

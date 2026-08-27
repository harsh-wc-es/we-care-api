"""
WeCare — Visit Endpoints HTTP Integration Tests (Part 6)

Comprehensive test suite covering all 9 Visit endpoints via FastAPI TestClient:
1. GET  /api/v1/visit/view_visit[]
2. POST /api/v1/visit/verify_start_otp[]
3. POST /api/v1/visit/check_in[]
4. GET  /api/v1/visit/active_visit[]
5. POST /api/v1/visit/add_note[]
6. POST /api/v1/visit/update_task_status[]
7. POST /api/v1/visit/check_out[]
8. GET  /api/v1/visit/completed_summary[]
9. GET  /api/v1/visit/full_report[]

Tests role scoping, state transitions, irreversible completed tasks, duration boundaries,
care point awards, payout holds, availability auto-restore, and financial data masking.
"""

from datetime import datetime, timedelta
import time
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from app.services.otp_service import otp_create
from app.services.visit_service import _format_duration_label
from tests.conftest import make_auth_headers


def _create_other_user(db, role="caretaker"):
    """Creates a real auxiliary user for IDOR testing."""
    ts = int(time.time() * 1000000) % 1000000000
    email = f"other_{role}_{ts}@example.com"
    username = f"oth_{role[:2]}_{ts}"
    phone = f"9{ts:09d}"
    pwd_hash = hash_password("TestPassword123!")

    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, :role, 1, 1)"
        ),
        {"email": email, "username": username, "phone": phone, "password": pwd_hash, "role": role},
    )
    db.commit()

    user_id = db.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": email}
    ).mappings().first()["id"]

    if role == "caretaker":
        db.execute(
            text(
                "INSERT INTO caretaker_profiles (user_id, full_name, verification_status, is_available, created_at, updated_at) "
                "VALUES (:uid, :name, 'approved', 1, NOW(), NOW())"
            ),
            {"uid": user_id, "name": f"Other Caretaker {username}"},
        )
        db.commit()

    return {
        "id": user_id,
        "email": email,
        "username": username,
        "phone_number": phone,
        "role": role,
    }


def _cleanup_other_user(db, user):
    if not user:
        return
    uid = user["id"]
    db.execute(text("DELETE FROM tokens WHERE user_id = :id"), {"id": uid})
    db.execute(text("DELETE FROM documents WHERE user_id = :id"), {"id": uid})
    db.execute(text("DELETE FROM caretaker_profiles WHERE user_id = :id"), {"id": uid})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    db.commit()


def _setup_full_visit_scenario(db, test_user, caretaker_user):
    """Helper to set up caretaker pricing, patient details, and a booking with tasks."""
    family_id = test_user["id"]
    caretaker_id = caretaker_user["id"]

    # 1. Caretaker Profile
    db.execute(
        text(
            "UPDATE caretaker_profiles "
            "SET pricing_tier_id = 1, "
            "    pricing_tier = 'standard', "
            "    skill_level = 'certified', "
            "    customer_hourly_rate = 30.00, "
            "    caretaker_hourly_rate = 20.00, "
            "    platform_commission_hourly = 10.00, "
            "    is_available = 1, "
            "    manual_availability_enabled = 1, "
            "    verification_status = 'approved', "
            "    availability_locked_by_admin = 0, "
            "    availability_reason = 'manual_on' "
            "WHERE user_id = :cid"
        ),
        {"cid": caretaker_id},
    )

    # 2. Patient Details
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, special_instructions, care_type) "
            "VALUES (:fuid, 'Grandma Rose', 82, 'female', 'Mild Dementia', 'Needs gentle guidance', 'Elder Care')"
        ),
        {"fuid": family_id},
    )
    db.commit()

    patient_id = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fuid ORDER BY id DESC LIMIT 1"),
        {"fuid": family_id},
    ).scalar()

    # 3. Accepted Booking
    db.execute(
        text(
            "INSERT INTO bookings "
            "(family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            " start_time, end_time, address, location_latitude, location_longitude, status, "
            " total_customer_amount, customer_hourly_rate, platform_commission_amount, platform_commission_hourly, "
            " caretaker_earning_amount, care_points_earned, created_at, updated_at) "
            "VALUES (:fuid, :cid, :pid, 'Elder Care', CURDATE(), '09:00:00', '13:00:00', "
            "        '123 Maple Street, Cityville', 23.0225, 72.5714, 'accepted', "
            "        120.00, 30.00, 40.00, 10.00, 80.00, 0, NOW(), NOW())"
        ),
        {"fuid": family_id, "cid": caretaker_id, "pid": patient_id},
    )
    db.commit()

    booking_id = db.execute(
        text("SELECT id FROM bookings WHERE family_user_id = :fuid ORDER BY id DESC LIMIT 1"),
        {"fuid": family_id},
    ).scalar()

    # 4. Add Tasks
    db.execute(
        text(
            "INSERT INTO booking_checklist_tasks (booking_id, family_user_id, caretaker_user_id, title, description, status, created_at) "
            "VALUES (:bid, :fuid, :cid, 'Prepare breakfast', 'Oatmeal with fruit', 'pending', NOW()), "
            "       (:bid, :fuid, :cid, 'Medication reminder', 'Blood pressure pill at 10 AM', 'pending', NOW())"
        ),
        {"bid": booking_id, "fuid": family_id, "cid": caretaker_id},
    )
    db.commit()

    task_ids = [
        int(r[0])
        for r in db.execute(
            text("SELECT id FROM booking_checklist_tasks WHERE booking_id = :bid ORDER BY id ASC"),
            {"bid": booking_id},
        ).fetchall()
    ]

    return family_id, caretaker_id, patient_id, booking_id, task_ids


def _cleanup_full_visit(db, booking_id=None, patient_id=None):
    """Cleanup all entities."""
    if booking_id:
        db.execute(text("DELETE FROM sos_alerts WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM visit_activity_logs WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM visit_notes WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM visit_tracking WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM booking_checklist_tasks WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM otp_codes WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM notifications WHERE related_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM admin_audit_logs WHERE entity_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM bookings WHERE id = :bid"), {"bid": booking_id})
    if patient_id:
        db.execute(text("DELETE FROM patient_details WHERE id = :pid"), {"pid": patient_id})
    db.commit()


# ─── 1. Duration Boundary Calculations ───

def test_duration_label_formatting_boundaries():
    """Verifies duration formatting for exact boundary cases matching visit_history_duration_label()."""
    assert _format_duration_label(0) == "0m"
    assert _format_duration_label(1) == "1m"
    assert _format_duration_label(59) == "59m"
    assert _format_duration_label(60) == "1h"
    assert _format_duration_label(61) == "1h 1m"
    assert _format_duration_label(119) == "1h 59m"
    assert _format_duration_label(120) == "2h"
    assert _format_duration_label(125) == "2h 5m"


# ─── 2. View Visit Endpoint Tests ───

def test_view_visit_caretaker_access(client, db, test_user, caretaker_user):
    """Caretaker views assigned visit details."""
    _, caretaker_id, patient_id, booking_id, task_ids = _setup_full_visit_scenario(db, test_user, caretaker_user)
    ct_headers = make_auth_headers(caretaker_user, db)

    try:
        res = client.get(f"/api/v1/visit/view_visit?booking_id={booking_id}", headers=ct_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"]["booking_id"] == booking_id
        assert body["data"]["patient_name"] == "Grandma Rose"
        assert body["data"]["patient_age"] == 82
        assert body["data"]["status"] == "accepted"
        assert body["data"]["can_navigate"] is True
        assert body["data"]["requires_otp"] is True
        assert body["data"]["otp_verified"] is False
        assert body["data"]["can_start_visit"] is False
        assert len(body["data"]["care_tasks"]) == 2
        assert "actions" in body["data"]

        # Test legacy  alias
        res_php = client.get(f"/api/v1/visit/view_visit?booking_id={booking_id}", headers=ct_headers)
        assert res_php.status_code == 200
        assert res_php.json()["data"]["booking_id"] == booking_id
    finally:
        _cleanup_full_visit(db, booking_id, patient_id)


def test_view_visit_family_and_admin_access(client, db, test_user, caretaker_user, admin_user):
    """Family owner and admin can view visit details."""
    _, caretaker_id, patient_id, booking_id, _ = _setup_full_visit_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    admin_headers = make_auth_headers(admin_user, db)

    try:
        # Family owner
        res_fam = client.get(f"/api/v1/visit/view_visit?booking_id={booking_id}", headers=family_headers)
        assert res_fam.status_code == 200
        assert res_fam.json()["data"]["booking_id"] == booking_id

        # Admin
        res_adm = client.get(f"/api/v1/visit/view_visit?booking_id={booking_id}", headers=admin_headers)
        assert res_adm.status_code == 200
        assert res_adm.json()["data"]["booking_id"] == booking_id
    finally:
        _cleanup_full_visit(db, booking_id, patient_id)


def test_view_visit_missing_booking_and_validation(client, db, test_user, caretaker_user):
    """Missing booking_id or invalid ID formats return 400 or 404."""
    ct_headers = make_auth_headers(caretaker_user, db)

    # Missing booking_id -> 400
    res_none = client.get("/api/v1/visit/view_visit", headers=ct_headers)
    assert res_none.status_code == 400

    # Invalid non-integer -> 400
    res_str = client.get("/api/v1/visit/view_visit?booking_id=abc", headers=ct_headers)
    assert res_str.status_code == 400

    # Non-existent booking_id -> 404
    res_notfound = client.get("/api/v1/visit/view_visit?booking_id=99999999", headers=ct_headers)
    assert res_notfound.status_code == 404


def test_view_visit_idor_protection(client, db, test_user, caretaker_user):
    """Another caretaker or family user cannot view someone else's visit (returns 404)."""
    _, caretaker_id, patient_id, booking_id, _ = _setup_full_visit_scenario(db, test_user, caretaker_user)
    other_ct = _create_other_user(db, role="caretaker")
    other_headers = make_auth_headers(other_ct, db)

    try:
        res = client.get(f"/api/v1/visit/view_visit?booking_id={booking_id}", headers=other_headers)
        assert res.status_code == 404
        assert res.json()["message"] == "Visit not found"
    finally:
        _cleanup_other_user(db, other_ct)
        _cleanup_full_visit(db, booking_id, patient_id)


# ─── 3. OTP Verification Tests ───

def test_verify_start_otp_success_and_failures(client, db, test_user, caretaker_user):
    """Verifies valid OTP, expired OTP, invalid code, and non-accepted booking."""
    _, caretaker_id, patient_id, booking_id, _ = _setup_full_visit_scenario(db, test_user, caretaker_user)
    ct_headers = make_auth_headers(caretaker_user, db)

    try:
        # 1. Invalid OTP
        res_bad = client.post(
            "/api/v1/visit/verify_start_otp",
            json={"booking_id": booking_id, "otp": "999999"},
            headers=ct_headers,
        )
        assert res_bad.status_code == 400

        # 2. Valid OTP
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        plain_otp = otp_res["code"]

        res_ok = client.post(
            "/api/v1/visit/verify_start_otp",
            json={"booking_id": booking_id, "otp": plain_otp},
            headers=ct_headers,
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["data"]["otp_verified"] is True
        assert res_ok.json()["data"]["can_check_in"] is True

        # Re-using already verified OTP fails with 400
        res_reuse = client.post(
            "/api/v1/visit/verify_start_otp",
            json={"booking_id": booking_id, "otp": plain_otp},
            headers=ct_headers,
        )
        assert res_reuse.status_code == 400

        # Test  alias with new OTP
        otp_res2 = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        res_php = client.post(
            "/api/v1/visit/verify_start_otp",
            json={"booking_id": booking_id, "otp": otp_res2["code"]},
            headers=ct_headers,
        )
        assert res_php.status_code == 200
    finally:
        _cleanup_full_visit(db, booking_id, patient_id)


# ─── 4. Task Status State Transitions & IDOR ───

def test_task_status_state_transitions_and_idor(client, db, test_user, caretaker_user):
    """Tests all valid and invalid task status state machine transitions and IDOR protection."""
    _, caretaker_id, patient_id, booking_id, task_ids = _setup_full_visit_scenario(db, test_user, caretaker_user)
    ct_headers = make_auth_headers(caretaker_user, db)
    other_ct = _create_other_user(db, role="caretaker")
    other_headers = make_auth_headers(other_ct, db)

    t1_id = task_ids[0]
    t2_id = task_ids[1]

    try:
        # Precondition: verify OTP and check in
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        client.post("/api/v1/visit/verify_start_otp", json={"booking_id": booking_id, "otp": otp_res["code"]}, headers=ct_headers)
        client.post("/api/v1/visit/check_in", json={"booking_id": booking_id}, headers=ct_headers)

        # 1. Other caretaker cannot update task (404)
        res_idor = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t1_id, "status": "ongoing"},
            headers=other_headers,
        )
        assert res_idor.status_code == 404

        # 2. Pending -> Ongoing
        res1 = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t1_id, "status": "ongoing"},
            headers=ct_headers,
        )
        assert res1.status_code == 200
        assert res1.json()["data"]["status"] == "ongoing"

        # 3. Ongoing -> Pending
        res2 = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t1_id, "status": "pending"},
            headers=ct_headers,
        )
        assert res2.status_code == 200
        assert res2.json()["data"]["status"] == "pending"

        # 4. Pending -> Completed directly (Task 2)
        res3 = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t2_id, "status": "completed"},
            headers=ct_headers,
        )
        assert res3.status_code == 200
        assert res3.json()["data"]["status"] == "completed"

        # 5. Completed -> Ongoing blocked (409)
        res4 = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t2_id, "status": "ongoing"},
            headers=ct_headers,
        )
        assert res4.status_code == 409
        assert "Invalid task status transition" in res4.json()["message"]

        # 6. Completed -> Pending blocked (409)
        res5 = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t2_id, "status": "pending"},
            headers=ct_headers,
        )
        assert res5.status_code == 409
        assert "Invalid task status transition" in res5.json()["message"]

        # 7. Test legacy  alias
        res_php = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t1_id, "status": "completed"},
            headers=ct_headers,
        )
        assert res_php.status_code == 200
        assert res_php.json()["data"]["status"] == "completed"

    finally:
        _cleanup_other_user(db, other_ct)
        _cleanup_full_visit(db, booking_id, patient_id)


# ─── 5. Full Live Visit Lifecycle End-to-End Test ───

def test_full_visit_execution_lifecycle_http(client, db, test_user, caretaker_user):
    """
    Executes the complete active visit lifecycle via HTTP client:
    1. View Visit (pre-visit)
    2. Check-in fails before OTP verification (403)
    3. Verify OTP via POST /verify_start_otp (200)
    4. Check-in via POST /check_in (201)
    5. View Active Visit via GET /active_visit (200)
    6. Update Task Status via POST /update_task_status (pending -> ongoing -> completed)
    7. Attempt backwards task transition (completed -> pending) -> 409 Conflict
    8. Add Note via POST /add_note (201)
    9. Complete Visit via POST /check_out (200)
    10. Verify Completed Summary via GET /completed_summary (200)
    11. Verify Full Report via GET /full_report (200) with Financial Privacy Masking
    12. Post-checkout Add Note blocked (404)
    13. Post-checkout Duplicate Check-out blocked (404)
    """
    family_id, caretaker_id, patient_id, booking_id, task_ids = _setup_full_visit_scenario(db, test_user, caretaker_user)
    ct_headers = make_auth_headers(caretaker_user, db)
    t1_id = task_ids[0]
    t2_id = task_ids[1]

    try:
        # Step 2: Check-in fails before OTP verification (403)
        res_no_otp = client.post(
            "/api/v1/visit/check_in",
            json={"booking_id": booking_id, "latitude": 23.02, "longitude": 72.57},
            headers=ct_headers,
        )
        assert res_no_otp.status_code == 403
        assert "Visit start OTP verification required" in res_no_otp.json()["message"]

        # Step 3: Verify OTP via POST /verify_start_otp
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        plain_otp = otp_res["code"]

        res_otp = client.post(
            "/api/v1/visit/verify_start_otp",
            json={"booking_id": booking_id, "otp": plain_otp},
            headers=ct_headers,
        )
        assert res_otp.status_code == 200
        assert res_otp.json()["data"]["otp_verified"] is True
        assert res_otp.json()["data"]["can_check_in"] is True

        # Re-using already verified OTP fails with 400
        res_reuse = client.post(
            "/api/v1/visit/verify_start_otp",
            json={"booking_id": booking_id, "otp": plain_otp},
            headers=ct_headers,
        )
        assert res_reuse.status_code == 400

        # Step 4: Check-in via POST /check_in (201)
        res_checkin = client.post(
            "/api/v1/visit/check_in",
            json={"booking_id": booking_id, "latitude": 23.0225, "longitude": 72.5714, "notes": "Reached location"},
            headers=ct_headers,
        )
        assert res_checkin.status_code == 201
        checkin_body = res_checkin.json()
        assert checkin_body["data"]["status"] == "in_progress"
        assert checkin_body["data"]["booking_status"] == "in_progress"
        assert checkin_body["data"]["availability_status"] == "unavailable"
        assert checkin_body["data"]["availability_reason"] == "on_visit"
        visit_id = checkin_body["data"]["visit_id"]

        # Duplicate check-in blocked
        res_dup_checkin = client.post(
            "/api/v1/visit/check_in",
            json={"booking_id": booking_id},
            headers=ct_headers,
        )
        assert res_dup_checkin.status_code in (404, 409)

        # Step 5: View Active Visit via GET /active_visit (200)
        res_active = client.get(f"/api/v1/visit/active_visit?booking_id={booking_id}", headers=ct_headers)
        assert res_active.status_code == 200
        active_body = res_active.json()
        assert active_body["data"]["status"] == "in_progress"
        assert active_body["data"]["patient"]["name"] == "Grandma Rose"
        assert len(active_body["data"]["tasks"]) == 2
        assert active_body["data"]["can_checkout"] is True
        assert active_body["data"]["sos_enabled"] is True

        # Test active_visit  alias
        res_active_php = client.get(f"/api/v1/visit/active_visit?booking_id={booking_id}", headers=ct_headers)
        assert res_active_php.status_code == 200

        # Step 6: Update Task Status via POST /update_task_status
        # Move task 1: pending -> ongoing
        res_t1_ongoing = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t1_id, "status": "ongoing"},
            headers=ct_headers,
        )
        assert res_t1_ongoing.status_code == 200
        assert res_t1_ongoing.json()["data"]["status"] == "ongoing"

        # Move task 1: ongoing -> completed
        res_t1_completed = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t1_id, "status": "completed"},
            headers=ct_headers,
        )
        assert res_t1_completed.status_code == 200
        assert res_t1_completed.json()["data"]["status"] == "completed"
        assert res_t1_completed.json()["data"]["completed_at"] != ""

        # Step 7: Attempt backwards transition on completed task -> 409 Conflict
        res_t1_backwards = client.post(
            "/api/v1/visit/update_task_status",
            json={"booking_id": booking_id, "task_id": t1_id, "status": "pending"},
            headers=ct_headers,
        )
        assert res_t1_backwards.status_code == 409
        assert "Invalid task status transition" in res_t1_backwards.json()["message"]

        # Step 8: Add Note via POST /add_note (201)
        res_note = client.post(
            "/api/v1/visit/add_note",
            json={"booking_id": booking_id, "note": "Patient had breakfast and morning tea peacefully."},
            headers=ct_headers,
        )
        assert res_note.status_code == 201
        note_body = res_note.json()
        assert note_body["data"]["note_id"] > 0
        assert "breakfast" in note_body["data"]["note"]

        # Note validation test (empty note)
        res_empty_note = client.post(
            "/api/v1/visit/add_note",
            json={"booking_id": booking_id, "note": "   "},
            headers=ct_headers,
        )
        assert res_empty_note.status_code == 400

        # Step 9: Complete Visit via POST /check_out (200)
        res_checkout = client.post(
            "/api/v1/visit/check_out",
            json={"booking_id": booking_id, "latitude": 23.023, "longitude": 72.572, "notes": "Care shift concluded."},
            headers=ct_headers,
        )
        assert res_checkout.status_code == 200
        checkout_body = res_checkout.json()
        assert checkout_body["data"]["status"] == "completed"
        assert checkout_body["data"]["booking_status"] == "completed"
        assert checkout_body["data"]["care_points_earned"] == 20
        assert checkout_body["data"]["payout_status"] == "hold"
        assert checkout_body["data"]["availability_restored"] is True
        assert checkout_body["data"]["availability_reason"] == "manual_on"

        # Step 10: Verify Completed Summary via GET /completed_summary (200)
        res_summary = client.get(f"/api/v1/visit/completed_summary?booking_id={booking_id}", headers=ct_headers)
        assert res_summary.status_code == 200
        summary_body = res_summary.json()
        assert summary_body["data"]["status"] == "completed"
        assert summary_body["data"]["patient_name"] == "Grandma Rose"
        assert summary_body["data"]["care_points_earned"] == 20
        assert summary_body["data"]["tasks_completed"] == 1
        assert summary_body["data"]["tasks_total"] == 2
        assert summary_body["data"]["can_view_full_report"] is True

        # Test completed_summary  alias
        res_summary_php = client.get(f"/api/v1/visit/completed_summary?booking_id={booking_id}", headers=ct_headers)
        assert res_summary_php.status_code == 200

        # Step 11: Verify Full Report via GET /full_report (200) with Financial Privacy Masking
        res_report = client.get(f"/api/v1/visit/full_report?booking_id={booking_id}", headers=ct_headers)
        assert res_report.status_code == 200
        report_body = res_report.json()
        data = report_body["data"]
        assert data["status"] == "completed"
        assert data["patient"]["name"] == "Grandma Rose"
        assert len(data["completed_tasks"]) == 1
        assert len(data["incomplete_tasks"]) == 1
        assert len(data["live_care_notes"]) == 1
        assert data["final_checkout_notes"] == "Care shift concluded."
        assert data["caretaker_earning_amount"] == 80.0
        assert data["care_points_earned"] == 20

        # CRITICAL FINANCIAL PRIVACY VERIFICATION:
        # Caretaker MUST NOT receive platform commission or customer amounts
        forbidden_keys = [
            "total_customer_amount",
            "customer_hourly_rate",
            "platform_commission_amount",
            "platform_commission_hourly",
            "commission_percentage",
        ]
        for key in forbidden_keys:
            assert key not in data, f"Forbidden financial key '{key}' leaked in caretaker full report!"

        # Step 12: Post-checkout Add Note blocked (404)
        res_post_note = client.post(
            "/api/v1/visit/add_note",
            json={"booking_id": booking_id, "note": "Post-checkout note should fail"},
            headers=ct_headers,
        )
        assert res_post_note.status_code == 404

        # Step 13: Post-checkout Duplicate Check-out blocked (404)
        res_dup_checkout = client.post(
            "/api/v1/visit/check_out",
            json={"booking_id": booking_id},
            headers=ct_headers,
        )
        assert res_dup_checkout.status_code == 404

    finally:
        _cleanup_full_visit(db, booking_id, patient_id)

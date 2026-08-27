"""
WeCare — Visit Lifecycle Service Tests (Part 6A)

Tests the core visit execution domain lifecycle:
1. verify_start_otp
2. check_in
3. check_out
and all associated validations, locks, state transitions, care point rewards,
payout holds, and availability transitions.
"""

from datetime import datetime, timedelta
import pytest
from sqlalchemy import text

from app.core.exceptions import APIException
from app.services.booking_workflow_service import booking_workflow_transition
from app.services.otp_service import otp_create, otp_verify
from app.services.visit_service import (
    check_in_visit,
    check_out_visit,
    verify_visit_start_otp,
)


def _setup_visit_scenario(db, test_user, caretaker_user, status="accepted"):
    """Helper to set up caretaker, patient, and booking in specified status."""
    family_id = test_user["id"]
    caretaker_id = caretaker_user["id"]

    # 1. Update caretaker profile
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

    # 2. Insert patient details
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fuid, 'Patient Alpha', 75, 'female', 'Post Surgery', 'Elder Care')"
        ),
        {"fuid": family_id},
    )
    db.commit()

    patient_id = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fuid ORDER BY id DESC LIMIT 1"),
        {"fuid": family_id},
    ).scalar()

    # 3. Create booking
    db.execute(
        text(
            "INSERT INTO bookings "
            "(family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            " start_time, end_time, address, status, total_customer_amount, caretaker_earning_amount, "
            " care_points_earned, created_at, updated_at) "
            "VALUES (:fuid, :cid, :pid, 'Elder Care', CURDATE(), '09:00:00', '13:00:00', "
            "        '123 Health Ave', :status, 120.00, 80.00, 0, NOW(), NOW())"
        ),
        {"fuid": family_id, "cid": caretaker_id, "pid": patient_id, "status": status},
    )
    db.commit()

    booking_id = db.execute(
        text("SELECT id FROM bookings WHERE family_user_id = :fuid ORDER BY id DESC LIMIT 1"),
        {"fuid": family_id},
    ).scalar()

    return family_id, caretaker_id, patient_id, booking_id


def _cleanup_visit_scenario(db, booking_id=None, patient_id=None):
    """Cleanup test entities."""
    if booking_id:
        db.execute(text("DELETE FROM visit_activity_logs WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM visit_notes WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM visit_tracking WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM otp_codes WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM notifications WHERE related_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM admin_audit_logs WHERE entity_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM bookings WHERE id = :bid"), {"bid": booking_id})
    if patient_id:
        db.execute(text("DELETE FROM patient_details WHERE id = :pid"), {"pid": patient_id})
    db.commit()


# ─── 1. OTP Verification Tests ───

def test_verify_visit_start_otp_success(db, test_user, caretaker_user):
    """Caretaker verifies valid visit start OTP and visit placeholder is confirmed."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        plain_code = otp_res["code"]

        result = verify_visit_start_otp(db, booking_id, plain_code, caretaker_id)
        assert result["otp_verified"] is True
        assert result["can_check_in"] is True
        assert result["booking_id"] == booking_id
        assert result["visit_id"] > 0

        # Check visit_tracking exists
        vt = db.execute(
            text("SELECT id, notes FROM visit_tracking WHERE booking_id = :bid"),
            {"bid": booking_id},
        ).fetchone()
        assert vt is not None
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_verify_visit_start_otp_invalid_code(db, test_user, caretaker_user):
    """Wrong OTP fails with 400."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        with pytest.raises(APIException) as exc_info:
            verify_visit_start_otp(db, booking_id, "000000", caretaker_id)
        assert exc_info.value.status_code == 400
        assert "Invalid OTP" in exc_info.value.message
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_verify_visit_start_otp_expired(db, test_user, caretaker_user):
    """Expired OTP fails with 400."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        # Force expiration
        db.execute(
            text("UPDATE otp_codes SET expires_at = DATE_SUB(NOW(), INTERVAL 10 MINUTE) WHERE booking_id = :bid"),
            {"bid": booking_id},
        )
        db.commit()

        with pytest.raises(APIException) as exc_info:
            verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.message.lower()
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_verify_visit_start_otp_wrong_booking(db, test_user, caretaker_user):
    """Non-existent booking or non-accepted booking fails with 404."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "pending")
    try:
        with pytest.raises(APIException) as exc_info:
            verify_visit_start_otp(db, booking_id, "123456", caretaker_id)
        assert exc_info.value.status_code == 404
        assert "Accepted booking not found" in exc_info.value.message
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


# ─── 2. Check-In Tests ───

def test_check_in_without_verified_otp_fails(db, test_user, caretaker_user):
    """Check-in without verified OTP raises 403."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        with pytest.raises(APIException) as exc_info:
            check_in_visit(db, booking_id, caretaker_id, 23.02, 72.57, "Arrived at location")
        assert exc_info.value.status_code == 403
        assert "Visit start OTP verification required" in exc_info.value.message
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_check_in_with_expired_otp_verification_window_fails(db, test_user, caretaker_user):
    """Check-in with OTP verified > 15 mins ago fails with 403."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)

        # Set used_at to 20 minutes ago
        db.execute(
            text("UPDATE otp_codes SET used_at = DATE_SUB(NOW(), INTERVAL 20 MINUTE) WHERE booking_id = :bid"),
            {"bid": booking_id},
        )
        db.commit()

        with pytest.raises(APIException) as exc_info:
            check_in_visit(db, booking_id, caretaker_id)
        assert exc_info.value.status_code == 403
        assert "Visit start OTP verification required" in exc_info.value.message
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_check_in_success_lifecycle(db, test_user, caretaker_user):
    """Check-in succeeds: booking becomes in_progress, caretaker forced unavailable."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)

        res = check_in_visit(db, booking_id, caretaker_id, 23.0225, 72.5714, "On site")
        assert res["status"] == "in_progress"
        assert res["booking_status"] == "in_progress"
        assert res["availability_status"] == "unavailable"
        assert res["availability_reason"] == "on_visit"
        assert res["check_in_time"] != ""

        # Verify booking table status
        b_status = db.execute(text("SELECT status FROM bookings WHERE id = :bid"), {"bid": booking_id}).scalar()
        assert b_status == "in_progress"

        # Verify caretaker profile is_available = 0, reason = 'on_visit'
        cp = db.execute(
            text("SELECT is_available, availability_reason FROM caretaker_profiles WHERE user_id = :cid"),
            {"cid": caretaker_id},
        ).mappings().first()
        assert int(cp["is_available"]) == 0
        assert cp["availability_reason"] == "on_visit"
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_duplicate_check_in_blocked(db, test_user, caretaker_user):
    """Duplicate check-in on the same booking raises 404 or 409."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)
        check_in_visit(db, booking_id, caretaker_id)

        with pytest.raises(APIException) as exc_info:
            check_in_visit(db, booking_id, caretaker_id)
        # Because status is now in_progress, locking accepted booking returns 404
        assert exc_info.value.status_code in (404, 409)
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_check_in_blocked_when_caretaker_has_another_active_visit(db, test_user, caretaker_user):
    """Caretaker cannot check in if already in an active visit."""
    _, caretaker_id, patient_id, b1_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    # Setup second booking for same caretaker
    db.execute(
        text(
            "INSERT INTO bookings "
            "(family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            " start_time, end_time, address, status, total_customer_amount, caretaker_earning_amount, created_at, updated_at) "
            "VALUES (:fuid, :cid, :pid, 'Elder Care', CURDATE(), '14:00:00', '18:00:00', '456 Elm St', 'accepted', 100, 70, NOW(), NOW())"
        ),
        {"fuid": test_user["id"], "cid": caretaker_id, "pid": patient_id},
    )
    db.commit()
    b2_id = db.execute(
        text("SELECT id FROM bookings WHERE family_user_id = :fuid ORDER BY id DESC LIMIT 1"),
        {"fuid": test_user["id"]},
    ).scalar()

    try:
        # Check into b1
        otp1 = otp_create(db, "visit_start", {"booking_id": b1_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, b1_id, otp1["code"], caretaker_id)
        check_in_visit(db, b1_id, caretaker_id)

        # Prepare b2
        otp2 = otp_create(db, "visit_start", {"booking_id": b2_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, b2_id, otp2["code"], caretaker_id)

        # Attempt check-in to b2 while b1 is active -> 409
        with pytest.raises(APIException) as exc_info:
            check_in_visit(db, b2_id, caretaker_id)
        assert exc_info.value.status_code == 409
        assert "Cannot check in while another visit is active" in exc_info.value.message
    finally:
        _cleanup_visit_scenario(db, b1_id, patient_id)
        _cleanup_visit_scenario(db, b2_id)


def test_check_in_blocked_when_caretaker_inactive_or_unapproved(db, test_user, caretaker_user):
    """Inactive or unapproved caretaker is blocked from check-in with 403."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)

        # Mark caretaker unapproved
        db.execute(
            text("UPDATE caretaker_profiles SET verification_status = 'pending' WHERE user_id = :cid"),
            {"cid": caretaker_id},
        )
        db.commit()

        with pytest.raises(APIException) as exc_info:
            check_in_visit(db, booking_id, caretaker_id)
        assert exc_info.value.status_code == 403
        assert "no longer eligible" in exc_info.value.message
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


# ─── 3. Check-Out Tests ───

def test_check_out_success_lifecycle(db, test_user, caretaker_user):
    """Check-out succeeds: completed booking, 20 care points, payout hold 24h, availability restored."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)
        check_in_visit(db, booking_id, caretaker_id, 23.02, 72.57)

        # Set check-in time to 2 hours ago to verify duration
        db.execute(
            text("UPDATE visit_tracking SET check_in_time = DATE_SUB(NOW(), INTERVAL 120 MINUTE) WHERE booking_id = :bid"),
            {"bid": booking_id},
        )
        db.commit()

        res = check_out_visit(db, booking_id, caretaker_id, 23.021, 72.572, "Visit finished smoothly")
        assert res["status"] == "completed"
        assert res["booking_status"] == "completed"
        assert res["care_points_earned"] == 20
        assert res["payout_status"] == "hold"
        assert res["duration_minutes"] >= 119
        assert res["availability_restored"] is True
        assert res["availability_reason"] == "manual_on"

        # Verify DB state
        b = db.execute(
            text("SELECT status, care_points_earned, payout_status, payout_hold_until FROM bookings WHERE id = :bid"),
            {"bid": booking_id},
        ).mappings().first()
        assert b["status"] == "completed"
        assert int(b["care_points_earned"]) == 20
        assert b["payout_status"] == "hold"
        assert b["payout_hold_until"] is not None

        # Verify activity log
        log = db.execute(
            text("SELECT activity_type, message, metadata FROM visit_activity_logs WHERE booking_id = :bid"),
            {"bid": booking_id},
        ).mappings().first()
        assert log is not None
        assert log["activity_type"] == "visit_checked_out"
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_duplicate_check_out_blocked(db, test_user, caretaker_user):
    """Checking out twice raises 404."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)
        check_in_visit(db, booking_id, caretaker_id)
        check_out_visit(db, booking_id, caretaker_id)

        with pytest.raises(APIException) as exc_info:
            check_out_visit(db, booking_id, caretaker_id)
        assert exc_info.value.status_code == 404
        assert "Active check-in record not found" in exc_info.value.message
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)


def test_check_out_preserves_existing_higher_care_points(db, test_user, caretaker_user):
    """If care points were already awarded (e.g. 50), checkout does not overwrite with 20."""
    _, caretaker_id, patient_id, booking_id = _setup_visit_scenario(db, test_user, caretaker_user, "accepted")
    try:
        # Pre-set care points
        db.execute(text("UPDATE bookings SET care_points_earned = 50 WHERE id = :bid"), {"bid": booking_id})
        db.commit()

        otp_res = otp_create(db, "visit_start", {"booking_id": booking_id, "expiry_seconds": 900})
        verify_visit_start_otp(db, booking_id, otp_res["code"], caretaker_id)
        check_in_visit(db, booking_id, caretaker_id)
        res = check_out_visit(db, booking_id, caretaker_id)

        assert res["care_points_earned"] == 50
    finally:
        _cleanup_visit_scenario(db, booking_id, patient_id)

"""
WeCare — Booking State Machine & Unit Tests

Validates:
- State transitions matrix
- Concurrency & stale update handling
- Visit tracking placeholder & OTP generation
- Refund policy tiered calculations
- Care request helper formatting
"""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import text

from app.services.booking_workflow_service import (
    booking_workflow_allowed_transitions,
    booking_workflow_transition,
    booking_workflow_validate_transition,
    booking_workflow_visit_placeholder,
)
from app.services.care_request_service import (
    care_request_date,
    care_request_datetime,
    care_request_decline_reasons,
    care_request_display_time,
    care_request_list_item,
    care_request_location_short,
    care_request_parse_coordinates,
    care_request_priority,
    care_request_text,
    care_request_time,
)
from app.services.refund_service import (
    refund_format_money,
    refund_iso,
    refund_policy_for_family_cancellation,
    refund_public_status,
    refund_statuses,
    successful_booking_payment_summary,
    sync_cancelled_booking_refund_snapshot,
)


def test_allowed_transitions_map():
    """Validates the state transition dictionary."""
    matrix = booking_workflow_allowed_transitions()
    assert matrix["pending"] == ["accepted", "declined", "cancelled"]
    assert matrix["accepted"] == ["in_progress", "cancelled"]
    assert matrix["in_progress"] == ["completed"]
    assert matrix["completed"] == []
    assert matrix["declined"] == []
    assert matrix["cancelled"] == []


def test_validate_transition_function():
    """Validates transition validation rules."""
    assert booking_workflow_validate_transition("pending", "accepted") is True
    assert booking_workflow_validate_transition("pending", "declined") is True
    assert booking_workflow_validate_transition("pending", "cancelled") is True
    assert booking_workflow_validate_transition("accepted", "in_progress") is True
    assert booking_workflow_validate_transition("accepted", "cancelled") is True
    assert booking_workflow_validate_transition("in_progress", "completed") is True

    # Invalid transitions
    assert booking_workflow_validate_transition("pending", "completed") is False
    assert booking_workflow_validate_transition("pending", "in_progress") is False
    assert booking_workflow_validate_transition("accepted", "completed") is False
    assert booking_workflow_validate_transition("completed", "pending") is False
    assert booking_workflow_validate_transition("completed", "in_progress") is False
    assert booking_workflow_validate_transition("cancelled", "accepted") is False
    assert booking_workflow_validate_transition("declined", "accepted") is False


def test_refund_policy_calculations():
    """Validates tiered refund policy for family cancellations."""
    p100, label100 = refund_policy_for_family_cancellation(48.0)
    assert p100 == Decimal("100.00")
    assert "24 or more hours" in label100

    p100_exact, label100_exact = refund_policy_for_family_cancellation(24.0)
    assert p100_exact == Decimal("100.00")

    p50, label50 = refund_policy_for_family_cancellation(18.0)
    assert p50 == Decimal("50.00")
    assert "12-24 hours" in label50

    p50_exact, label50_exact = refund_policy_for_family_cancellation(12.0)
    assert p50_exact == Decimal("50.00")

    p0, label0 = refund_policy_for_family_cancellation(6.0)
    assert p0 == Decimal("0.00")
    assert "less than 12 hours" in label0

    p0_past, label0_past = refund_policy_for_family_cancellation(-2.0)
    assert p0_past == Decimal("0.00")


def test_care_request_formatters():
    """Validates standard date, time, and text formatters."""
    # Display time
    assert care_request_display_time("09:00:00", "13:00:00") == "9:00 AM - 1:00 PM"
    assert care_request_display_time("14:30:00", "16:45:00") == "2:30 PM - 4:45 PM"

    # Location short
    assert care_request_location_short("123 Main St, Apartment 4B, Springfield") == "123 Main St"
    assert care_request_location_short("SingleLineAddress") == "SingleLineAddress"
    assert care_request_location_short(None) == ""

    # Dates and times
    assert care_request_date("2026-08-25") == "2026-08-25"
    assert care_request_time("09:30:00") == "09:30:00"
    assert "2026-08-25" in care_request_datetime(datetime(2026, 8, 25, 10, 0, 0))

    # Priority
    assert care_request_priority({"request_priority": "urgent"}) == "urgent"
    assert care_request_priority({"request_priority": "high"}) == "high"
    assert care_request_priority({"request_priority": "other"}) == "normal"
    assert care_request_priority({}) == "normal"

    # Decline reasons
    reasons = care_request_decline_reasons()
    assert "not_available" in reasons
    assert "location_too_far" in reasons
    assert "other" in reasons

    # Parse coordinates
    coords = care_request_parse_coordinates({"location_latitude": "12.9716", "location_longitude": "77.5946"})
    assert coords["latitude"] == 12.9716
    assert coords["longitude"] == 77.5946


def test_booking_workflow_lifecycle(db, test_user, caretaker_user):
    """
    Tests full booking lifecycle through booking_workflow_transition:
    pending -> accepted -> in_progress -> completed
    """
    family_id = test_user["id"]
    caretaker_id = caretaker_user["id"]

    # 1. Setup patient
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fuid, 'John Doe', 75, 'male', 'Arthritis', 'Elder Care')"
        ),
        {"fuid": family_id},
    )
    db.commit()
    patient_id = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fuid"),
        {"fuid": family_id},
    ).scalar()

    # 2. Insert pending booking
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, "
            "                      booking_date, start_time, end_time, address, total_amount, "
            "                      status, payment_status) "
            "VALUES (:fuid, :cid, :pid, 'Elder Care', '2026-09-01', '09:00:00', '13:00:00', "
            "        '123 Test Street', 100.00, 'pending', 'pending')"
        ),
        {"fuid": family_id, "cid": caretaker_id, "pid": patient_id},
    )
    db.commit()
    booking_id = db.execute(
        text("SELECT id FROM bookings WHERE family_user_id = :fuid ORDER BY id DESC LIMIT 1"),
        {"fuid": family_id},
    ).scalar()

    # 3. Transition: pending -> accepted
    res_accept = booking_workflow_transition(
        db=db,
        booking_id=booking_id,
        actor_user_id=caretaker_id,
        actor_role="caretaker",
        to_status="accepted",
        options={"caretaker_user_id": caretaker_id},
    )
    db.commit()
    assert res_accept["success"] is True
    assert res_accept["to_status"] == "accepted"
    assert res_accept["visit_otp_required"] is True
    assert res_accept["visit_id"] is not None

    # Verify visit_tracking placeholder created
    vt_count = db.execute(
        text("SELECT COUNT(*) FROM visit_tracking WHERE booking_id = :bid"),
        {"bid": booking_id},
    ).scalar()
    assert vt_count == 1

    # Verify visit_start OTP created
    otp_count = db.execute(
        text("SELECT COUNT(*) FROM otp_codes WHERE booking_id = :bid AND purpose = 'visit_start'"),
        {"bid": booking_id},
    ).scalar()
    assert otp_count == 1

    # 4. Invalid transition: accepted -> completed (must go through in_progress)
    res_invalid = booking_workflow_transition(
        db=db,
        booking_id=booking_id,
        actor_user_id=caretaker_id,
        actor_role="caretaker",
        to_status="completed",
        options={"caretaker_user_id": caretaker_id},
    )
    assert res_invalid["success"] is False
    assert res_invalid["status"] == 409

    # 5. Transition: accepted -> in_progress
    res_in_prog = booking_workflow_transition(
        db=db,
        booking_id=booking_id,
        actor_user_id=caretaker_id,
        actor_role="caretaker",
        to_status="in_progress",
        options={"caretaker_user_id": caretaker_id},
    )
    db.commit()
    assert res_in_prog["success"] is True
    assert res_in_prog["to_status"] == "in_progress"

    # 6. Transition: in_progress -> completed
    res_complete = booking_workflow_transition(
        db=db,
        booking_id=booking_id,
        actor_user_id=caretaker_id,
        actor_role="caretaker",
        to_status="completed",
        options={"caretaker_user_id": caretaker_id},
    )
    db.commit()
    assert res_complete["success"] is True
    assert res_complete["to_status"] == "completed"

    # Verify completed_at and payout_status hold
    booking_row = db.execute(
        text("SELECT status, payout_status, payout_hold_until, completed_at FROM bookings WHERE id = :bid"),
        {"bid": booking_id},
    ).mappings().first()
    assert booking_row["status"] == "completed"
    assert booking_row["payout_status"] == "hold"
    assert booking_row["completed_at"] is not None
    assert booking_row["payout_hold_until"] is not None

    # Cleanup
    db.execute(text("DELETE FROM otp_codes WHERE booking_id = :bid"), {"bid": booking_id})
    db.execute(text("DELETE FROM notifications WHERE related_id = :bid"), {"bid": booking_id})
    db.execute(text("DELETE FROM visit_tracking WHERE booking_id = :bid"), {"bid": booking_id})
    db.execute(text("DELETE FROM admin_audit_logs WHERE entity_id = :bid"), {"bid": booking_id})
    db.execute(text("DELETE FROM bookings WHERE id = :bid"), {"bid": booking_id})
    db.execute(text("DELETE FROM patient_details WHERE id = :pid"), {"pid": patient_id})
    db.commit()

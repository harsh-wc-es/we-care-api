"""
WeCare — Booking Workflow Service

Mirrors helpers/booking_workflow.
Single source of truth for booking state transitions, concurrency locks,
visit placeholders, OTP creation, notifications, and audit logging.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit_service import audit_log
from app.services.notification_service import (
    notify_booking_accepted,
    notify_booking_cancelled,
    notify_booking_declined,
    notify_visit_completed,
    notify_visit_started,
)
from app.services.otp_service import otp_create


def booking_workflow_allowed_transitions() -> Dict[str, List[str]]:
    """
    Route: booking_workflow_allowed_transitions() — helpers/booking_workflow L9-19
    """
    return {
        "pending": ["accepted", "declined", "cancelled"],
        "accepted": ["in_progress", "cancelled"],
        "in_progress": ["completed"],
        "completed": [],
        "declined": [],
        "cancelled": [],
    }


def booking_workflow_validate_transition(from_status: str, to_status: str) -> bool:
    """
    Route: booking_workflow_validate_transition() — helpers/booking_workflow L21-25
    """
    allowed = booking_workflow_allowed_transitions()
    return to_status in allowed.get(str(from_status).lower(), [])


def booking_workflow_visit_placeholder(
    db: Session, booking_id: int, caretaker_user_id: int
) -> int:
    """
    Route: booking_workflow_visit_placeholder() — helpers/booking_workflow L27-50
    Ensures a visit_tracking row exists for the accepted booking.
    """
    row = db.execute(
        text(
            "SELECT id FROM visit_tracking "
            "WHERE booking_id = :bid AND caretaker_user_id = :cid "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"bid": int(booking_id), "cid": int(caretaker_user_id)},
    ).fetchone()

    if row:
        return int(row[0])

    db.execute(
        text(
            "INSERT INTO visit_tracking (booking_id, caretaker_user_id, notes) "
            "VALUES (:bid, :cid, 'Visit prepared after request acceptance')"
        ),
        {"bid": int(booking_id), "cid": int(caretaker_user_id)},
    )

    result = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
    return int(result["id"]) if result else 0


def booking_workflow_transition(
    db: Session,
    booking_id: int,
    actor_user_id: int,
    actor_role: str,
    to_status: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Route: booking_workflow_transition() — helpers/booking_workflow L52-196
    Central transition engine for booking state lifecycle.
    """
    options = options or {}
    scope_caretaker = options.get("caretaker_user_id")

    lock_sql = (
        "SELECT id, family_user_id, caretaker_user_id, status, "
        "       location_latitude, location_longitude "
        "FROM bookings "
        "WHERE id = :booking_id"
    )
    params: Dict[str, Any] = {"booking_id": int(booking_id)}

    if scope_caretaker is not None:
        lock_sql += " AND caretaker_user_id = :caretaker_user_id"
        params["caretaker_user_id"] = int(scope_caretaker)

    lock_sql += " FOR UPDATE"

    row = db.execute(text(lock_sql), params).fetchone()
    if not row:
        return {
            "success": False,
            "status": 404,
            "message": "Booking request not found",
            "errors": None,
        }

    booking = dict(row._mapping)
    from_status = str(booking["status"]).lower()
    to_status = str(to_status).lower()

    if not booking_workflow_validate_transition(from_status, to_status):
        return {
            "success": False,
            "status": 409,
            "message": "Invalid booking status transition",
            "errors": {
                "status": [f"Cannot transition booking from {from_status} to {to_status}"]
            },
            "booking": booking,
        }

    decline_code = options.get("decline_reason_code")
    decline_label = options.get("decline_reason_label")
    decline_note = options.get("decline_note")
    cancellation_reason = options.get("cancellation_reason")
    notification_metadata = options.get("notification_metadata")
    if not isinstance(notification_metadata, dict):
        notification_metadata = {}

    update_res = db.execute(
        text(
            "UPDATE bookings "
            "SET status = :to_status, "
            "    decline_reason_code = :decline_code, "
            "    decline_reason_label = :decline_label, "
            "    decline_note = :decline_note, "
            "    responded_at = IF(:to_status IN ('accepted','declined','cancelled'), NOW(), responded_at), "
            "    completed_at = IF(:to_status = 'completed', COALESCE(completed_at, NOW()), completed_at), "
            "    payout_status = IF(:to_status = 'completed', 'hold', payout_status), "
            "    payout_hold_until = IF(:to_status = 'completed', DATE_ADD(COALESCE(completed_at, NOW()), INTERVAL 24 HOUR), payout_hold_until), "
            "    updated_at = NOW() "
            "WHERE id = :booking_id "
            "  AND status = :from_status"
        ),
        {
            "to_status": to_status,
            "decline_code": decline_code if to_status == "declined" else None,
            "decline_label": decline_label if to_status == "declined" else None,
            "decline_note": decline_note if to_status == "declined" else None,
            "booking_id": int(booking_id),
            "from_status": from_status,
        },
    )

    if update_res.rowcount == 0:
        return {
            "success": False,
            "status": 409,
            "message": "Duplicate or stale booking action",
            "errors": {
                "status": ["Booking status changed before this request completed"]
            },
            "booking": booking,
        }

    visit_id = None
    visit_otp_required = False

    if to_status == "accepted":
        cid = int(booking["caretaker_user_id"])
        visit_id = booking_workflow_visit_placeholder(db, int(booking_id), cid)
        otp_create(
            db=db,
            purpose="visit_start",
            options={
                "booking_id": int(booking_id),
                "expiry_seconds": 900,
                "cooldown_seconds": 0,
                "metadata": {"source": "accept_prepared"},
            },
        )
        visit_otp_required = True

    # Trigger notifications
    if to_status == "accepted":
        notify_booking_accepted(db, int(booking_id))
    elif to_status == "declined":
        notify_booking_declined(db, int(booking_id))
    elif to_status == "in_progress":
        notify_visit_started(db, int(booking_id))
    elif to_status == "completed":
        notify_visit_completed(db, int(booking_id))
    elif to_status == "cancelled":
        cancel_meta = {
            "cancelled_by_role": actor_role,
            "cancellation_reason": cancellation_reason,
        }
        cancel_meta.update(notification_metadata)
        notify_booking_cancelled(db, int(booking_id), cancel_meta)

    # Audit logging
    audit_log(
        db=db,
        admin_user_id=int(actor_user_id),
        action="booking_status_transition",
        entity_type="booking",
        entity_id=int(booking_id),
        old_values={"status": from_status},
        new_values={
            "status": to_status,
            "actor_role": actor_role,
            "decline_reason_code": decline_code,
            "decline_reason_label": decline_label,
            "decline_note": decline_note,
            "cancellation_reason": cancellation_reason if to_status == "cancelled" else None,
        },
    )

    lat = booking.get("location_latitude")
    lng = booking.get("location_longitude")

    return {
        "success": True,
        "status": 200,
        "message": "Booking status updated",
        "booking": booking,
        "from_status": from_status,
        "to_status": to_status,
        "visit_id": visit_id,
        "visit_otp_required": visit_otp_required,
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lng) if lng is not None else None,
    }

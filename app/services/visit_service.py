"""
WeCare — Visit Execution Service (Part 6: Complete Visit Domain)

Mirrors all Visit endpoints and helpers:
- api/v1/visit/verify_start_otp
- api/v1/visit/check_in
- api/v1/visit/check_out
- api/v1/visit/view_visit
- api/v1/visit/active_visit
- api/v1/visit/add_note
- api/v1/visit/update_task_status
- api/v1/visit/completed_summary
- api/v1/visit/full_report
- helpers/visit_live
- helpers/visit_history
"""

from datetime import datetime
import json
import logging
import math
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.availability_service import (
    caretaker_has_active_visit,
    force_caretaker_unavailable_for_visit,
    restore_caretaker_availability_after_visit,
)
from app.services.booking_workflow_service import booking_workflow_transition
from app.services.care_request_service import (
    care_request_date,
    care_request_datetime,
    care_request_display_time,
    care_request_location_short,
    care_request_parse_coordinates,
    care_request_text,
    care_request_time,
)
from app.services.otp_service import otp_verify
from app.services.rate_limit_service import clear_rate_limit, enforce_rate_limit

logger = logging.getLogger(__name__)


def _validate_booking_id(booking_id: Any) -> int:
    """Validates that booking_id is an integer > 0; raises 400 on error."""
    if booking_id is None or str(booking_id).strip() == "":
        raise APIException(
            "Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )
    try:
        bid = int(booking_id)
        if bid <= 0:
            raise ValueError()
        return bid
    except (ValueError, TypeError):
        raise APIException(
            "Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )


def _format_duration_label(minutes: int) -> str:
    """
    Route: visit_history_duration_label() — helpers/visit_history L5-20
    Formats minutes to 'Xh Ym', 'Xh', or 'Ym'.
    """
    minutes = max(0, int(minutes))
    hours = minutes // 60
    rem = minutes % 60
    if hours > 0 and rem > 0:
        return f"{hours}h {rem}m"
    if hours > 0:
        return f"{hours}h"
    return f"{rem}m"


def _calculate_duration_minutes(check_in_time: Any, check_out_time: Any) -> int:
    """Calculates duration in integer minutes between check_in and check_out timestamps."""
    if not check_in_time or not check_out_time:
        return 0
    try:
        in_dt = (
            check_in_time
            if isinstance(check_in_time, datetime)
            else datetime.fromisoformat(str(check_in_time).replace("Z", "+00:00"))
        )
        out_dt = (
            check_out_time
            if isinstance(check_out_time, datetime)
            else datetime.fromisoformat(str(check_out_time).replace("Z", "+00:00"))
        )
        return max(0, int(math.floor((out_dt.timestamp() - in_dt.timestamp()) / 60)))
    except Exception as e:
        logger.warning(f"Failed to calculate duration minutes: {e}")
        return 0


def visit_live_log(
    db: Session,
    booking_id: int,
    visit_id: Optional[int],
    actor_user_id: Optional[int],
    actor_role: str,
    activity_type: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Route: visit_live_log() — helpers/visit_live L5-21
    Inserts a record into visit_activity_logs.
    """
    meta_json = json.dumps(metadata) if metadata else None
    db.execute(
        text(
            "INSERT INTO visit_activity_logs "
            "(booking_id, visit_id, actor_user_id, actor_role, activity_type, message, metadata) "
            "VALUES (:booking_id, :visit_id, :actor_user_id, :actor_role, :activity_type, :message, :metadata)"
        ),
        {
            "booking_id": int(booking_id),
            "visit_id": int(visit_id) if visit_id is not None else None,
            "actor_user_id": int(actor_user_id) if actor_user_id is not None else None,
            "actor_role": str(actor_role),
            "activity_type": str(activity_type),
            "message": str(message),
            "metadata": meta_json,
        },
    )


def normalize_task_status(status: Any) -> str:
    """
    Route: visit_live_task_status() — helpers/visit_live L23-31
    Normalizes 'done' to 'completed'.
    """
    s = str(status or "").strip().lower()
    if s == "done":
        return "completed"
    return s if s in ("pending", "ongoing", "completed") else ""


# ─────────────────────────────────────────────────────────────
# 1. verify_start_otp
# ─────────────────────────────────────────────────────────────

def verify_visit_start_otp(
    db: Session,
    booking_id: Any,
    otp: Any,
    caretaker_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/verify_start_otp L1-82
    Verifies the family-provided visit start OTP submitted by the caretaker.
    """
    rate_key = f"{int(caretaker_user_id)}:{booking_id}"
    enforce_rate_limit(
        db,
        "visit_start_otp",
        rate_key,
        max_attempts=5,
        window_seconds=900,
        block_seconds=900,
    )

    bid = _validate_booking_id(booking_id)

    otp_str = str(otp or "").strip()
    if not otp_str:
        raise APIException(
            "Validation failed",
            errors={"otp": ["OTP is required"]},
            status_code=400,
        )

    # Validate booking exists for caretaker in accepted status
    booking_row = db.execute(
        text(
            "SELECT id, caretaker_user_id "
            "FROM bookings "
            "WHERE id = :bid AND caretaker_user_id = :cid AND status = 'accepted' "
            "LIMIT 1"
        ),
        {"bid": bid, "cid": int(caretaker_user_id)},
    ).fetchone()

    if not booking_row:
        raise APIException("Accepted booking not found", status_code=404)

    # Verify OTP against otp_codes table
    result = otp_verify(
        db=db,
        purpose="visit_start",
        code=otp_str,
        options={"booking_id": bid},
    )

    if not result.get("success"):
        msg = result.get("message", "Invalid OTP")
        raise APIException(msg, errors={"otp": [msg]}, status_code=400)

    # Clear rate limit on success
    clear_rate_limit(db, "visit_start_otp", rate_key)

    # Ensure a visit_tracking placeholder exists
    v_row = db.execute(
        text(
            "SELECT id FROM visit_tracking "
            "WHERE booking_id = :bid AND caretaker_user_id = :cid "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"bid": bid, "cid": int(caretaker_user_id)},
    ).fetchone()

    if v_row:
        visit_id = int(v_row[0])
    else:
        db.execute(
            text(
                "INSERT INTO visit_tracking (booking_id, caretaker_user_id, notes) "
                "VALUES (:bid, :cid, 'Visit prepared after OTP verification')"
            ),
            {"bid": bid, "cid": int(caretaker_user_id)},
        )
        res = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
        visit_id = int(res["id"]) if res else 0
        db.commit()

    return {
        "booking_id": bid,
        "visit_id": visit_id,
        "otp_verified": True,
        "can_check_in": True,
    }


# ─────────────────────────────────────────────────────────────
# 2. check_in
# ─────────────────────────────────────────────────────────────

def check_in_visit(
    db: Session,
    booking_id: Any,
    caretaker_user_id: int,
    latitude: Optional[Union[float, str]] = None,
    longitude: Optional[Union[float, str]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/check_in L1-170
    Performs caretaker check-in with row-level locking, OTP verification check,
    eligibility validation, availability disabling, and booking state transition.
    """
    bid = _validate_booking_id(booking_id)
    cid = int(caretaker_user_id)

    # 1. Lock the booking row
    booking_row = db.execute(
        text(
            "SELECT id, caretaker_user_id, status "
            "FROM bookings "
            "WHERE id = :bid AND caretaker_user_id = :cid AND status = 'accepted' "
            "FOR UPDATE"
        ),
        {"bid": bid, "cid": cid},
    ).fetchone()

    if not booking_row:
        raise APIException("Accepted booking not found", status_code=404)

    # 2. Verify OTP was verified within last 15 minutes
    otp_row = db.execute(
        text(
            "SELECT id FROM otp_codes "
            "WHERE booking_id = :bid "
            "  AND purpose = 'visit_start' "
            "  AND used_at IS NOT NULL "
            "  AND used_at >= DATE_SUB(NOW(), INTERVAL 15 MINUTE) "
            "  AND id = ( "
            "      SELECT MAX(id) "
            "      FROM otp_codes "
            "      WHERE booking_id = :bid "
            "        AND purpose = 'visit_start' "
            "  ) "
            "LIMIT 1"
        ),
        {"bid": bid},
    ).fetchone()

    if not otp_row:
        raise APIException(
            "Visit start OTP verification required",
            errors={
                "otp": [
                    "Caretaker must verify the family-provided visit start OTP before check-in"
                ]
            },
            status_code=403,
        )

    # 3. Verify caretaker has no other active visit
    if caretaker_has_active_visit(db, cid):
        raise APIException(
            "Cannot check in while another visit is active",
            errors={"visit": ["Complete your current visit before starting a new one"]},
            status_code=409,
        )

    # 4. Verify caretaker eligibility (active + approved)
    profile_row = db.execute(
        text(
            "SELECT u.is_active, cp.verification_status "
            "FROM users u "
            "INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "WHERE u.id = :cid AND u.role = 'caretaker'"
        ),
        {"cid": cid},
    ).fetchone()

    if (
        not profile_row
        or int(profile_row._mapping.get("is_active") or 0) != 1
        or profile_row._mapping.get("verification_status") != "approved"
    ):
        raise APIException("Caretaker is no longer eligible for visits", status_code=403)

    # 5. Prevent duplicate active check-in for this booking
    active_visit_row = db.execute(
        text(
            "SELECT id FROM visit_tracking "
            "WHERE booking_id = :bid AND caretaker_user_id = :cid "
            "  AND check_in_time IS NOT NULL AND check_out_time IS NULL "
            "LIMIT 1"
        ),
        {"bid": bid, "cid": cid},
    ).fetchone()

    if active_visit_row:
        raise APIException(
            "Visit already checked in",
            errors={"booking_id": ["This booking already has an active check-in"]},
            status_code=409,
        )

    # 6. Update or insert visit_tracking record
    existing_vt = db.execute(
        text(
            "SELECT id FROM visit_tracking "
            "WHERE booking_id = :bid AND caretaker_user_id = :cid "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"bid": bid, "cid": cid},
    ).fetchone()

    lat_val = str(latitude) if latitude is not None else None
    lng_val = str(longitude) if longitude is not None else None
    notes_val = str(notes) if notes is not None else None

    if existing_vt:
        visit_id = int(existing_vt[0])
        db.execute(
            text(
                "UPDATE visit_tracking "
                "SET check_in_time = NOW(), check_in_lat = :lat, check_in_lng = :lng, notes = :notes "
                "WHERE id = :vid"
            ),
            {"lat": lat_val, "lng": lng_val, "notes": notes_val, "vid": visit_id},
        )
    else:
        db.execute(
            text(
                "INSERT INTO visit_tracking "
                "(booking_id, caretaker_user_id, check_in_time, check_in_lat, check_in_lng, notes) "
                "VALUES (:bid, :cid, NOW(), :lat, :lng, :notes)"
            ),
            {"bid": bid, "cid": cid, "lat": lat_val, "lng": lng_val, "notes": notes_val},
        )
        res = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
        visit_id = int(res["id"]) if res else 0

    # Retrieve check_in_time
    check_in_row = db.execute(
        text("SELECT check_in_time FROM visit_tracking WHERE id = :vid LIMIT 1"),
        {"vid": visit_id},
    ).fetchone()
    check_in_time = check_in_row[0] if check_in_row else None

    # 7. Transition booking status to in_progress
    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=cid,
        actor_role="caretaker",
        to_status="in_progress",
        options={"caretaker_user_id": cid},
    )

    if not transition.get("success"):
        raise APIException(
            message=transition.get("message", "Check-in failed"),
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    # 8. Force caretaker unavailable during visit
    force_caretaker_unavailable_for_visit(db, cid, bid)

    db.commit()

    return {
        "booking_id": bid,
        "visit_id": visit_id,
        "status": "in_progress",
        "check_in_time": care_request_datetime(check_in_time),
        "booking_status": "in_progress",
        "availability_status": "unavailable",
        "availability_reason": "on_visit",
    }


# ─────────────────────────────────────────────────────────────
# 3. check_out
# ─────────────────────────────────────────────────────────────

def check_out_visit(
    db: Session,
    booking_id: Any,
    caretaker_user_id: int,
    latitude: Optional[Union[float, str]] = None,
    longitude: Optional[Union[float, str]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/check_out L1-131
    Performs caretaker check-out with active check-in row locking, duration calculation,
    care points award, availability restoration, and booking transition to completed.
    """
    bid = _validate_booking_id(booking_id)
    cid = int(caretaker_user_id)

    # 1. Lock active visit joined with booking in in_progress status
    visit_row = db.execute(
        text(
            "SELECT vt.id, vt.booking_id, vt.caretaker_user_id, vt.check_in_time, "
            "       vt.check_out_time, vt.check_in_lat, vt.check_in_lng, vt.check_out_lat, "
            "       vt.check_out_lng, vt.notes, vt.created_at, b.status AS booking_status "
            "FROM visit_tracking vt "
            "INNER JOIN bookings b ON b.id = vt.booking_id "
            "WHERE vt.booking_id = :bid "
            "  AND vt.caretaker_user_id = :cid "
            "  AND vt.check_in_time IS NOT NULL "
            "  AND vt.check_out_time IS NULL "
            "  AND b.status = 'in_progress' "
            "ORDER BY vt.id DESC "
            "LIMIT 1 "
            "FOR UPDATE"
        ),
        {"bid": bid, "cid": cid},
    ).fetchone()

    if not visit_row:
        raise APIException("Active check-in record not found", status_code=404)

    visit = dict(visit_row._mapping)
    visit_id = int(visit["id"])
    check_in_time = visit["check_in_time"]

    lat_val = str(latitude) if latitude is not None else None
    lng_val = str(longitude) if longitude is not None else None
    notes_val = str(notes) if notes is not None else None

    # 2. Update visit_tracking with check_out_time = NOW()
    db.execute(
        text(
            "UPDATE visit_tracking "
            "SET check_out_time = NOW(), check_out_lat = :lat, check_out_lng = :lng, notes = :notes "
            "WHERE id = :vid"
        ),
        {"lat": lat_val, "lng": lng_val, "notes": notes_val, "vid": visit_id},
    )

    # 3. Transition booking status to completed
    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=cid,
        actor_role="caretaker",
        to_status="completed",
        options={"caretaker_user_id": cid},
    )

    if not transition.get("success"):
        raise APIException(
            message=transition.get("message", "Check-out failed"),
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    # 4. Award care points (default 20 if 0)
    db.execute(
        text(
            "UPDATE bookings "
            "SET care_points_earned = CASE WHEN care_points_earned = 0 THEN 20 ELSE care_points_earned END "
            "WHERE id = :bid"
        ),
        {"bid": bid},
    )

    # 5. Restore caretaker availability after visit
    restore_res = restore_caretaker_availability_after_visit(db, cid, bid)
    restored = bool(restore_res.get("restored", False))

    # 6. Retrieve updated check_out_time and care_points_earned
    out_row = db.execute(
        text("SELECT check_out_time FROM visit_tracking WHERE id = :vid LIMIT 1"),
        {"vid": visit_id},
    ).fetchone()
    check_out_time = out_row[0] if out_row else None

    pts_row = db.execute(
        text("SELECT care_points_earned FROM bookings WHERE id = :bid LIMIT 1"),
        {"bid": bid},
    ).fetchone()
    care_points_earned = int(pts_row[0]) if pts_row and pts_row[0] is not None else 20

    # 7. Duration calculation in integer minutes
    duration_minutes = _calculate_duration_minutes(check_in_time, check_out_time)

    # 8. Log activity
    visit_live_log(
        db=db,
        booking_id=bid,
        visit_id=visit_id,
        actor_user_id=cid,
        actor_role="caretaker",
        activity_type="visit_checked_out",
        message="Visit checked out",
        metadata={"duration_minutes": duration_minutes},
    )

    db.commit()

    response_data: Dict[str, Any] = {
        "booking_id": bid,
        "visit_id": visit_id,
        "status": "completed",
        "check_out_time": care_request_datetime(check_out_time),
        "duration_minutes": duration_minutes,
        "care_points_earned": care_points_earned,
        "booking_status": "completed",
        "payout_status": "hold",
        "availability_restored": restored,
    }

    if restored:
        response_data["availability_reason"] = "manual_on"
    else:
        response_data["availability_reason"] = "Visit ended; availability not auto-restored"

    return response_data


# ─────────────────────────────────────────────────────────────
# 4. view_visit
# ─────────────────────────────────────────────────────────────

def get_visit_detail(
    db: Session,
    booking_id: Any,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/view_visit L1-124
    Retrieves complete visit details scoped by role (family, caretaker, admin).
    """
    bid = _validate_booking_id(booking_id)
    role = str(current_user.get("role") or "").lower()
    uid = int(current_user["id"])

    scope_sql = ""
    params: Dict[str, Any] = {"bid": bid}
    if role == "family":
        scope_sql = " AND b.family_user_id = :uid"
        params["uid"] = uid
    elif role == "caretaker":
        scope_sql = " AND b.caretaker_user_id = :uid"
        params["uid"] = uid

    query = (
        "SELECT b.id AS booking_id, b.status, b.service_type, b.booking_date, b.start_time, b.end_time, "
        "       b.address, b.notes, b.location_latitude, b.location_longitude, "
        "       p.patient_name, p.age, p.medical_condition, p.special_instructions, p.care_type, "
        "       family.phone_number AS family_phone, "
        "       vt.id AS visit_id, vt.check_in_time, vt.check_out_time, vt.check_in_lat, vt.check_in_lng, "
        "       latest_otp.used_at AS otp_verified_at "
        "FROM bookings b "
        "LEFT JOIN patient_details p ON p.id = b.patient_id "
        "LEFT JOIN users family ON family.id = b.family_user_id "
        "LEFT JOIN visit_tracking vt "
        "  ON vt.booking_id = b.id "
        " AND vt.caretaker_user_id = b.caretaker_user_id "
        "LEFT JOIN ( "
        "    SELECT oc.booking_id, oc.used_at "
        "    FROM otp_codes oc "
        "    INNER JOIN ( "
        "        SELECT booking_id, MAX(id) AS latest_id "
        "        FROM otp_codes "
        "        WHERE purpose = 'visit_start' "
        "        GROUP BY booking_id "
        "    ) latest ON latest.latest_id = oc.id "
        ") latest_otp ON latest_otp.booking_id = b.id "
        f"WHERE b.id = :bid {scope_sql} "
        "ORDER BY vt.id DESC "
        "LIMIT 1"
    )

    row = db.execute(text(query), params).fetchone()
    if not row:
        raise APIException("Visit not found", status_code=404)

    m = row._mapping

    # Fetch tasks
    tasks_rows = db.execute(
        text(
            "SELECT id, title, description, status, completed_at "
            "FROM booking_checklist_tasks "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": bid},
    ).fetchall()

    tasks = [
        {
            "task_id": int(t._mapping["id"]),
            "title": care_request_text(t._mapping.get("title") or ""),
            "description": care_request_text(t._mapping.get("description") or ""),
            "status": normalize_task_status(t._mapping.get("status") or "pending") or "pending",
            "completed_at": care_request_datetime(t._mapping.get("completed_at")),
        }
        for t in tasks_rows
    ]

    start = care_request_time(m.get("start_time"))
    end = care_request_time(m.get("end_time"))
    coords = care_request_parse_coordinates(dict(m))
    otp_verified = m.get("otp_verified_at") is not None
    status = str(care_request_text(m.get("status") or "")).lower()

    return {
        "booking_id": int(m["booking_id"]),
        "visit_id": int(m["visit_id"]) if m.get("visit_id") is not None else None,
        "status": status,
        "patient_name": care_request_text(m.get("patient_name") or ""),
        "patient_age": int(m["age"]) if m.get("age") is not None else 0,
        "patient_condition": care_request_text(m.get("medical_condition") or ""),
        "contact_phone": care_request_text(m.get("family_phone") or ""),
        "address": care_request_text(m.get("address") or ""),
        "location_short": care_request_location_short(m.get("address") or ""),
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "visit_date": care_request_date(m.get("booking_date")),
        "start_time": start,
        "end_time": end,
        "display_time": care_request_display_time(start, end),
        "service_type": care_request_text(m.get("service_type") or ""),
        "care_type": care_request_text(m.get("care_type") or ""),
        "care_tasks": tasks,
        "instructions": care_request_text(m.get("special_instructions") or (m.get("notes") or "")),
        "can_call": care_request_text(m.get("family_phone") or "") != "",
        "can_navigate": coords["latitude"] is not None and coords["longitude"] is not None,
        "can_start_visit": role == "caretaker" and status == "accepted" and otp_verified,
        "requires_otp": role == "caretaker" and status == "accepted",
        "otp_verified": otp_verified,
        "check_in_time": care_request_datetime(m.get("check_in_time")),
        "check_out_time": care_request_datetime(m.get("check_out_time")),
        "actions": {
            "verify_otp_endpoint": "/api/v1/visit/verify_start_otp",
            "check_in_endpoint": "/api/v1/visit/check_in",
            "check_out_endpoint": "/api/v1/visit/check_out",
            "sos_endpoint": "/api/v1/sos/create_sos",
        },
    }


# ─────────────────────────────────────────────────────────────
# 5. active_visit
# ─────────────────────────────────────────────────────────────

def get_active_visit(
    db: Session,
    booking_id: Any,
    caretaker_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/active_visit L1-38 & helpers/visit_live L33-144
    Returns live in-progress visit payload with tasks and notes for caretaker.
    """
    bid = _validate_booking_id(booking_id)
    cid = int(caretaker_user_id)

    # Check booking existence and ownership
    booking_row = db.execute(
        text("SELECT caretaker_user_id, status FROM bookings WHERE id = :bid LIMIT 1"),
        {"bid": bid},
    ).fetchone()

    if not booking_row:
        raise APIException("Active visit not found", status_code=404)

    if int(booking_row._mapping.get("caretaker_user_id") or 0) != cid:
        raise APIException("You are not allowed to access this visit", status_code=403)

    # Fetch active visit
    query = (
        "SELECT b.id AS booking_id, b.status, b.booking_date, b.start_time, b.end_time, "
        "       b.address, b.location_latitude, b.location_longitude, b.notes, "
        "       p.id AS patient_id, p.patient_name, p.age, p.medical_condition, "
        "       family.phone_number AS family_phone, "
        "       cp.full_name AS caretaker_name, u.profile_picture AS caretaker_photo_url, "
        "       vt.id AS visit_id, vt.check_in_time, vt.check_out_time "
        "FROM bookings b "
        "INNER JOIN visit_tracking vt "
        "  ON vt.booking_id = b.id "
        " AND vt.caretaker_user_id = b.caretaker_user_id "
        " AND vt.check_in_time IS NOT NULL "
        " AND vt.check_out_time IS NULL "
        "LEFT JOIN patient_details p ON p.id = b.patient_id "
        "LEFT JOIN users family ON family.id = b.family_user_id "
        "LEFT JOIN users u ON u.id = b.caretaker_user_id "
        "LEFT JOIN caretaker_profiles cp ON cp.user_id = b.caretaker_user_id "
        "WHERE b.id = :bid "
        "  AND b.caretaker_user_id = :cid "
        "  AND b.status = 'in_progress' "
        "LIMIT 1"
    )

    visit_row = db.execute(text(query), {"bid": bid, "cid": cid}).fetchone()
    if not visit_row:
        raise APIException("Active visit not found", status_code=404)

    visit = dict(visit_row._mapping)
    coords = care_request_parse_coordinates(visit)

    # Fetch tasks
    tasks_rows = db.execute(
        text(
            "SELECT id, title, description, status, completed_at "
            "FROM booking_checklist_tasks "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": bid},
    ).fetchall()

    tasks = [
        {
            "task_id": int(t._mapping["id"]),
            "title": care_request_text(t._mapping.get("title") or ""),
            "description": care_request_text(t._mapping.get("description") or ""),
            "status": normalize_task_status(t._mapping.get("status") or "pending") or "pending",
            "completed_at": care_request_datetime(t._mapping.get("completed_at")),
        }
        for t in tasks_rows
    ]

    # Fetch live notes
    notes_rows = db.execute(
        text(
            "SELECT id, note, created_at "
            "FROM visit_notes "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": bid},
    ).fetchall()

    live_notes = [
        {
            "note_id": int(n._mapping["id"]),
            "note": care_request_text(n._mapping.get("note") or ""),
            "created_at": care_request_datetime(n._mapping.get("created_at")),
        }
        for n in notes_rows
    ]

    start = care_request_time(visit.get("start_time"))
    end = care_request_time(visit.get("end_time"))

    return {
        "booking_id": bid,
        "visit_id": int(visit["visit_id"]),
        "status": "in_progress",
        "started_at": care_request_datetime(visit.get("check_in_time")),
        "patient": {
            "id": int(visit["patient_id"]) if visit.get("patient_id") is not None else 0,
            "name": care_request_text(visit.get("patient_name") or ""),
            "phone": care_request_text(visit.get("family_phone") or ""),
            "age": int(visit["age"]) if visit.get("age") is not None else 0,
        },
        "caretaker": {
            "id": cid,
            "name": care_request_text(visit.get("caretaker_name") or ""),
            "photo_url": care_request_text(visit.get("caretaker_photo_url") or ""),
        },
        "visit": {
            "location_short": care_request_location_short(visit.get("address") or ""),
            "address": care_request_text(visit.get("address") or ""),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "start_time": start,
            "end_time": end,
            "display_time": care_request_display_time(start, end),
        },
        "tasks": tasks,
        "live_notes": live_notes,
        "can_checkout": True,
        "sos_enabled": True,
    }


# ─────────────────────────────────────────────────────────────
# 6. add_note
# ─────────────────────────────────────────────────────────────

def add_visit_note(
    db: Session,
    booking_id: Any,
    note: Any,
    caretaker_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/add_note L1-67
    Adds an immutable care note during an active visit.
    """
    bid = _validate_booking_id(booking_id)
    cid = int(caretaker_user_id)

    note_str = str(note or "").strip()
    if not note_str:
        raise APIException("Validation failed", errors={"note": ["Note is required"]}, status_code=400)
    if len(note_str) > 1000:
        raise APIException(
            "Validation failed",
            errors={"note": ["Note must not exceed 1000 characters"]},
            status_code=400,
        )

    # Active visit requirement
    vt_row = db.execute(
        text(
            "SELECT vt.id AS visit_id "
            "FROM bookings b "
            "INNER JOIN visit_tracking vt "
            "  ON vt.booking_id = b.id "
            " AND vt.caretaker_user_id = b.caretaker_user_id "
            " AND vt.check_in_time IS NOT NULL "
            " AND vt.check_out_time IS NULL "
            "WHERE b.id = :bid AND b.caretaker_user_id = :cid AND b.status = 'in_progress' "
            "LIMIT 1"
        ),
        {"bid": bid, "cid": cid},
    ).fetchone()

    if not vt_row:
        raise APIException("Active visit not found", status_code=404)

    visit_id = int(vt_row._mapping["visit_id"])

    db.execute(
        text(
            "INSERT INTO visit_notes (booking_id, visit_id, caretaker_user_id, note) "
            "VALUES (:bid, :vid, :cid, :note)"
        ),
        {"bid": bid, "vid": visit_id, "cid": cid, "note": note_str},
    )
    res = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
    note_id = int(res["id"]) if res else 0

    visit_live_log(
        db=db,
        booking_id=bid,
        visit_id=visit_id,
        actor_user_id=cid,
        actor_role="caretaker",
        activity_type="note_added",
        message="Live care note added",
        metadata={"note_id": note_id},
    )

    db.commit()

    created_row = db.execute(
        text("SELECT note, created_at FROM visit_notes WHERE id = :nid LIMIT 1"),
        {"nid": note_id},
    ).fetchone()

    created_at = created_row._mapping.get("created_at") if created_row else None

    return {
        "note_id": note_id,
        "note": care_request_text(note_str),
        "created_at": care_request_datetime(created_at),
    }


# ─────────────────────────────────────────────────────────────
# 7. update_task_status
# ─────────────────────────────────────────────────────────────

def update_visit_task_status(
    db: Session,
    booking_id: Any,
    task_id: Any,
    status: Any,
    caretaker_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/update_task_status L1-101
    Updates checklist task status during an active visit with transition constraints.
    """
    errors: Dict[str, List[str]] = {}
    bid = None
    tid = None

    try:
        bid = int(booking_id)
        if bid <= 0:
            raise ValueError()
    except Exception:
        errors["booking_id"] = ["Booking id must be an integer"]

    try:
        tid = int(task_id)
        if tid <= 0:
            raise ValueError()
    except Exception:
        errors["task_id"] = ["Task id must be an integer"]

    norm_status = normalize_task_status(status)
    if not norm_status:
        errors["status"] = ["Allowed values are pending, ongoing, completed"]

    if errors:
        raise APIException("Validation failed", errors=errors, status_code=400)

    cid = int(caretaker_user_id)

    # Lock task record joined with active booking and visit
    task_row = db.execute(
        text(
            "SELECT t.id, t.status, t.booking_id, b.status AS booking_status, vt.id AS visit_id "
            "FROM booking_checklist_tasks t "
            "INNER JOIN bookings b ON b.id = t.booking_id "
            "INNER JOIN visit_tracking vt "
            "  ON vt.booking_id = b.id "
            " AND vt.caretaker_user_id = b.caretaker_user_id "
            " AND vt.check_in_time IS NOT NULL "
            " AND vt.check_out_time IS NULL "
            "WHERE t.id = :tid "
            "  AND t.booking_id = :bid "
            "  AND b.caretaker_user_id = :cid "
            "  AND b.status = 'in_progress' "
            "FOR UPDATE"
        ),
        {"tid": tid, "bid": bid, "cid": cid},
    ).fetchone()

    if not task_row:
        raise APIException("Active visit task not found", status_code=404)

    t_map = task_row._mapping
    old_status = normalize_task_status(t_map.get("status") or "pending") or "pending"

    allowed = {
        "pending": ["ongoing", "completed"],
        "ongoing": ["pending", "completed"],
        "completed": [],
    }

    if old_status != norm_status and norm_status not in allowed.get(old_status, []):
        raise APIException(
            "Invalid task status transition",
            errors={"status": [f"Cannot transition task from {old_status} to {norm_status}"]},
            status_code=409,
        )

    completed_at = datetime.now() if norm_status == "completed" else None
    completed_by = cid if norm_status == "completed" else None

    db.execute(
        text(
            "UPDATE booking_checklist_tasks "
            "SET status = :status, completed_by = :completed_by, completed_at = :completed_at "
            "WHERE id = :tid"
        ),
        {
            "status": norm_status,
            "completed_by": completed_by,
            "completed_at": completed_at,
            "tid": tid,
        },
    )

    visit_live_log(
        db=db,
        booking_id=bid,
        visit_id=int(t_map["visit_id"]),
        actor_user_id=cid,
        actor_role="caretaker",
        activity_type="task_status_updated",
        message="Task status updated",
        metadata={
            "task_id": tid,
            "old_status": old_status,
            "new_status": norm_status,
        },
    )

    db.commit()

    return {
        "task_id": tid,
        "status": norm_status,
        "completed_at": care_request_datetime(completed_at),
    }


# ─────────────────────────────────────────────────────────────
# 8. completed_summary
# ─────────────────────────────────────────────────────────────

def get_completed_summary(
    db: Session,
    booking_id: Any,
    caretaker_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/completed_summary L1-60
    Returns completed visit summary metrics for caretaker popup.
    """
    bid = _validate_booking_id(booking_id)
    cid = int(caretaker_user_id)

    # Booking check
    b_row = db.execute(
        text(
            "SELECT b.id, b.caretaker_user_id, b.status, b.completed_at, b.care_points_earned, "
            "       p.patient_name "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE b.id = :bid "
            "LIMIT 1"
        ),
        {"bid": bid},
    ).fetchone()

    if not b_row:
        raise APIException("Completed visit not found", status_code=404)

    if int(b_row._mapping.get("caretaker_user_id") or 0) != cid:
        raise APIException("You are not allowed to view this visit", status_code=403)

    if str(b_row._mapping.get("status") or "") != "completed":
        raise APIException("Completed visit not found", status_code=404)

    # Visit check
    v_row = db.execute(
        text(
            "SELECT id, check_in_time, check_out_time "
            "FROM visit_tracking "
            "WHERE booking_id = :bid AND caretaker_user_id = :cid "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"bid": bid, "cid": cid},
    ).fetchone()

    if not v_row or not v_row._mapping.get("check_out_time"):
        raise APIException("Completed visit not found", status_code=404)

    duration_minutes = _calculate_duration_minutes(
        v_row._mapping.get("check_in_time"),
        v_row._mapping.get("check_out_time"),
    )

    # Task summary count
    task_row = db.execute(
        text(
            "SELECT COUNT(*) AS total_count, SUM(status = 'completed') AS completed_count "
            "FROM booking_checklist_tasks "
            "WHERE booking_id = :bid"
        ),
        {"bid": bid},
    ).fetchone()

    tasks_total = int(task_row._mapping.get("total_count") or 0) if task_row else 0
    tasks_completed = int(task_row._mapping.get("completed_count") or 0) if task_row else 0

    completed_at = b_row._mapping.get("completed_at") or v_row._mapping.get("check_out_time")
    care_points = int(b_row._mapping.get("care_points_earned") or 0)
    if care_points <= 0:
        care_points = 20

    return {
        "booking_id": bid,
        "visit_id": int(v_row._mapping["id"]),
        "status": "completed",
        "care_points_earned": care_points,
        "patient_name": care_request_text(b_row._mapping.get("patient_name") or ""),
        "duration_label": _format_duration_label(duration_minutes),
        "duration_minutes": duration_minutes,
        "tasks_completed": tasks_completed,
        "tasks_total": tasks_total,
        "completed_at": care_request_datetime(completed_at),
        "can_view_full_report": True,
    }


# ─────────────────────────────────────────────────────────────
# 9. full_report
# ─────────────────────────────────────────────────────────────

def get_full_report(
    db: Session,
    booking_id: Any,
    caretaker_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/visit/full_report L1-92
    Returns comprehensive report for completed visit.
    CRITICAL: Platform commission and customer booking totals are strictly hidden.
    """
    bid = _validate_booking_id(booking_id)
    cid = int(caretaker_user_id)

    query = (
        "SELECT b.id AS booking_id, b.family_user_id, b.caretaker_user_id, b.patient_id, "
        "       b.service_type, b.booking_date, b.start_time, b.end_time, b.address, "
        "       b.location_latitude, b.location_longitude, b.notes, b.status, "
        "       b.completed_at, b.payout_status, b.caretaker_earning_amount, b.care_points_earned, "
        "       p.patient_name, p.age, p.gender, p.medical_condition, "
        "       family.phone_number AS family_phone, "
        "       cu.profile_picture AS caretaker_photo_url, "
        "       cp.full_name AS caretaker_name "
        "FROM bookings b "
        "LEFT JOIN patient_details p ON p.id = b.patient_id "
        "LEFT JOIN users family ON family.id = b.family_user_id "
        "LEFT JOIN users cu ON cu.id = b.caretaker_user_id "
        "LEFT JOIN caretaker_profiles cp ON cp.user_id = b.caretaker_user_id "
        "WHERE b.id = :bid "
        "LIMIT 1"
    )

    booking_row = db.execute(text(query), {"bid": bid}).fetchone()
    if not booking_row:
        raise APIException("Completed visit not found", status_code=404)

    booking = dict(booking_row._mapping)
    if int(booking.get("caretaker_user_id") or 0) != cid:
        raise APIException("You are not allowed to view this visit", status_code=403)

    if str(booking.get("status") or "") != "completed":
        raise APIException("Completed visit not found", status_code=404)

    # Fetch latest visit
    v_row = db.execute(
        text(
            "SELECT id, check_in_time, check_out_time, notes "
            "FROM visit_tracking "
            "WHERE booking_id = :bid AND caretaker_user_id = :cid "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"bid": bid, "cid": cid},
    ).fetchone()

    if not v_row or not v_row._mapping.get("check_out_time"):
        raise APIException("Completed visit not found", status_code=404)

    visit = dict(v_row._mapping)
    duration_minutes = _calculate_duration_minutes(visit.get("check_in_time"), visit.get("check_out_time"))

    # Tasks breakdown
    tasks_rows = db.execute(
        text(
            "SELECT id, title, description, status, completed_at "
            "FROM booking_checklist_tasks "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": bid},
    ).fetchall()

    completed_tasks = []
    incomplete_tasks = []
    for t in tasks_rows:
        t_data = {
            "task_id": int(t._mapping["id"]),
            "title": care_request_text(t._mapping.get("title") or ""),
            "description": care_request_text(t._mapping.get("description") or ""),
            "status": normalize_task_status(t._mapping.get("status") or "pending") or "pending",
            "completed_at": care_request_datetime(t._mapping.get("completed_at")),
        }
        if t_data["status"] == "completed":
            completed_tasks.append(t_data)
        else:
            incomplete_tasks.append(t_data)

    # Live care notes
    notes_rows = db.execute(
        text("SELECT id, note, created_at FROM visit_notes WHERE booking_id = :bid ORDER BY id ASC"),
        {"bid": bid},
    ).fetchall()
    live_care_notes = [
        {
            "note_id": int(n._mapping["id"]),
            "note": care_request_text(n._mapping.get("note") or ""),
            "created_at": care_request_datetime(n._mapping.get("created_at")),
        }
        for n in notes_rows
    ]

    # SOS incidents
    sos_rows = db.execute(
        text(
            "SELECT id, message, latitude, longitude, status, created_at "
            "FROM sos_alerts "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": bid},
    ).fetchall()
    sos_incidents = [
        {
            "sos_id": int(s._mapping["id"]),
            "message": care_request_text(s._mapping.get("message") or ""),
            "latitude": float(s._mapping["latitude"]) if s._mapping.get("latitude") is not None else None,
            "longitude": float(s._mapping["longitude"]) if s._mapping.get("longitude") is not None else None,
            "status": str(care_request_text(s._mapping.get("status") or "")).lower(),
            "created_at": care_request_datetime(s._mapping.get("created_at")),
        }
        for s in sos_rows
    ]

    coords = care_request_parse_coordinates(booking)
    start = care_request_time(booking.get("start_time"))
    end = care_request_time(booking.get("end_time"))
    completed_at = booking.get("completed_at") or visit.get("check_out_time")

    return {
        "booking_id": bid,
        "visit_id": int(visit["id"]),
        "status": "completed",
        "patient": {
            "id": int(booking["patient_id"]) if booking.get("patient_id") is not None else 0,
            "name": care_request_text(booking.get("patient_name") or ""),
            "age": int(booking["age"]) if booking.get("age") is not None else 0,
            "gender": care_request_text(booking.get("gender") or ""),
            "condition": care_request_text(booking.get("medical_condition") or ""),
            "phone": care_request_text(booking.get("family_phone") or ""),
        },
        "caretaker": {
            "id": cid,
            "name": care_request_text(booking.get("caretaker_name") or ""),
            "photo_url": care_request_text(booking.get("caretaker_photo_url") or ""),
        },
        "booking": {
            "booking_date": care_request_date(booking.get("booking_date")),
            "start_time": start,
            "end_time": end,
            "display_time": care_request_display_time(start, end),
            "service_type": care_request_text(booking.get("service_type") or ""),
            "location_short": care_request_location_short(booking.get("address") or ""),
            "address": care_request_text(booking.get("address") or ""),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
        },
        "check_in_time": care_request_datetime(visit.get("check_in_time")),
        "check_out_time": care_request_datetime(visit.get("check_out_time")),
        "completed_at": care_request_datetime(completed_at),
        "duration_minutes": duration_minutes,
        "duration_label": _format_duration_label(duration_minutes),
        "tasks_completed": len(completed_tasks),
        "tasks_total": len(completed_tasks) + len(incomplete_tasks),
        "completed_tasks": completed_tasks,
        "incomplete_tasks": incomplete_tasks,
        "live_care_notes": live_care_notes,
        "sos_incidents": sos_incidents,
        "final_checkout_notes": care_request_text(visit.get("notes") or ""),
        "payout_status": str(care_request_text(booking.get("payout_status") or "")).lower(),
        "caretaker_earning_amount": float(booking.get("caretaker_earning_amount") or 0),
        "care_points_earned": max(20, int(booking.get("care_points_earned") or 0)),
    }

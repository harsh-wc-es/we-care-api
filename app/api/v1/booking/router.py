"""
WeCare — Booking Domain Router

Implements all 11 booking endpoints with strict behavioral parity to FastAPI.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_user,
    require_caretaker,
    require_family,
)
from app.services.audit_service import audit_log
from app.services.availability_service import (
    restore_caretaker_availability_after_visit,
    touch_caretaker_presence,
)
from app.services.booking_service import (
    create_booking,
    generate_visit_otp,
    get_caretaker_request_detail,
    get_caretaker_requests,
    get_my_bookings,
)
from app.services.booking_workflow_service import booking_workflow_transition
from app.services.care_request_service import (
    care_request_datetime,
    care_request_decline_reasons,
)
from app.services.notification_service import notify_admins_caretaker_cancelled
from app.services.refund_service import (
    create_booking_refund_if_payable,
    refund_format_money,
    refund_iso,
    refund_policy_for_family_cancellation,
    refund_public_status,
    successful_booking_payment_summary,
    sync_cancelled_booking_refund_snapshot,
)

router = APIRouter(tags=["Booking"])


def _family_cancel_reasons() -> Dict[str, str]:
    return {
        "change_of_plan": "Change of plan",
        "caretaker_not_needed": "Caretaker not needed",
        "schedule_changed": "Schedule changed",
        "booked_by_mistake": "Booked by mistake",
        "emergency": "Emergency",
        "other": "Other",
    }


def _caretaker_cancel_reasons() -> Dict[str, str]:
    return {
        "sick": "Sick / unwell",
        "emergency": "Emergency",
        "schedule_conflict": "Schedule conflict",
        "travel_issue": "Travel issue",
        "personal_reasons": "Personal reasons",
        "other": "Other",
    }


# ============================================================================
# 1. CREATE BOOKING
# ============================================================================
@router.post("/create_booking", status_code=201)
async def api_create_booking(
    request: Request,
    user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    result = create_booking(db, family_user_id=int(user["id"]), data=data)
    return success_response(
        message="Booking request created successfully",
        data=result,
        status_code=201,
    )


# ============================================================================
# 2. MY BOOKINGS
# ============================================================================
@router.get("/my_bookings")
def api_my_bookings(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    paginated: bool = Query(False),
    user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data, pagination = get_my_bookings(
        db=db,
        user=user,
        page=page,
        limit=limit,
        status=status,
        paginated=paginated,
    )
    return success_response(
        message="Bookings retrieved successfully",
        data=data,
        status_code=200,
    )


# ============================================================================
# 3. CARETAKER REQUESTS (NEW WORKFLOW)
# ============================================================================
@router.get("/caretaker_requests")
def api_caretaker_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    result = get_caretaker_requests(
        db=db,
        caretaker_user_id=int(user["id"]),
        page=page,
        limit=limit,
    )
    return success_response(
        message="Caretaker requests retrieved successfully",
        data=result,
        status_code=200,
    )


# ============================================================================
# 4. CARETAKER REQUEST DETAIL
# ============================================================================
@router.get("/caretaker_request_detail")
def api_caretaker_request_detail(
    booking_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    if not booking_id:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id is required"]},
            status_code=400,
        )

    try:
        bid = int(booking_id)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    result = get_caretaker_request_detail(
        db=db,
        caretaker_user_id=int(user["id"]),
        booking_id=bid,
    )
    return success_response(
        message="Care request detail retrieved successfully",
        data=result,
        status_code=200,
    )


# ============================================================================
# 5. RESPOND REQUEST
# ============================================================================
@router.post("/respond_request")
async def api_respond_request(
    request: Request,
    user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    touch_caretaker_presence(db, int(user["id"]))

    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    action = str(data.get("action") or "").lower().strip()
    decline_reason_code = str(
        data.get("decline_reason_code") or data.get("decline_reason") or ""
    ).lower().strip()
    decline_note = str(data.get("decline_note") or "").strip()

    if not booking_id_raw:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    try:
        bid = int(booking_id_raw)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    if action not in ("accept", "decline"):
        raise APIException(
            message="Validation failed",
            errors={"action": ["Allowed values are accept and decline"]},
            status_code=400,
        )

    decline_reasons = care_request_decline_reasons()
    if action == "decline" and decline_reason_code not in decline_reasons:
        raise APIException(
            message="Validation failed",
            errors={
                "decline_reason_code": [
                    "Allowed values are not_available, location_too_far, not_comfortable_with_care, personal_reasons, other"
                ]
            },
            status_code=400,
        )

    if action == "decline" and decline_reason_code == "other" and not decline_note:
        raise APIException(
            message="Validation failed",
            errors={"decline_note": ["Please enter a reason"]},
            status_code=422,
        )

    if action == "decline" and len(decline_note) > 1000:
        raise APIException(
            message="Validation failed",
            errors={"decline_note": ["Decline note must not exceed 1000 characters"]},
            status_code=422,
        )

    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=int(user["id"]),
        actor_role="caretaker",
        to_status="accepted" if action == "accept" else "declined",
        options={
            "caretaker_user_id": int(user["id"]),
            "decline_reason_code": decline_reason_code if action == "decline" else None,
            "decline_reason_label": decline_reasons.get(decline_reason_code) if action == "decline" else None,
            "decline_note": decline_note if action == "decline" else None,
        },
    )

    if not transition["success"]:
        raise APIException(
            message=transition["message"],
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    db.commit()

    new_status = transition["to_status"]
    visit_otp_required = transition["visit_otp_required"]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    confirmation = {
        "booking_id": bid,
        "request_id": bid,
        "status": new_status,
        "action": action,
        "message": "Request accepted successfully" if action == "accept" else "Request declined successfully",
        "decline_reason_code": decline_reason_code if action == "decline" else "",
        "decline_reason_label": decline_reasons.get(decline_reason_code, "") if action == "decline" else "",
        "decline_note": decline_note if action == "decline" else "",
        "visit_otp_required": visit_otp_required,
        "visit_id": int(transition["visit_id"]) if (action == "accept" and transition.get("visit_id")) else None,
        "latitude": transition.get("latitude"),
        "longitude": transition.get("longitude"),
        "can_navigate": transition.get("latitude") is not None and transition.get("longitude") is not None,
        "can_start_visit": False,
        "requires_otp": visit_otp_required,
        "responded_at": now_iso,
        "status_transitions": [
            "pending -> accepted -> in_progress -> completed",
            "pending -> declined",
            "pending -> cancelled",
        ],
        "enums": {
            "booking_status": ["pending", "accepted", "in_progress", "completed", "declined", "cancelled"],
            "request_action": ["accept", "decline"],
            "decline_reason_code": list(decline_reasons.keys()),
        },
        "next_steps": (
            {
                "show_confirmation": True,
                "can_start_visit": False,
                "requires_visit_otp": True,
                "detail_endpoint": f"/api/v1/booking/caretaker_request_detail?booking_id={bid}",
                "verify_otp_endpoint": "/api/v1/visit/verify_start_otp",
                "check_in_endpoint": "/api/v1/visit/check_in",
            }
            if action == "accept"
            else {
                "show_confirmation": True,
                "return_to_requests": True,
            }
        ),
    }

    return success_response(
        message="Request responded successfully",
        data=confirmation,
        status_code=200,
    )


# ============================================================================
# 6. ACCEPT BOOKING
# ============================================================================
@router.post("/accept_booking")
async def api_accept_booking(
    request: Request,
    user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    touch_caretaker_presence(db, int(user["id"]))

    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    if not booking_id_raw:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    try:
        bid = int(booking_id_raw)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=int(user["id"]),
        actor_role="caretaker",
        to_status="accepted",
        options={"caretaker_user_id": int(user["id"])},
    )

    if not transition["success"]:
        raise APIException(
            message=transition["message"],
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    db.commit()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    return success_response(
        message="Booking accepted successfully",
        data={
            "booking_id": bid,
            "status": "accepted",
            "visit_id": int(transition.get("visit_id") or 0),
            "visit_otp_required": True,
            "requires_otp": True,
            "responded_at": now_iso,
        },
        status_code=200,
    )


# ============================================================================
# 7. REJECT BOOKING
# ============================================================================
@router.post("/reject_booking")
async def api_reject_booking(
    request: Request,
    user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    decline_reason_code = str(
        data.get("decline_reason_code") or data.get("decline_reason") or "other"
    ).lower().strip()
    decline_note = str(data.get("decline_note") or "").strip()

    if not booking_id_raw:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    try:
        bid = int(booking_id_raw)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    reasons = care_request_decline_reasons()
    if decline_reason_code not in reasons:
        raise APIException(
            message="Validation failed",
            errors={
                "decline_reason_code": [
                    "Allowed values are not_available, location_too_far, not_comfortable_with_care, personal_reasons, other"
                ]
            },
            status_code=400,
        )

    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=int(user["id"]),
        actor_role="caretaker",
        to_status="declined",
        options={
            "caretaker_user_id": int(user["id"]),
            "decline_reason_code": decline_reason_code,
            "decline_reason_label": reasons[decline_reason_code],
            "decline_note": decline_note,
        },
    )

    if not transition["success"]:
        raise APIException(
            message=transition["message"],
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    db.commit()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    return success_response(
        message="Booking declined successfully",
        data={
            "booking_id": bid,
            "status": "declined",
            "decline_reason_code": decline_reason_code,
            "decline_reason_label": reasons[decline_reason_code],
            "decline_note": decline_note,
            "responded_at": now_iso,
        },
        status_code=200,
    )


# ============================================================================
# 8. CANCEL BOOKING (FAMILY)
# ============================================================================
@router.post("/cancel_booking")
async def api_cancel_booking(
    request: Request,
    user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    reason_code = str(data.get("cancel_reason_code") or data.get("cancellation_reason") or data.get("reason") or "").strip()
    cancel_note = str(data.get("cancel_note") or "").strip()
    reason_labels = _family_cancel_reasons()

    errors: Dict[str, List[str]] = {}
    if not booking_id_raw:
        errors["booking_id"] = ["Booking id must be a valid integer"]
    else:
        try:
            bid = int(booking_id_raw)
            if bid < 1:
                errors["booking_id"] = ["Booking id must be a valid integer"]
        except ValueError:
            errors["booking_id"] = ["Booking id must be a valid integer"]

    if not reason_code or reason_code not in reason_labels:
        errors["cancel_reason_code"] = ["Invalid cancellation reason"]

    if len(cancel_note) > 1000:
        errors["cancel_note"] = ["Cancel note must not exceed 1000 characters"]

    if errors:
        raise APIException(
            message="Validation failed",
            errors=errors,
            status_code=400,
        )

    bid = int(booking_id_raw)
    reason_label = reason_labels[reason_code]

    # Row lock on booking
    row = db.execute(
        text(
            "SELECT id, family_user_id, caretaker_user_id, status, booking_date, start_time, "
            "       paid_amount, cancelled_at "
            "FROM bookings "
            "WHERE id = :bid "
            "FOR UPDATE"
        ),
        {"bid": bid},
    ).fetchone()

    if not row:
        raise APIException(
            message="Booking not found",
            status_code=404,
        )

    booking = dict(row._mapping)

    if int(booking["family_user_id"]) != int(user["id"]):
        raise APIException(
            message="You do not have permission to cancel this booking",
            errors={"booking_id": ["This booking does not belong to the authenticated family user"]},
            status_code=403,
        )

    if str(booking["status"]).lower() not in ("pending", "accepted"):
        raise APIException(
            message="Booking cannot be cancelled in its current status",
            errors={"status": ["Only pending or accepted upcoming bookings can be cancelled"]},
            status_code=409,
        )

    # Parse start time
    b_date = str(booking["booking_date"])
    s_time = str(booking["start_time"])
    try:
        visit_start_dt = datetime.strptime(f"{b_date} {s_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            visit_start_dt = datetime.strptime(f"{b_date} {s_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            visit_start_dt = None

    if not visit_start_dt:
        raise APIException(
            message="Booking start time is invalid",
            errors={"booking_date": ["Booking date/start time could not be parsed"]},
            status_code=409,
        )

    now_dt = datetime.now()
    if visit_start_dt <= now_dt:
        raise APIException(
            message="Visit has already started and cannot be cancelled",
            errors={"booking": ["Only future visits can be cancelled"]},
            status_code=409,
        )

    payment_summary = successful_booking_payment_summary(db, bid)
    paid_amount = payment_summary["paid_amount"]
    payment_id = payment_summary["payment_id"]

    hours_before = (visit_start_dt - now_dt).total_seconds() / 3600.0
    refund_percentage, policy_label = refund_policy_for_family_cancellation(hours_before)
    refund_amount = refund_format_money(paid_amount * (refund_percentage / 100))
    cancellation_fee = refund_format_money(paid_amount - refund_amount)
    refund_eligible = refund_amount > 0
    refund_status = "pending" if refund_eligible else "not_applicable"

    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=int(user["id"]),
        actor_role="family",
        to_status="cancelled",
        options={
            "cancellation_reason": reason_label,
            "notification_metadata": {
                "cancelled_by_role": "family",
                "cancel_reason_code": reason_code,
                "cancel_reason_label": reason_label,
                "refund_percentage": float(refund_percentage),
                "refund_amount": float(refund_amount),
                "cancellation_fee": float(cancellation_fee),
                "refund_status": refund_status,
            },
        },
    )

    if not transition["success"]:
        raise APIException(
            message=transition["message"],
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    db.execute(
        text(
            "UPDATE bookings "
            "SET cancelled_by = 'family', "
            "    cancellation_reason = :reason_label, "
            "    cancelled_at = NOW(), "
            "    cancelled_by_user_id = :uid, "
            "    cancelled_by_role = 'family', "
            "    cancel_reason_code = :reason_code, "
            "    cancel_reason_label = :reason_label, "
            "    cancel_note = :cancel_note, "
            "    refund_percentage = :refund_percentage, "
            "    refund_amount = :refund_amount, "
            "    cancellation_fee = :cancellation_fee, "
            "    refund_eligible = :refund_eligible, "
            "    refund_status = :refund_status, "
            "    payout_status = 'not_applicable', "
            "    updated_at = NOW() "
            "WHERE id = :bid AND status = 'cancelled'"
        ),
        {
            "reason_label": reason_label,
            "uid": int(user["id"]),
            "reason_code": reason_code,
            "cancel_note": cancel_note if cancel_note else None,
            "refund_percentage": str(refund_percentage),
            "refund_amount": str(refund_amount),
            "cancellation_fee": str(cancellation_fee),
            "refund_eligible": 1 if refund_eligible else 0,
            "refund_status": refund_status,
            "bid": bid,
        },
    )

    sync_cancelled_booking_refund_snapshot(
        db=db,
        booking_id=bid,
        paid_amount=paid_amount,
        refund_percentage=refund_percentage,
        refund_amount=refund_amount,
    )

    refund_id, refund_record_created = create_booking_refund_if_payable(
        db=db,
        booking=booking,
        paid_amount=paid_amount,
        refund_percentage=refund_percentage,
        refund_amount=refund_amount,
        payment_id=payment_id,
        reason=reason_label,
    )

    cancelled_at_row = db.execute(
        text("SELECT cancelled_at FROM bookings WHERE id = :bid LIMIT 1"),
        {"bid": bid},
    ).fetchone()
    cancelled_at = cancelled_at_row[0] if cancelled_at_row else None

    audit_log(
        db=db,
        admin_user_id=int(user["id"]),
        action="family_cancel_booking",
        entity_type="booking",
        entity_id=bid,
        old_values={"status": booking["status"], "paid_amount": float(paid_amount)},
        new_values={
            "status": "cancelled",
            "cancel_reason_code": reason_code,
            "cancel_reason_label": reason_label,
            "refund_percentage": float(refund_percentage),
            "refund_amount": float(refund_amount),
            "cancellation_fee": float(cancellation_fee),
            "refund_status": refund_status,
            "refund_id": refund_id,
        },
    )

    db.commit()

    return success_response(
        message="Booking cancelled successfully",
        data={
            "booking_id": bid,
            "status": "cancelled",
            "cancelled_at": refund_iso(cancelled_at),
            "refund": {
                "eligible": bool(refund_eligible),
                "refund_eligible": bool(refund_eligible),
                "refund_id": refund_id,
                "paid_amount": float(paid_amount),
                "refund_percentage": float(refund_percentage),
                "refund_amount": float(refund_amount),
                "cancellation_fee": float(cancellation_fee),
                "status": refund_public_status(refund_id, refund_amount),
                "refund_status": refund_status,
                "refund_record_created": refund_record_created,
                "policy_label": policy_label,
                "message": (
                    "Refund request created and pending admin review"
                    if refund_eligible
                    else "Cancellation is not eligible for refund"
                ),
            },
        },
        status_code=200,
    )


# ============================================================================
# 9. CARETAKER CANCEL BOOKING
# ============================================================================
@router.post("/caretaker_cancel_booking")
async def api_caretaker_cancel_booking(
    request: Request,
    user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    reason_code = str(
        data.get("cancel_reason_code") or data.get("cancellation_reason") or data.get("reason") or ""
    ).strip()
    cancel_note = str(data.get("cancel_note") or "").strip()
    reason_labels = _caretaker_cancel_reasons()

    errors: Dict[str, List[str]] = {}
    if not booking_id_raw:
        errors["booking_id"] = ["Booking id must be a valid integer"]
    else:
        try:
            bid = int(booking_id_raw)
            if bid < 1:
                errors["booking_id"] = ["Booking id must be a valid integer"]
        except ValueError:
            errors["booking_id"] = ["Booking id must be a valid integer"]

    if not reason_code or reason_code not in reason_labels:
        errors["cancel_reason_code"] = ["Invalid cancellation reason"]

    if len(cancel_note) > 1000:
        errors["cancel_note"] = ["Cancel note must not exceed 1000 characters"]

    if errors:
        raise APIException(
            message="Validation failed",
            errors=errors,
            status_code=400,
        )

    bid = int(booking_id_raw)
    reason_label = reason_labels[reason_code]

    # Lock booking row
    row = db.execute(
        text(
            "SELECT id, family_user_id, caretaker_user_id, status, booking_date, start_time, "
            "       paid_amount, cancelled_at "
            "FROM bookings "
            "WHERE id = :bid "
            "FOR UPDATE"
        ),
        {"bid": bid},
    ).fetchone()

    if not row:
        raise APIException(
            message="Booking not found",
            status_code=404,
        )

    booking = dict(row._mapping)

    if int(booking["caretaker_user_id"] or 0) != int(user["id"]):
        raise APIException(
            message="You do not have permission to cancel this booking",
            errors={"booking_id": ["This booking does not belong to the authenticated caretaker"]},
            status_code=403,
        )

    b_status = str(booking["status"]).lower()
    if b_status == "pending":
        raise APIException(
            message="Use decline request for pending bookings",
            errors={"status": ["Pending booking requests must be declined, not cancelled"]},
            status_code=409,
        )

    if b_status != "accepted":
        raise APIException(
            message="Booking cannot be cancelled in its current status",
            errors={"status": ["Only accepted upcoming bookings can be cancelled by caretaker"]},
            status_code=409,
        )

    b_date = str(booking["booking_date"])
    s_time = str(booking["start_time"])
    try:
        visit_start_dt = datetime.strptime(f"{b_date} {s_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            visit_start_dt = datetime.strptime(f"{b_date} {s_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            visit_start_dt = None

    if not visit_start_dt:
        raise APIException(
            message="Booking start time is invalid",
            errors={"booking_date": ["Booking date/start time could not be parsed"]},
            status_code=409,
        )

    now_dt = datetime.now()
    if visit_start_dt <= now_dt:
        raise APIException(
            message="Visit has already started and cannot be cancelled",
            errors={"booking": ["Only future accepted bookings can be cancelled"]},
            status_code=409,
        )

    payment_summary = successful_booking_payment_summary(db, bid)
    paid_amount = payment_summary["paid_amount"]
    payment_id = payment_summary["payment_id"]

    refund_percentage = refund_format_money(100.00)
    refund_amount = paid_amount
    cancellation_fee = refund_format_money(0.00)
    refund_eligible = refund_amount > 0
    refund_status = "pending" if refund_eligible else "not_applicable"

    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=int(user["id"]),
        actor_role="caretaker",
        to_status="cancelled",
        options={
            "cancellation_reason": reason_label,
            "notification_metadata": {
                "cancelled_by_role": "caretaker",
                "cancel_reason_code": reason_code,
                "cancel_reason_label": reason_label,
                "refund_percentage": float(refund_percentage),
                "refund_amount": float(refund_amount),
                "cancellation_fee": float(cancellation_fee),
                "refund_status": refund_status,
            },
        },
    )

    if not transition["success"]:
        raise APIException(
            message=transition["message"],
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    db.execute(
        text(
            "UPDATE bookings "
            "SET cancelled_by = 'caretaker', "
            "    cancellation_reason = :reason_label, "
            "    cancelled_at = NOW(), "
            "    cancelled_by_user_id = :uid, "
            "    cancelled_by_role = 'caretaker', "
            "    cancel_reason_code = :reason_code, "
            "    cancel_reason_label = :reason_label, "
            "    cancel_note = :cancel_note, "
            "    refund_percentage = :refund_percentage, "
            "    refund_amount = :refund_amount, "
            "    cancellation_fee = :cancellation_fee, "
            "    refund_eligible = :refund_eligible, "
            "    refund_status = :refund_status, "
            "    payout_status = 'not_applicable', "
            "    updated_at = NOW() "
            "WHERE id = :bid AND status = 'cancelled'"
        ),
        {
            "reason_label": reason_label,
            "uid": int(user["id"]),
            "reason_code": reason_code,
            "cancel_note": cancel_note if cancel_note else None,
            "refund_percentage": str(refund_percentage),
            "refund_amount": str(refund_amount),
            "cancellation_fee": str(cancellation_fee),
            "refund_eligible": 1 if refund_eligible else 0,
            "refund_status": refund_status,
            "bid": bid,
        },
    )

    sync_cancelled_booking_refund_snapshot(
        db=db,
        booking_id=bid,
        paid_amount=paid_amount,
        refund_percentage=refund_percentage,
        refund_amount=refund_amount,
    )

    refund_id, refund_record_created = create_booking_refund_if_payable(
        db=db,
        booking=booking,
        paid_amount=paid_amount,
        refund_percentage=refund_percentage,
        refund_amount=refund_amount,
        payment_id=payment_id,
        reason=reason_label,
    )

    # Replacement ticket
    replacement_reason = f"Caretaker cancelled accepted booking: {reason_label}"
    if cancel_note:
        replacement_reason += f" - {cancel_note}"

    rep_row = db.execute(
        text(
            "SELECT id FROM replacement_tickets "
            "WHERE booking_id = :bid AND status IN ('open','assigned') "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"bid": bid},
    ).fetchone()

    if not rep_row:
        db.execute(
            text(
                "INSERT INTO replacement_tickets "
                "(booking_id, family_user_id, original_caretaker_user_id, reason) "
                "VALUES (:bid, :fuid, :cid, :reason)"
            ),
            {
                "bid": bid,
                "fuid": int(booking["family_user_id"]),
                "cid": int(user["id"]),
                "reason": replacement_reason,
            },
        )
        rep_id_row = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
        replacement_ticket_id = int(rep_id_row["id"]) if rep_id_row else None
    else:
        replacement_ticket_id = int(rep_row[0])

    avail_res = restore_caretaker_availability_after_visit(db, int(user["id"]), bid)
    availability_restored = bool(avail_res.get("restored", False))

    cancelled_at_row = db.execute(
        text("SELECT cancelled_at FROM bookings WHERE id = :bid LIMIT 1"),
        {"bid": bid},
    ).fetchone()
    cancelled_at = cancelled_at_row[0] if cancelled_at_row else None

    audit_log(
        db=db,
        admin_user_id=int(user["id"]),
        action="caretaker_cancel_booking",
        entity_type="booking",
        entity_id=bid,
        old_values={"status": booking["status"], "paid_amount": float(paid_amount)},
        new_values={
            "status": "cancelled",
            "cancel_reason_code": reason_code,
            "cancel_reason_label": reason_label,
            "refund_percentage": float(refund_percentage),
            "refund_amount": float(refund_amount),
            "cancellation_fee": float(cancellation_fee),
            "refund_status": refund_status,
            "refund_id": refund_id,
            "replacement_ticket_id": replacement_ticket_id,
            "availability_restored": availability_restored,
        },
    )

    db.commit()

    notify_admins_caretaker_cancelled(
        db=db,
        booking_id=bid,
        caretaker_user_id=int(user["id"]),
        metadata={
            "cancel_reason_code": reason_code,
            "cancel_reason_label": reason_label,
            "replacement_ticket_id": replacement_ticket_id,
            "refund_status": refund_status,
        },
    )

    return success_response(
        message="Booking cancelled successfully",
        data={
            "booking_id": bid,
            "status": "cancelled",
            "cancelled_at": refund_iso(cancelled_at),
            "cancelled_by_role": "caretaker",
            "replacement_ticket_id": replacement_ticket_id,
            "availability_restored": availability_restored,
            "refund": {
                "eligible": bool(refund_eligible),
                "refund_eligible": bool(refund_eligible),
                "refund_id": refund_id,
                "paid_amount": float(paid_amount),
                "refund_percentage": float(refund_percentage),
                "refund_amount": float(refund_amount),
                "cancellation_fee": float(cancellation_fee),
                "status": refund_public_status(refund_id, refund_amount),
                "refund_status": refund_status,
                "refund_record_created": refund_record_created,
                "policy_label": "Caretaker cancelled before visit start",
                "message": (
                    "Refund request created and pending admin review"
                    if refund_eligible
                    else "Cancellation is not eligible for refund"
                ),
            },
        },
        status_code=200,
    )


# ============================================================================
# 10. COMPLETE BOOKING
# ============================================================================
@router.post("/complete_booking")
async def api_complete_booking(
    request: Request,
    user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    if not booking_id_raw:
        raise APIException(
            message="Booking id is required",
            status_code=400,
        )

    try:
        bid = int(booking_id_raw)
    except ValueError:
        raise APIException(
            message="Booking id is required",
            status_code=400,
        )

    row = db.execute(
        text(
            "SELECT id, caretaker_user_id, status "
            "FROM bookings "
            "WHERE id = :bid AND caretaker_user_id = :cid AND status IN ('accepted','in_progress') "
            "FOR UPDATE"
        ),
        {"bid": bid, "cid": int(user["id"])},
    ).fetchone()

    if not row:
        raise APIException(
            message="Booking not found or not accepted",
            status_code=404,
        )

    curr_status = str(row._mapping["status"]).lower()

    if curr_status == "accepted":
        t1 = booking_workflow_transition(
            db=db,
            booking_id=bid,
            actor_user_id=int(user["id"]),
            actor_role="caretaker",
            to_status="in_progress",
            options={"caretaker_user_id": int(user["id"])},
        )
        if not t1["success"]:
            raise APIException(
                message=t1["message"],
                errors=t1.get("errors"),
                status_code=t1.get("status", 400),
            )

    t2 = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=int(user["id"]),
        actor_role="caretaker",
        to_status="completed",
        options={"caretaker_user_id": int(user["id"])},
    )

    if not t2["success"]:
        raise APIException(
            message=t2["message"],
            errors=t2.get("errors"),
            status_code=t2.get("status", 400),
        )

    restore_res = restore_caretaker_availability_after_visit(db, int(user["id"]), bid)
    restored = bool(restore_res.get("restored", False))

    db.commit()

    return success_response(
        message="Booking completed successfully",
        data={
            "payout_status": "hold",
            "availability_restored": restored,
        },
        status_code=200,
    )


# ============================================================================
# 11. VISIT OTP
# ============================================================================
@router.post("/visit_otp")
async def api_visit_otp(
    request: Request,
    user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    if not booking_id_raw:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    try:
        bid = int(booking_id_raw)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    result = generate_visit_otp(db, family_user_id=int(user["id"]), booking_id=bid)
    return success_response(
        message="Visit start OTP generated",
        data=result,
        status_code=200,
    )

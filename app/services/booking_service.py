"""
WeCare — Booking Service

Handles booking creation, pricing calculations, listings, detail aggregations,
and OTP generation for bookings.
"""

from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.availability_service import (
    caretaker_has_active_visit,
    touch_caretaker_presence,
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
from app.services.notification_service import (
    create_notification,
    notify_booking_created,
)
from app.services.otp_service import otp_can_resend, otp_create, otp_latest
from app.services.refund_service import (
    refund_format_money,
    refund_iso,
    refund_public_status,
)


def _to_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def create_booking(
    db: Session,
    family_user_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/booking/create_booking L15-189
    Creates a new booking request within an explicit transaction using SELECT ... FOR UPDATE.
    """
    caretaker_user_id = str(data.get("caretaker_user_id") or "").strip()
    patient_id = str(data.get("patient_id") or "").strip()
    service_type = str(data.get("service_type") or "").strip()
    booking_date = str(data.get("booking_date") or "").strip()
    start_time = str(data.get("start_time") or "").strip()
    end_time = str(data.get("end_time") or "").strip()
    address = str(data.get("address") or "").strip()
    notes = str(data.get("notes") or "").strip()

    # Validate required fields (L25-35)
    missing: Dict[str, List[str]] = {}
    if not caretaker_user_id:
        missing["caretaker_user_id"] = ["Caretaker user id is required"]
    if not patient_id:
        missing["patient_id"] = ["Patient id is required"]
    if not service_type:
        missing["service_type"] = ["Service type is required"]
    if not booking_date:
        missing["booking_date"] = ["Booking date is required"]
    if not start_time:
        missing["start_time"] = ["Start time is required"]
    if not end_time:
        missing["end_time"] = ["End time is required"]
    if not address:
        missing["address"] = ["Address is required"]

    if missing:
        raise APIException(
            message="Required fields missing",
            errors=missing,
            status_code=400,
        )

    try:
        cid = int(caretaker_user_id)
        pid = int(patient_id)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={
                "caretaker_user_id": ["Caretaker user id must be an integer"],
                "patient_id": ["Patient id must be an integer"],
            },
            status_code=400,
        )

    # Begin explicit transaction and row lock on caretaker_profiles & users (L41-63)
    caretaker_row = db.execute(
        text(
            "SELECT cp.user_id, cp.pricing_tier_id, cp.pricing_tier, cp.skill_level, "
            "       cp.customer_hourly_rate, cp.caretaker_hourly_rate, cp.platform_commission_hourly, "
            "       cp.is_available, cp.availability_locked_by_admin, cp.availability_reason, "
            "       u.is_active, cp.verification_status "
            "FROM caretaker_profiles cp "
            "INNER JOIN users u ON u.id = cp.user_id "
            "WHERE cp.user_id = :cid "
            "  AND u.role = 'caretaker' "
            "  AND cp.verification_status = 'approved' "
            "FOR UPDATE"
        ),
        {"cid": cid},
    ).fetchone()

    if not caretaker_row:
        raise APIException(
            message="Caretaker not approved or not found",
            status_code=400,
        )

    ct = dict(caretaker_row._mapping)

    # Verify availability inside transaction (L71-76)
    if int(ct.get("is_active") or 0) != 1 or int(ct.get("is_available") or 0) != 1:
        raise APIException(
            message="Caretaker is currently unavailable",
            errors={"caretaker": ["This caretaker is not accepting bookings right now"]},
            status_code=400,
        )

    # Verify no admin lock (L79-84)
    if int(ct.get("availability_locked_by_admin") or 0) == 1 and not (int(ct.get("is_available") or 0) == 1):
        raise APIException(
            message="Caretaker is currently unavailable",
            errors={"caretaker": ["This caretaker is not accepting bookings right now"]},
            status_code=400,
        )

    # Verify no active visit (L87-92)
    if caretaker_has_active_visit(db, cid):
        raise APIException(
            message="Caretaker is currently unavailable",
            errors={"caretaker": ["This caretaker is currently on a visit"]},
            status_code=400,
        )

    customer_hourly_rate = _to_decimal(ct.get("customer_hourly_rate"))
    caretaker_hourly_rate = _to_decimal(ct.get("caretaker_hourly_rate"))
    platform_commission_hourly = _to_decimal(ct.get("platform_commission_hourly"))

    if customer_hourly_rate <= Decimal("0.00") or caretaker_hourly_rate <= Decimal("0.00") or caretaker_hourly_rate > customer_hourly_rate:
        raise APIException(
            message="Caretaker pricing is not configured",
            errors={"caretaker_user_id": ["Admin must approve this caretaker with valid pricing before booking"]},
            status_code=400,
        )

    if platform_commission_hourly < Decimal("0.00"):
        platform_commission_hourly = _to_decimal(customer_hourly_rate - caretaker_hourly_rate)

    # Parse and validate duration (L109-118)
    try:
        start_dt = datetime.strptime(f"{booking_date} {start_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            start_dt = datetime.strptime(f"{booking_date} {start_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            start_dt = None

    try:
        end_dt = datetime.strptime(f"{booking_date} {end_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            end_dt = datetime.strptime(f"{booking_date} {end_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            end_dt = None

    if not start_dt or not end_dt or end_dt <= start_dt:
        raise APIException(
            message="Invalid booking duration",
            errors={
                "start_time": ["Start time must be before end time"],
                "end_time": ["End time must be after start time"],
            },
            status_code=400,
        )

    seconds = (end_dt - start_dt).total_seconds()
    total_hours = Decimal(str(round(seconds / 3600.0, 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_customer_amount = _to_decimal(total_hours * customer_hourly_rate)
    caretaker_earning_amount = _to_decimal(total_hours * caretaker_hourly_rate)
    platform_commission_amount = _to_decimal(total_hours * platform_commission_hourly)
    total_amount = total_customer_amount

    # Patient ownership verification (L126-135)
    pat_row = db.execute(
        text("SELECT id FROM patient_details WHERE id = :pid AND family_user_id = :fuid"),
        {"pid": pid, "fuid": int(family_user_id)},
    ).fetchone()

    if not pat_row:
        raise APIException(
            message="Patient not found for this family user",
            status_code=404,
        )

    # Insert booking (L137-168)
    insert_res = db.execute(
        text(
            "INSERT INTO bookings "
            "(family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            " start_time, end_time, address, notes, total_amount, pricing_tier_id, "
            " pricing_tier, skill_level, customer_hourly_rate, caretaker_hourly_rate, "
            " platform_commission_hourly, total_customer_amount, caretaker_earning_amount, "
            " platform_commission_amount, total_hours, status, payment_status) "
            "VALUES (:fuid, :cid, :pid, :service_type, :booking_date, :start_time, :end_time, "
            " :address, :notes, :total_amount, :tier_id, :tier_slug, :skill_level, "
            " :cust_rate, :care_rate, :comm_rate, :cust_amt, :care_amt, :comm_amt, "
            " :total_hours, 'pending', 'pending')"
        ),
        {
            "fuid": int(family_user_id),
            "cid": cid,
            "pid": pid,
            "service_type": service_type,
            "booking_date": booking_date,
            "start_time": start_time,
            "end_time": end_time,
            "address": address,
            "notes": notes,
            "total_amount": str(total_amount),
            "tier_id": ct.get("pricing_tier_id"),
            "tier_slug": ct.get("pricing_tier"),
            "skill_level": ct.get("skill_level"),
            "cust_rate": str(customer_hourly_rate),
            "care_rate": str(caretaker_hourly_rate),
            "comm_rate": str(platform_commission_hourly),
            "cust_amt": str(total_customer_amount),
            "care_amt": str(caretaker_earning_amount),
            "comm_amt": str(platform_commission_amount),
            "total_hours": str(total_hours),
        },
    )

    last_id_row = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
    booking_id = int(last_id_row["id"]) if last_id_row else 0

    db.commit()

    # Trigger notification (L171)
    notify_booking_created(db, booking_id)

    return {
        "booking_id": booking_id,
        "pricing_tier_id": ct.get("pricing_tier_id"),
        "pricing_tier": ct.get("pricing_tier"),
        "skill_level": ct.get("skill_level"),
        "total_hours": float(total_hours),
        "customer_hourly_rate": float(customer_hourly_rate),
        "total_customer_amount": float(total_customer_amount),
        "total_amount": float(total_amount),
    }


def get_my_bookings(
    db: Session,
    user: Dict[str, Any],
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    paginated: bool = False,
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    """
    Route: api/v1/booking/my_bookings L12-142
    Retrieves bookings list with role-specific field stripping and optional pagination.
    """
    page = max(1, page)
    limit = min(100, max(1, limit))
    offset = (page - 1) * limit
    role = user.get("role")
    uid = int(user["id"])

    status_filter = ""
    params: Dict[str, Any] = {}

    if status and status.strip() and status.strip().lower() != "all":
        st = status.strip().lower()
        if st not in ("pending", "accepted", "in_progress", "completed", "declined", "cancelled"):
            raise APIException(
                message="Validation failed",
                errors={"status": ["Invalid booking status"]},
                status_code=400,
            )
        status_filter = " AND b.status = :status"
        params["status"] = st

    if role == "family":
        count_sql = f"SELECT COUNT(*) FROM bookings b WHERE b.family_user_id = :uid{status_filter}"
        params["uid"] = uid
        total = int(db.execute(text(count_sql), params).scalar() or 0)

        query_sql = f"""
            SELECT b.id, b.family_user_id, b.caretaker_user_id, b.patient_id,
                   b.service_type, b.booking_date, b.start_time, b.end_time, b.address,
                   b.location_latitude, b.location_longitude, b.notes, b.request_priority,
                   b.status, b.cancelled_by, b.cancellation_reason, b.decline_reason_code,
                   b.decline_reason_label, b.decline_note, b.responded_at, b.cancelled_at,
                   b.total_amount, b.pricing_tier_id, b.pricing_tier, b.skill_level,
                   b.customer_hourly_rate, b.total_customer_amount, b.care_points_earned,
                   b.total_hours, b.payment_status, b.created_at, b.updated_at, b.completed_at,
                   b.payout_status, b.payout_hold_until, b.payout_paid_at, b.payout_id,
                   b.paid_amount, b.remaining_amount, p.patient_name, u.username AS caretaker_username
            FROM bookings b
            LEFT JOIN patient_details p ON p.id = b.patient_id
            LEFT JOIN users u ON u.id = b.caretaker_user_id
            WHERE b.family_user_id = :uid{status_filter}
            ORDER BY b.id DESC
            LIMIT :limit OFFSET :offset
        """
    elif role == "caretaker":
        count_sql = f"SELECT COUNT(*) FROM bookings b WHERE b.caretaker_user_id = :uid{status_filter}"
        params["uid"] = uid
        total = int(db.execute(text(count_sql), params).scalar() or 0)

        query_sql = f"""
            SELECT b.id, b.family_user_id, b.caretaker_user_id, b.patient_id,
                   b.service_type, b.booking_date, b.start_time, b.end_time, b.address,
                   b.location_latitude, b.location_longitude, b.notes, b.request_priority,
                   b.status, b.cancelled_by, b.cancellation_reason, b.decline_reason_code,
                   b.decline_reason_label, b.decline_note, b.responded_at, b.cancelled_at,
                   b.pricing_tier_id, b.pricing_tier, b.skill_level, b.caretaker_earning_amount,
                   b.care_points_earned, b.total_hours, b.created_at, b.updated_at, b.completed_at,
                   b.payout_status, b.payout_hold_until, b.payout_paid_at, b.payout_id,
                   p.patient_name, u.username AS family_username
            FROM bookings b
            LEFT JOIN patient_details p ON p.id = b.patient_id
            LEFT JOIN users u ON u.id = b.family_user_id
            WHERE b.caretaker_user_id = :uid{status_filter}
            ORDER BY b.id DESC
            LIMIT :limit OFFSET :offset
        """
    else:  # admin
        admin_where = f"WHERE 1=1{status_filter}" if status_filter else ""
        count_sql = f"SELECT COUNT(*) FROM bookings b {admin_where}"
        total = int(db.execute(text(count_sql), params).scalar() or 0)

        query_sql = f"""
            SELECT b.id, b.family_user_id, b.caretaker_user_id, b.patient_id,
                   b.service_type, b.booking_date, b.start_time, b.end_time, b.address,
                   b.location_latitude, b.location_longitude, b.notes, b.request_priority,
                   b.status, b.cancelled_by, b.cancellation_reason, b.decline_reason_code,
                   b.decline_reason_label, b.decline_note, b.responded_at, b.cancelled_at,
                   b.total_amount, b.pricing_tier_id, b.pricing_tier, b.skill_level,
                   b.customer_hourly_rate, b.caretaker_hourly_rate, b.platform_commission_hourly,
                   b.total_customer_amount, b.caretaker_earning_amount, b.platform_commission_amount,
                   b.care_points_earned, b.total_hours, b.payment_status, b.created_at,
                   b.updated_at, b.completed_at, b.payout_status, b.payout_hold_until,
                   b.payout_paid_at, b.payout_id, b.paid_amount, b.remaining_amount,
                   p.patient_name
            FROM bookings b
            LEFT JOIN patient_details p ON p.id = b.patient_id
            {admin_where}
            ORDER BY b.id DESC
            LIMIT :limit OFFSET :offset
        """

    params["limit"] = limit
    params["offset"] = offset

    rows = db.execute(text(query_sql), params).mappings().all()
    items: List[Dict[str, Any]] = []

    for r in rows:
        item = dict(r)
        # Format datetime fields for JSON response
        for k in ("created_at", "updated_at", "completed_at", "responded_at", "cancelled_at", "payout_hold_until", "payout_paid_at"):
            if k in item and item[k] is not None:
                item[k] = str(item[k])
        if "booking_date" in item and item["booking_date"] is not None:
            item["booking_date"] = str(item["booking_date"])
        if "start_time" in item and item["start_time"] is not None:
            item["start_time"] = str(item["start_time"])
        if "end_time" in item and item["end_time"] is not None:
            item["end_time"] = str(item["end_time"])

        # Convert Decimal values
        for k in (
            "total_amount", "customer_hourly_rate", "caretaker_hourly_rate",
            "platform_commission_hourly", "total_customer_amount",
            "caretaker_earning_amount", "platform_commission_amount",
            "total_hours", "paid_amount", "remaining_amount"
        ):
            if k in item and item[k] is not None:
                item[k] = float(item[k])

        # Role-based field stripping matching L102-126
        if role == "family":
            for f in (
                "caretaker_hourly_rate", "platform_commission_hourly",
                "caretaker_earning_amount", "platform_commission_amount",
                "payout_status", "payout_hold_until", "payout_paid_at", "payout_id"
            ):
                item.pop(f, None)
        elif role == "caretaker":
            for f in (
                "customer_hourly_rate", "caretaker_hourly_rate",
                "platform_commission_hourly", "total_customer_amount",
                "platform_commission_amount", "total_amount",
                "paid_amount", "remaining_amount", "payout_id"
            ):
                item.pop(f, None)

        items.append(item)

    if paginated:
        pagination = {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": int(math.ceil(total / limit)) if limit > 0 else 0,
        }
        return {"items": items, "bookings": items, "pagination": pagination}, pagination

    return items, None


def get_caretaker_requests(
    db: Session,
    caretaker_user_id: int,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/booking/caretaker_requests L8-59
    """
    touch_caretaker_presence(db, caretaker_user_id)

    page = max(1, page)
    limit = min(100, max(1, limit))
    offset = (page - 1) * limit

    total = int(
        db.execute(
            text(
                "SELECT COUNT(*) FROM bookings b "
                "WHERE b.caretaker_user_id = :cid AND b.status = 'pending'"
            ),
            {"cid": int(caretaker_user_id)},
        ).scalar()
        or 0
    )

    rows = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "       b.address, b.status, b.request_priority, b.created_at, "
            "       p.patient_name, p.care_type "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE b.caretaker_user_id = :cid "
            "  AND b.status = 'pending' "
            "ORDER BY b.created_at DESC, b.id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"cid": int(caretaker_user_id), "limit": limit, "offset": offset},
    ).mappings().all()

    requests = [care_request_list_item(dict(r)) for r in rows]

    return {
        "requests": requests,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": int(math.ceil(total / limit)) if limit > 0 else 0,
        },
    }


def get_caretaker_request_detail(
    db: Session,
    caretaker_user_id: int,
    booking_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/booking/caretaker_request_detail L8-128
    """
    touch_caretaker_presence(db, caretaker_user_id)

    row = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "       b.address, b.notes, b.status, b.request_priority, b.location_latitude, b.location_longitude, "
            "       b.total_hours, b.caretaker_earning_amount, b.created_at, "
            "       p.patient_name, p.age, p.gender, p.medical_condition, p.special_instructions, p.mobility_status, p.care_type, "
            "       u.username AS family_username "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "LEFT JOIN users u ON u.id = b.family_user_id "
            "WHERE b.id = :bid "
            "  AND b.caretaker_user_id = :cid "
            "LIMIT 1"
        ),
        {"bid": int(booking_id), "cid": int(caretaker_user_id)},
    ).mappings().first()

    if not row:
        raise APIException(
            message="Booking request not found",
            status_code=404,
        )

    r = dict(row)
    is_pending = str(r.get("status") or "").lower() == "pending"
    start = care_request_time(r.get("start_time"))
    end = care_request_time(r.get("end_time"))
    coords = care_request_parse_coordinates(r)

    tasks_rows = db.execute(
        text(
            "SELECT id, title, description, status "
            "FROM booking_checklist_tasks "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": int(booking_id)},
    ).mappings().all()

    care_tasks = [
        {
            "task_id": int(t["id"]),
            "title": care_request_text(t.get("title") or ""),
            "description": care_request_text(t.get("description") or ""),
            "status": str(care_request_text(t.get("status") or "pending")).lower(),
        }
        for t in tasks_rows
    ]

    reasons = care_request_decline_reasons()

    return {
        "request_id": int(r["booking_id"]),
        "booking_id": int(r["booking_id"]),
        "booking": {
            "booking_id": int(r["booking_id"]),
            "request_id": int(r["booking_id"]),
            "status": str(care_request_text(r.get("status") or "")).lower(),
            "service_type": care_request_text(r.get("service_type") or ""),
            "care_type": care_request_text(r.get("care_type") or ""),
            "visit_date": care_request_date(r.get("booking_date")),
            "start_time": start,
            "end_time": end,
            "display_time": care_request_display_time(start, end),
            "location_short": care_request_location_short(r.get("address")),
            "address": care_request_text(r.get("address") or ""),
            "notes": care_request_text(r.get("notes") or ""),
            "priority": care_request_priority(r),
            "is_urgent": care_request_priority(r) == "urgent",
            "total_hours": float(r.get("total_hours") or 0),
            "earning_amount": float(r.get("caretaker_earning_amount") or 0),
            "created_at": care_request_datetime(r.get("created_at")),
        },
        "patient": {
            "patient_name": care_request_text(r.get("patient_name") or ""),
            "elder_name": care_request_text(r.get("patient_name") or ""),
            "age": int(r["age"]) if r.get("age") is not None else 0,
            "gender": care_request_text(r.get("gender") or ""),
            "condition": care_request_text(r.get("medical_condition") or ""),
            "mobility_status": care_request_text(r.get("mobility_status") or ""),
            "care_type": care_request_text(r.get("care_type") or ""),
        },
        "visit": {
            "location": care_request_location_short(r.get("address")),
            "address": care_request_text(r.get("address") or ""),
            "date": care_request_date(r.get("booking_date")),
            "start_time": start,
            "end_time": end,
            "display_time": care_request_display_time(start, end),
            "service": care_request_text(r.get("service_type") or ""),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
        },
        "care_tasks": care_tasks,
        "special_instructions": care_request_text(r.get("special_instructions") or ""),
        "family": {
            "username": care_request_text(r.get("family_username") or ""),
        },
        "actions": {
            "can_accept": is_pending,
            "can_decline": is_pending,
            "respond_endpoint": "/api/v1/booking/respond_request",
            "decline_reasons": [
                {"code": k, "label": v} for k, v in reasons.items()
            ],
        },
        "enums": {
            "booking_status": ["pending", "accepted", "in_progress", "completed", "declined", "cancelled"],
            "request_action": ["accept", "decline"],
            "decline_reason_code": list(reasons.keys()),
            "priority": ["normal", "high", "urgent"],
        },
    }


def get_caretaker_booking_detail(
    db: Session,
    caretaker_user_id: int,
    booking_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/caretaker/booking_detail L8-92
    """
    touch_caretaker_presence(db, caretaker_user_id)

    row = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "       b.address, b.notes, b.status, b.payment_status, b.payout_status, "
            "       b.caretaker_earning_amount, b.completed_at, "
            "       p.patient_name, "
            "       vt.id AS visit_id, vt.check_in_time, vt.check_out_time, "
            "       latest_otp.used_at AS visit_otp_verified_at, "
            "       latest_otp.expires_at AS visit_otp_expires_at "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "LEFT JOIN visit_tracking vt "
            "  ON vt.booking_id = b.id "
            " AND vt.caretaker_user_id = b.caretaker_user_id "
            "LEFT JOIN ( "
            "    SELECT booking_id, MAX(used_at) AS used_at, MAX(expires_at) AS expires_at "
            "    FROM otp_codes "
            "    WHERE purpose = 'visit_start' "
            "    GROUP BY booking_id "
            ") latest_otp ON latest_otp.booking_id = b.id "
            "WHERE b.id = :bid "
            "  AND b.caretaker_user_id = :cid "
            "LIMIT 1"
        ),
        {"bid": int(booking_id), "cid": int(caretaker_user_id)},
    ).mappings().first()

    if not row:
        raise APIException(
            message="Booking not found",
            status_code=404,
        )

    b = dict(row)
    status = str(b.get("status") or "").lower()
    verified_at = b.get("visit_otp_verified_at")
    visit_otp_state = "not_required"
    if status == "accepted":
        visit_otp_state = "verified" if verified_at else "required"

    st_str = str(b["start_time"]) if b.get("start_time") else None
    et_str = str(b["end_time"]) if b.get("end_time") else None
    visit_label = care_request_display_time(st_str, et_str) if (st_str and et_str) else None

    cin_time = str(b["check_in_time"]) if b.get("check_in_time") else None
    cout_time = str(b["check_out_time"]) if b.get("check_out_time") else None
    is_active = (status == "in_progress" and cin_time is not None and cout_time is None)

    return {
        "booking_id": int(b["booking_id"]),
        "patient_name": b.get("patient_name"),
        "service_type": b.get("service_type"),
        "booking_date": str(b["booking_date"]) if b.get("booking_date") else None,
        "start_time": st_str,
        "end_time": et_str,
        "visit_label": visit_label,
        "address": b.get("address"),
        "notes": b.get("notes"),
        "status": b.get("status"),
        "payment_status": b.get("payment_status"),
        "payout_status": b.get("payout_status"),
        "earning_amount": float(b.get("caretaker_earning_amount") or 0),
        "completed_at": str(b["completed_at"]) if b.get("completed_at") else None,
        "visit": {
            "visit_id": int(b["visit_id"]) if b.get("visit_id") else None,
            "check_in_time": cin_time,
            "check_out_time": cout_time,
            "is_active": is_active,
        },
        "visit_otp": {
            "state": visit_otp_state,
            "verified_at": str(verified_at) if verified_at else None,
            "expires_at": str(b["visit_otp_expires_at"]) if b.get("visit_otp_expires_at") else None,
        },
        "actions": {
            "can_accept": status == "pending",
            "can_verify_otp": status == "accepted",
            "can_check_in": status == "accepted" and visit_otp_state == "verified",
            "can_check_out": status == "in_progress",
            "can_raise_sos": status in ("accepted", "in_progress"),
        },
    }


def get_legacy_caretaker_requests(
    db: Session,
    caretaker_user_id: int,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/caretaker/requests L8-68
    Legacy flat pagination contract for caretaker requests.
    """
    touch_caretaker_presence(db, caretaker_user_id)

    page = max(1, page)
    limit = min(100, max(1, limit))
    offset = (page - 1) * limit

    total = int(
        db.execute(
            text(
                "SELECT COUNT(*) FROM bookings "
                "WHERE caretaker_user_id = :cid AND status = 'pending'"
            ),
            {"cid": int(caretaker_user_id)},
        ).scalar()
        or 0
    )

    rows = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "       b.address, b.status, b.created_at, p.patient_name "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE b.caretaker_user_id = :cid "
            "  AND b.status = 'pending' "
            "ORDER BY b.created_at DESC, b.id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"cid": int(caretaker_user_id), "limit": limit, "offset": offset},
    ).mappings().all()

    items: List[Dict[str, Any]] = []
    for r in rows:
        st = str(r["start_time"]) if r.get("start_time") else None
        et = str(r["end_time"]) if r.get("end_time") else None
        v_label = care_request_display_time(st, et) if (st and et) else None

        items.append({
            "booking_id": int(r["booking_id"]),
            "patient_name": r.get("patient_name"),
            "service_type": r.get("service_type"),
            "booking_date": str(r["booking_date"]) if r.get("booking_date") else None,
            "start_time": st,
            "end_time": et,
            "visit_label": v_label,
            "address": r.get("address"),
            "status": r.get("status"),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
        })

    return {
        "requests": items,
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": int(math.ceil(total / limit)) if limit > 0 else 0,
    }


def get_admin_bookings(
    db: Session,
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/bookings L8-116
    """
    page = max(1, page)
    limit = min(100, max(1, limit))
    offset = (page - 1) * limit

    params: Dict[str, Any] = {}
    where = ""

    if status and status.strip():
        st = status.strip().lower()
        if st not in ("pending", "accepted", "declined", "in_progress", "completed", "cancelled"):
            raise APIException(
                message="Invalid booking status",
                status_code=400,
            )
        where = "WHERE b.status = :status"
        params["status"] = st

    count_sql = f"SELECT COUNT(*) FROM bookings b {where}"
    total = int(db.execute(text(count_sql), params).scalar() or 0)

    query_sql = f"""
        SELECT b.id, b.id AS booking_id, CONCAT('#', b.id) AS formatted_booking_id,
               CONCAT('#', b.id) AS booking_code,
               b.family_user_id, b.caretaker_user_id, b.patient_id,
               b.service_type, b.booking_date, b.start_time, b.end_time, b.address,
               b.location_latitude, b.location_longitude, b.notes, b.request_priority,
               b.status, b.cancelled_by, b.cancellation_reason, b.decline_reason_code,
               b.decline_reason_label, b.decline_note, b.responded_at, b.cancelled_at,
               b.total_amount, b.pricing_tier_id, b.pricing_tier, b.skill_level,
               b.customer_hourly_rate, b.caretaker_hourly_rate, b.platform_commission_hourly,
               b.total_customer_amount, b.caretaker_earning_amount, b.platform_commission_amount,
               b.care_points_earned, b.total_hours, b.payment_status, b.created_at,
               b.updated_at, b.completed_at, b.payout_status, b.payout_hold_until,
               b.payout_paid_at, b.payout_id, b.paid_amount, b.remaining_amount,
               p.patient_name,
               fp.city AS family_city,
               COALESCE(fp.city, cp.city) AS city,
               fu.username AS family_username,
               fu.email AS family_email,
               fu.phone_number AS family_phone,
               COALESCE(fp.full_name, fu.username, fu.email, fu.phone_number) AS family_name,
               cu.username AS caretaker_username,
               cu.email AS caretaker_email,
               cu.phone_number AS caretaker_phone,
               COALESCE(cp.full_name, cu.username, cu.email, cu.phone_number) AS caretaker_name,
               COALESCE(cp.full_name, cu.username, cu.email, cu.phone_number) AS caregiver_name,
               cu.phone_number AS caregiver_phone,
               vt.id AS visit_id,
               vt.check_in_time AS checked_in_at,
               vt.check_out_time AS checked_out_at,
               vt.check_in_time,
               vt.check_out_time,
               CASE
                 WHEN vt.check_in_time IS NOT NULL AND vt.check_out_time IS NULL THEN 'in_progress'
                 WHEN vt.check_out_time IS NOT NULL THEN 'completed'
                 ELSE b.status
               END AS visit_status,
               CASE
                 WHEN vt.check_in_time IS NOT NULL AND vt.check_out_time IS NULL
                   THEN ROUND(TIMESTAMPDIFF(MINUTE, vt.check_in_time, NOW()) / 60, 2)
                 WHEN vt.check_in_time IS NOT NULL AND vt.check_out_time IS NOT NULL
                   THEN ROUND(TIMESTAMPDIFF(MINUTE, vt.check_in_time, vt.check_out_time) / 60, 2)
                 ELSE b.total_hours
               END AS duration_hours,
               (SELECT COUNT(*) FROM sos_alerts s WHERE s.booking_id = b.id AND s.status = 'open') AS active_sos_count,
               (SELECT s.status FROM sos_alerts s WHERE s.booking_id = b.id ORDER BY s.id DESC LIMIT 1) AS latest_sos_status
        FROM bookings b
        LEFT JOIN patient_details p ON p.id = b.patient_id
        LEFT JOIN users fu ON fu.id = b.family_user_id
        LEFT JOIN family_profiles fp ON fp.user_id = b.family_user_id
        LEFT JOIN users cu ON cu.id = b.caretaker_user_id
        LEFT JOIN caretaker_profiles cp ON cp.user_id = b.caretaker_user_id
        LEFT JOIN visit_tracking vt
          ON vt.booking_id = b.id
         AND vt.caretaker_user_id = b.caretaker_user_id
         AND (vt.check_out_time IS NULL OR b.status = 'in_progress')
         AND vt.id = (
            SELECT MAX(vt2.id)
            FROM visit_tracking vt2
            WHERE vt2.booking_id = b.id
              AND vt2.caretaker_user_id = b.caretaker_user_id
         )
        {where}
        ORDER BY b.id DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    rows = db.execute(text(query_sql), params).mappings().all()
    items: List[Dict[str, Any]] = []

    for r in rows:
        item = dict(r)
        # Format dates / times
        for k in ("created_at", "updated_at", "completed_at", "responded_at", "cancelled_at", "payout_hold_until", "payout_paid_at", "checked_in_at", "checked_out_at", "check_in_time", "check_out_time"):
            if k in item and item[k] is not None:
                item[k] = str(item[k])
        if "booking_date" in item and item["booking_date"] is not None:
            item["booking_date"] = str(item["booking_date"])
        if "start_time" in item and item["start_time"] is not None:
            item["start_time"] = str(item["start_time"])
        if "end_time" in item and item["end_time"] is not None:
            item["end_time"] = str(item["end_time"])

        # Decimal to float
        for k in (
            "total_amount", "customer_hourly_rate", "caretaker_hourly_rate",
            "platform_commission_hourly", "total_customer_amount",
            "caretaker_earning_amount", "platform_commission_amount",
            "total_hours", "paid_amount", "remaining_amount"
        ):
            if k in item and item[k] is not None:
                item[k] = float(item[k])

        # L100-108 computed attributes
        item["booking_status"] = item.get("status")
        active_sos = int(item.get("active_sos_count") or 0)
        item["has_sos"] = active_sos > 0
        item["sos_count"] = active_sos
        item["active_sos_count"] = active_sos
        item["duration_hours"] = float(item["duration_hours"]) if item.get("duration_hours") is not None else None
        item["started_at"] = item.get("checked_in_at") or item.get("start_time")

        items.append(item)

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": int(math.ceil(total / limit)) if limit > 0 else 0,
        "items": items,
    }


def get_admin_booking_detail(
    db: Session,
    booking_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/booking_detail L13-188
    Full 360-degree booking aggregation.
    """
    row = db.execute(
        text(
            "SELECT b.id AS booking_id, b.family_user_id, b.caretaker_user_id, b.patient_id, "
            "       b.service_type, b.booking_date, b.start_time, b.end_time, b.address, "
            "       b.location_latitude, b.location_longitude, b.notes, b.request_priority, "
            "       b.status, b.cancelled_by, b.cancellation_reason, b.decline_reason_code, "
            "       b.decline_reason_label, b.decline_note, b.responded_at, b.cancelled_at, "
            "       b.cancelled_by_user_id, b.cancelled_by_role, b.cancel_reason_code, "
            "       b.cancel_reason_label, b.cancel_note, b.refund_eligible, b.refund_percentage, "
            "       b.refund_amount, b.refund_status, b.cancellation_fee, "
            "       b.total_amount, b.pricing_tier_id, b.pricing_tier, b.skill_level, "
            "       b.customer_hourly_rate, b.caretaker_hourly_rate, b.platform_commission_hourly, "
            "       b.total_customer_amount, b.caretaker_earning_amount, b.platform_commission_amount, "
            "       b.care_points_earned, b.total_hours, b.payment_status, b.created_at, "
            "       b.updated_at, b.completed_at, b.payout_status, b.payout_hold_until, "
            "       b.payout_paid_at, b.payout_id, b.paid_amount, b.remaining_amount, "
            "       p.patient_name, p.age AS patient_age, p.gender AS patient_gender, "
            "       p.medical_condition, p.allergies, p.medications, p.special_instructions, "
            "       p.mobility_status, p.care_type, "
            "       fu.username AS family_username, fu.email AS family_email, fu.phone_number AS family_phone, "
            "       fp.full_name AS family_name, "
            "       cu.username AS caretaker_username, cu.email AS caretaker_email, cu.phone_number AS caretaker_phone, "
            "       cp.full_name AS caretaker_name, "
            "       cp.full_name AS caregiver_name, "
            "       cp.rating AS caretaker_rating, "
            "       cp.pricing_tier AS caretaker_tier, "
            "       po.status AS payout_batch_status, "
            "       po.created_at AS payout_created_at, "
            "       po.settled_at AS payout_processed_at, "
            "       po.admin_note AS payout_admin_note, "
            "       po.admin_note AS failure_reason "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "LEFT JOIN users fu ON fu.id = b.family_user_id "
            "LEFT JOIN family_profiles fp ON fp.user_id = b.family_user_id "
            "LEFT JOIN users cu ON cu.id = b.caretaker_user_id "
            "LEFT JOIN caretaker_profiles cp ON cp.user_id = b.caretaker_user_id "
            "LEFT JOIN caretaker_payouts po ON po.id = b.payout_id "
            "WHERE b.id = :bid "
            "LIMIT 1"
        ),
        {"bid": int(booking_id)},
    ).mappings().first()

    if not row:
        raise APIException(
            message="Booking not found",
            status_code=404,
        )

    booking = dict(row)

    # Sub-queries
    payments_rows = db.execute(
        text(
            "SELECT id, booking_id, family_user_id, caretaker_user_id, amount, payment_method, "
            "       transaction_id, status, paid_at, created_at, payment_type, total_amount, "
            "       remaining_amount "
            "FROM payments "
            "WHERE booking_id = :bid "
            "ORDER BY id DESC"
        ),
        {"bid": int(booking_id)},
    ).mappings().all()

    visits_rows = db.execute(
        text(
            "SELECT id, booking_id, caretaker_user_id, check_in_time, check_out_time, "
            "       check_in_lat, check_in_lng, check_out_lat, check_out_lng, notes, created_at "
            "FROM visit_tracking "
            "WHERE booking_id = :bid "
            "ORDER BY id DESC"
        ),
        {"bid": int(booking_id)},
    ).mappings().all()

    tasks_rows = db.execute(
        text(
            "SELECT id, booking_id, family_user_id, caretaker_user_id, title, description, "
            "       status, completed_by, completed_at, created_at, updated_at "
            "FROM booking_checklist_tasks "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": int(booking_id)},
    ).mappings().all()

    complaints_rows = db.execute(
        text(
            "SELECT id, booking_id, family_user_id, caretaker_user_id, subject, description, "
            "       proof_file, status, admin_note, resolved_by, resolved_at, created_at, updated_at "
            "FROM complaints "
            "WHERE booking_id = :bid "
            "ORDER BY id DESC"
        ),
        {"bid": int(booking_id)},
    ).mappings().all()

    sos_rows = db.execute(
        text(
            "SELECT id, user_id, booking_id, message, latitude, longitude, status, created_at "
            "FROM sos_alerts "
            "WHERE booking_id = :bid "
            "ORDER BY id DESC"
        ),
        {"bid": int(booking_id)},
    ).mappings().all()

    payment_summary_row = db.execute(
        text(
            "SELECT COALESCE(SUM(CASE WHEN status = 'success' THEN amount ELSE 0 END), 0) AS successful_paid_amount, "
            "       COUNT(CASE WHEN status = 'success' THEN 1 END) AS successful_payment_count "
            "FROM payments "
            "WHERE booking_id = :bid"
        ),
        {"bid": int(booking_id)},
    ).mappings().first() or {}

    refund_row = db.execute(
        text(
            "SELECT id, booking_id, family_user_id, caretaker_user_id, payment_id, "
            "       paid_amount, refund_percentage, refund_amount, status, reason, "
            "       refund_method, refund_transaction_id, approved_at, rejected_at, "
            "       processed_at, created_at, updated_at "
            "FROM booking_refunds "
            "WHERE booking_id = :bid "
            "ORDER BY id DESC "
            "LIMIT 1"
        ),
        {"bid": int(booking_id)},
    ).mappings().first()

    successful_paid_amount = float(refund_format_money(payment_summary_row.get("successful_paid_amount") or 0))
    tot_cust = float(booking.get("total_customer_amount") or booking.get("total_amount") or 0)
    current_paid = float(refund_format_money(booking.get("paid_amount") or 0))
    paid_amt = max(current_paid, successful_paid_amount)
    rem_amt = float(refund_format_money(max(0, tot_cust - paid_amt)))

    booking["paid_amount"] = paid_amt
    booking["remaining_amount"] = rem_amt
    booking["refund_eligible"] = bool(booking.get("refund_eligible"))
    booking["refund_percentage"] = float(refund_format_money(booking.get("refund_percentage") or 0))
    booking["refund_amount"] = float(refund_format_money(booking.get("refund_amount") or 0))
    booking["cancellation_fee"] = float(refund_format_money(booking.get("cancellation_fee") or 0))
    booking["successful_paid_amount"] = successful_paid_amount
    booking["successful_payment_count"] = int(payment_summary_row.get("successful_payment_count") or 0)
    booking["refund_warning"] = None
    booking["booking_status"] = booking.get("status")
    booking["status"] = booking.get("payout_status") or booking.get("status")

    caretaker_name = booking.get("caretaker_name") or booking.get("caretaker_username")
    booking["caretaker_name"] = caretaker_name
    booking["caregiver_name"] = caretaker_name
    booking["family_name"] = booking.get("family_name") or booking.get("family_username")
    booking["caretaker_earning"] = float(booking["caretaker_earning_amount"]) if booking.get("caretaker_earning_amount") is not None else None
    booking["hold_until"] = str(booking["payout_hold_until"]) if booking.get("payout_hold_until") else None
    booking["paid_at"] = str(booking["payout_paid_at"]) if booking.get("payout_paid_at") else None
    booking["booking_completed_at"] = str(booking["completed_at"]) if booking.get("completed_at") else None

    # Stringify dates / Decimals
    for k in (
        "booking_date", "start_time", "end_time", "created_at", "updated_at",
        "completed_at", "responded_at", "cancelled_at", "payout_created_at",
        "payout_processed_at"
    ):
        if k in booking and booking[k] is not None:
            booking[k] = str(booking[k])

    for k in (
        "total_amount", "customer_hourly_rate", "caretaker_hourly_rate",
        "platform_commission_hourly", "total_customer_amount",
        "caretaker_earning_amount", "platform_commission_amount",
        "total_hours", "caretaker_rating"
    ):
        if k in booking and booking[k] is not None:
            booking[k] = float(booking[k])

    if refund_row:
        rf = dict(refund_row)
        booking["refund"] = {
            "id": int(rf["id"]),
            "booking_id": int(rf["booking_id"]),
            "payment_id": int(rf["payment_id"]) if rf.get("payment_id") is not None else None,
            "paid_amount": float(refund_format_money(rf.get("paid_amount"))),
            "refund_percentage": float(refund_format_money(rf.get("refund_percentage"))),
            "refund_amount": float(refund_format_money(rf.get("refund_amount"))),
            "status": rf.get("status"),
            "reason": rf.get("reason"),
            "refund_method": rf.get("refund_method"),
            "refund_transaction_id": rf.get("refund_transaction_id"),
            "approved_at": refund_iso(rf.get("approved_at")),
            "rejected_at": refund_iso(rf.get("rejected_at")),
            "processed_at": refund_iso(rf.get("processed_at")),
            "created_at": refund_iso(rf.get("created_at")),
            "updated_at": refund_iso(rf.get("updated_at")),
        }
    else:
        booking["refund"] = None
        if str(booking.get("status")) == "cancelled" and successful_paid_amount > 0:
            booking["refund_warning"] = "Refund record missing for cancelled paid booking"

    payments = [dict(p) for p in payments_rows]
    for p in payments:
        for k in ("paid_at", "created_at"):
            if k in p and p[k] is not None:
                p[k] = str(p[k])
        for k in ("amount", "total_amount", "remaining_amount"):
            if k in p and p[k] is not None:
                p[k] = float(p[k])

    visits = [dict(v) for v in visits_rows]
    for v in visits:
        for k in ("check_in_time", "check_out_time", "created_at"):
            if k in v and v[k] is not None:
                v[k] = str(v[k])

    checklist_tasks = [dict(t) for t in tasks_rows]
    for t in checklist_tasks:
        for k in ("completed_at", "created_at", "updated_at"):
            if k in t and t[k] is not None:
                t[k] = str(t[k])

    complaints = [dict(c) for c in complaints_rows]
    for c in complaints:
        for k in ("resolved_at", "created_at", "updated_at"):
            if k in c and c[k] is not None:
                c[k] = str(c[k])

    sos_alerts = [dict(s) for s in sos_rows]
    for s in sos_alerts:
        for k in ("created_at",):
            if k in s and s[k] is not None:
                s[k] = str(s[k])

    booking["payments"] = payments
    booking["visits"] = visits
    booking["checklist_tasks"] = checklist_tasks
    booking["complaints"] = complaints
    booking["sos_alerts"] = sos_alerts
    booking["complaint_count"] = len(complaints)
    booking["dispute_count"] = len([
        c for c in complaints if str(c.get("status") or "") in ("open", "in_review")
    ])
    booking["sos_count"] = len(sos_alerts)

    p_status = booking.get("payout_status")
    failure_reason = booking.get("failure_reason")
    if p_status == "hold":
        booking["hold_reason"] = "24-hour completion hold is active"
    elif p_status == "disputed":
        booking["hold_reason"] = "Complaint, SOS, checklist, or refund review blocks payout"
    else:
        booking["hold_reason"] = failure_reason or None

    return booking


def generate_visit_otp(
    db: Session,
    family_user_id: int,
    booking_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/booking/visit_otp L16-72
    """
    row = db.execute(
        text(
            "SELECT id, status "
            "FROM bookings "
            "WHERE id = :bid AND family_user_id = :fuid AND status IN ('accepted','in_progress') "
            "LIMIT 1"
        ),
        {"bid": int(booking_id), "fuid": int(family_user_id)},
    ).fetchone()

    if not row:
        raise APIException(
            message="Active accepted booking not found",
            status_code=404,
        )

    latest = otp_latest(db, "visit_start", {"booking_id": int(booking_id)})
    latest_meta = {}
    if latest and latest.get("metadata"):
        import json
        try:
            latest_meta = json.loads(latest["metadata"]) if isinstance(latest["metadata"], str) else latest["metadata"]
        except Exception:
            latest_meta = {}

    if (
        isinstance(latest_meta, dict)
        and latest_meta.get("source") == "family_visible"
        and not otp_can_resend(db, "visit_start", {"booking_id": int(booking_id)})
    ):
        raise APIException(
            message="Please wait before regenerating visit OTP",
            errors={"otp": ["Please wait before requesting another visit OTP"]},
            status_code=429,
        )

    otp_data = otp_create(
        db=db,
        purpose="visit_start",
        options={
            "booking_id": int(booking_id),
            "expiry_seconds": 900,
            "cooldown_seconds": 60,
            "metadata": {"source": "family_visible"},
        },
    )

    create_notification(
        db=db,
        user_id=int(family_user_id),
        title="Visit OTP generated",
        message="A visit start OTP was generated for your booking.",
        notification_type="otp_generated",
        related_type="booking",
        related_id=int(booking_id),
        metadata={"booking_id": int(booking_id), "purpose": "visit_start"},
    )

    return {
        "booking_id": int(booking_id),
        "visit_start_otp": otp_data["code"],
        "otp_expires_in": otp_data["expires_in"],
        "resend_cooldown": otp_data["resend_cooldown"],
    }

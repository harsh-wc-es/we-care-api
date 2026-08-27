"""
WeCare — Emergency SOS Service

Complete implementation of the SOS domain business logic mirroring Route: - api/v1/sos/create_sos
- api/v1/sos/create
- api/v1/sos/my_sos
- api/v1/sos/resolve_sos
- api/v1/sos/update_status
- api/v1/sos/admin_sos_list
- api/v1/admin/sos_detail
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.audit_service import audit_log
from app.services.notification_service import notify_sos_created
from app.services.rate_limit_service import enforce_rate_limit
from app.services.visit_service import visit_live_log


def _get_user_id(user: Any) -> int:
    """Extracts integer user ID from dict or User model."""
    if isinstance(user, dict):
        return int(user["id"])
    return int(user.id)


def _get_user_role(user: Any) -> str:
    """Extracts string role from dict or User model."""
    if isinstance(user, dict):
        role_val = user.get("role")
        if hasattr(role_val, "value"):
            return str(role_val.value)
        return str(role_val)
    if hasattr(user, "role"):
        if hasattr(user.role, "value"):
            return str(user.role.value)
        return str(user.role)
    return ""


def _format_dt(val: Any) -> Optional[str]:
    """Formats datetime values to standard string representation matching FastAPI."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def _format_date(val: Any) -> Optional[str]:
    """Formats date values to standard string."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    return str(val)


def _format_time(val: Any) -> Optional[str]:
    """Formats time values to standard string."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%H:%M:%S")
    return str(val)


def create_sos_alert(
    db: Session,
    user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/sos/create_sos
    Triggers SOS alert for family, caretaker, or admin with booking validation,
    rate limiting, visit activity logging, audit logging, and notifications.
    """
    user_id = _get_user_id(user)
    user_role = _get_user_role(user)

    booking_id = data.get("booking_id")
    raw_message = data.get("message")
    message = str(raw_message).strip() if raw_message is not None else ""
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    enforce_rate_limit(db, "create_sos", str(user_id), 5, 900, 900)

    if not message:
        raise APIException(
            "Validation failed",
            status_code=400,
            errors={"message": ["Message is required"]},
        )

    booking_id_int: Optional[int] = None
    if booking_id is not None and str(booking_id).strip() != "":
        try:
            booking_id_int = int(booking_id)
        except (ValueError, TypeError):
            raise APIException(
                "Validation failed",
                status_code=400,
                errors={"booking_id": ["Booking id must be an integer"]},
            )

        if user_role == "family":
            b_row = db.execute(
                text(
                    "SELECT id, family_user_id, caretaker_user_id, status "
                    "FROM bookings WHERE id = :bid AND family_user_id = :uid"
                ),
                {"bid": booking_id_int, "uid": user_id},
            ).fetchone()
        elif user_role == "caretaker":
            b_row = db.execute(
                text(
                    "SELECT id, family_user_id, caretaker_user_id, status "
                    "FROM bookings WHERE id = :bid AND caretaker_user_id = :uid "
                    "AND status IN ('accepted','in_progress')"
                ),
                {"bid": booking_id_int, "uid": user_id},
            ).fetchone()
        else:  # admin or other
            b_row = db.execute(
                text(
                    "SELECT id, family_user_id, caretaker_user_id, status "
                    "FROM bookings WHERE id = :bid"
                ),
                {"bid": booking_id_int},
            ).fetchone()

        if not b_row:
            raise APIException("Booking not found for this user", status_code=404)

    db.execute(
        text(
            "INSERT INTO sos_alerts (user_id, booking_id, message, latitude, longitude, status) "
            "VALUES (:user_id, :booking_id, :message, :latitude, :longitude, 'open')"
        ),
        {
            "user_id": user_id,
            "booking_id": booking_id_int,
            "message": message,
            "latitude": str(latitude) if latitude is not None else None,
            "longitude": str(longitude) if longitude is not None else None,
        },
    )
    sos_id_val = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()
    sos_id = int(sos_id_val)

    if booking_id_int is not None:
        v_row = db.execute(
            text(
                "SELECT id FROM visit_tracking WHERE booking_id = :bid "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"bid": booking_id_int},
        ).fetchone()
        visit_id = int(v_row.id) if v_row and getattr(v_row, "id", None) else None

        visit_live_log(
            db=db,
            booking_id=booking_id_int,
            visit_id=visit_id,
            actor_user_id=user_id,
            actor_role=user_role,
            activity_type="sos_created",
            message="SOS alert created during visit",
            metadata={
                "sos_id": sos_id,
                "latitude": str(latitude) if latitude is not None else None,
                "longitude": str(longitude) if longitude is not None else None,
            },
        )

        audit_log(
            db=db,
            admin_user_id=user_id,
            action="sos_created",
            entity_type="sos_alert",
            entity_id=sos_id,
            old_values=None,
            new_values={
                "booking_id": booking_id_int,
                "message": message,
                "status": "open",
            },
        )


        notify_sos_created(db, sos_id)

    db.commit()

    return {
        "sos_id": sos_id,
        "booking_id": booking_id_int,
        "status": "open",
    }


def create_caretaker_sos(
    db: Session,
    user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/sos/create
    Caretaker-specific fast trigger for accepted/in_progress bookings.
    """
    user_id = _get_user_id(user)
    booking_id = data.get("booking_id")
    raw_message = data.get("message")
    message = str(raw_message).strip() if raw_message is not None else ""
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    enforce_rate_limit(db, "create_sos", str(user_id), 5, 900, 900)

    if booking_id is None or str(booking_id).strip() == "":
        raise APIException(
            "Valid booking id is required",
            status_code=400,
            errors={"booking_id": ["Booking id must be an integer"]},
        )

    try:
        booking_id_int = int(booking_id)
    except (ValueError, TypeError):
        raise APIException(
            "Valid booking id is required",
            status_code=400,
            errors={"booking_id": ["Booking id must be an integer"]},
        )

    if booking_id_int <= 0:
        raise APIException(
            "Valid booking id is required",
            status_code=400,
            errors={"booking_id": ["Booking id must be an integer"]},
        )

    if message == "":
        raise APIException(
            "Message is required",
            status_code=400,
            errors={"message": ["Message is required"]},
        )

    b_row = db.execute(
        text(
            "SELECT id, status FROM bookings "
            "WHERE id = :bid AND caretaker_user_id = :cid "
            "  AND status IN ('accepted','in_progress') "
            "LIMIT 1"
        ),
        {"bid": booking_id_int, "cid": user_id},
    ).fetchone()

    if not b_row:
        raise APIException(
            "Assigned active booking not found",
            status_code=404,
            errors={
                "booking_id": [
                    "SOS can only be created for an assigned accepted or in-progress booking"
                ]
            },
        )

    db.execute(
        text(
            "INSERT INTO sos_alerts (user_id, booking_id, message, latitude, longitude, status) "
            "VALUES (:user_id, :booking_id, :message, :latitude, :longitude, 'open')"
        ),
        {
            "user_id": user_id,
            "booking_id": booking_id_int,
            "message": message,
            "latitude": str(latitude) if latitude is not None else None,
            "longitude": str(longitude) if longitude is not None else None,
        },
    )
    sos_id_val = db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar()
    sos_id = int(sos_id_val)
    db.commit()

    return {
        "sos_id": sos_id,
        "booking_id": booking_id_int,
        "status": "open",
    }


def get_user_sos_list(
    db: Session,
    user: Any,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/sos/my_sos
    Retrieves paginated SOS alerts created by the authenticated user.
    """
    user_id = _get_user_id(user)
    page = max(1, int(page))
    limit = min(100, max(1, int(limit)))
    offset = (page - 1) * limit

    count_row = db.execute(
        text("SELECT COUNT(*) AS total FROM sos_alerts WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchone()
    total = int(count_row.total) if count_row else 0

    rows = db.execute(
        text(
            "SELECT id, user_id, booking_id, message, latitude, longitude, status, created_at "
            "FROM sos_alerts "
            "WHERE user_id = :uid "
            "ORDER BY id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"uid": user_id, "limit": limit, "offset": offset},
    ).fetchall()

    items = []
    for r in rows:
        items.append({
            "id": int(r.id),
            "user_id": int(r.user_id),
            "booking_id": int(r.booking_id) if r.booking_id is not None else None,
            "message": r.message,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "status": str(r.status.value if hasattr(r.status, "value") else r.status),
            "created_at": _format_dt(r.created_at),
        })

    total_pages = math.ceil(total / limit) if limit > 0 else 1

    return {
        "items": items,
        "sos_alerts": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
        },
    }


def resolve_sos_alert(
    db: Session,
    admin_user: Any,
    sos_id: Optional[Union[int, str]],
) -> None:
    """
    Route: api/v1/sos/resolve_sos
    Quickly resolves an SOS alert.
    """
    if sos_id is None or str(sos_id).strip() == "":
        raise APIException("SOS id is required", status_code=400)

    try:
        sos_id_int = int(sos_id)
    except (ValueError, TypeError):
        raise APIException("SOS id is required", status_code=400)

    res = db.execute(
        text("UPDATE sos_alerts SET status = 'resolved' WHERE id = :sid"),
        {"sid": sos_id_int},
    )

    if res.rowcount == 0:
        raise APIException("SOS alert not found", status_code=404)

    db.commit()


def update_sos_status(
    db: Session,
    admin_user: Any,
    sos_id: Optional[Union[int, str]],
    status: Optional[str],
) -> None:
    """
    Route: api/v1/sos/update_status
    Updates status of an SOS alert with admin audit logging.
    """
    admin_id = _get_user_id(admin_user)

    if sos_id is None or str(sos_id).strip() == "":
        raise APIException("SOS id and valid status are required", status_code=400)

    try:
        sos_id_int = int(sos_id)
    except (ValueError, TypeError):
        raise APIException("SOS id and valid status are required", status_code=400)

    status_str = str(status).strip().lower() if status is not None else ""
    if status_str not in ("open", "resolved"):
        raise APIException("SOS id and valid status are required", status_code=400)

    old_row = db.execute(
        text(
            "SELECT id, user_id, booking_id, message, latitude, longitude, status, created_at "
            "FROM sos_alerts WHERE id = :sid"
        ),
        {"sid": sos_id_int},
    ).fetchone()

    if not old_row:
        raise APIException("SOS alert not found", status_code=404)

    old_dict = {
        "id": int(old_row.id),
        "user_id": int(old_row.user_id),
        "booking_id": int(old_row.booking_id) if old_row.booking_id is not None else None,
        "message": old_row.message,
        "latitude": old_row.latitude,
        "longitude": old_row.longitude,
        "status": str(old_row.status.value if hasattr(old_row.status, "value") else old_row.status),
        "created_at": _format_dt(old_row.created_at),
    }

    db.execute(
        text("UPDATE sos_alerts SET status = :status WHERE id = :sid"),
        {"status": status_str, "sid": sos_id_int},
    )

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_sos_status",
        entity_type="sos_alert",
        entity_id=sos_id_int,
        old_values=old_dict,
        new_values={"status": status_str},
    )


    db.commit()


def get_admin_sos_list(
    db: Session,
    admin_user: Any,
    status: str = "all",
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/sos/admin_sos_list
    Comprehensive admin list of SOS alerts with joins and subquery effective booking.
    """
    status_clean = str(status).strip() if status else "all"
    if status_clean == "":
        status_clean = "all"

    allowed_statuses = ["all", "open", "resolved"]
    if status_clean not in allowed_statuses:
        raise APIException(
            "Invalid SOS status",
            status_code=400,
            errors={"status": ["Allowed values are all, open and resolved"]},
        )

    page = max(1, int(page))
    limit = min(100, max(1, int(limit)))
    offset = (page - 1) * limit

    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    where_sql = ""
    if status_clean != "all":
        where_sql = "WHERE s.status = :status_val"
        params["status_val"] = status_clean

    count_query = f"SELECT COUNT(*) AS total FROM sos_alerts s {where_sql}"
    count_row = db.execute(text(count_query), params).fetchone()
    total = int(count_row.total) if count_row else 0

    effective_booking_sql = """COALESCE(s.booking_id, (
        SELECT b2.id
        FROM bookings b2
        WHERE u.role = 'caretaker'
          AND b2.caretaker_user_id = s.user_id
          AND b2.status = 'in_progress'
        ORDER BY b2.id DESC
        LIMIT 1
    ))"""

    query = f"""
        SELECT s.id, s.id AS sos_id, s.id AS alert_id,
               s.user_id, s.user_id AS reporter_user_id,
               {effective_booking_sql} AS booking_id,
               CONCAT('#', {effective_booking_sql}) AS formatted_booking_id,
               s.message, s.latitude, s.longitude, s.status, s.created_at,
               s.created_at AS triggered_at,
               NULL AS resolved_at,
               NULL AS resolved_by_name,
               CASE
                 WHEN s.latitude IS NOT NULL AND s.latitude <> '' AND s.longitude IS NOT NULL AND s.longitude <> ''
                   THEN CONCAT(s.latitude, ', ', s.longitude)
                 ELSE NULL
               END AS location_text,
               u.email, u.username, u.role,
               u.username AS reporter_username,
               COALESCE(u.username, u.email, u.phone_number) AS reporter_name,
               u.username AS user_name,
               u.username AS raised_by_name,
               u.email AS reporter_email,
               u.role AS reporter_role,
               u.phone_number AS reporter_phone,
               b.status AS booking_status,
               b.booking_date,
               b.start_time,
               b.end_time,
               b.address,
               p.patient_name,
               COALESCE(fp.full_name, fu.username, fu.email, fu.phone_number) AS family_name,
               fu.phone_number AS family_phone,
               b.caretaker_user_id,
               COALESCE(cp.full_name, cu.username, cu.email, cu.phone_number) AS caretaker_name,
               COALESCE(cp.full_name, cu.username, cu.email, cu.phone_number) AS caregiver_name,
               cu.username AS caretaker_username,
               cu.phone_number AS caretaker_phone,
               cu.phone_number AS caregiver_phone,
               cu.email AS caretaker_email
        FROM sos_alerts s
        INNER JOIN users u ON u.id = s.user_id
        LEFT JOIN bookings b ON b.id = {effective_booking_sql}
        LEFT JOIN patient_details p ON p.id = b.patient_id
        LEFT JOIN users fu ON fu.id = b.family_user_id
        LEFT JOIN family_profiles fp ON fp.user_id = b.family_user_id
        LEFT JOIN users cu ON cu.id = b.caretaker_user_id
        LEFT JOIN caretaker_profiles cp ON cp.user_id = b.caretaker_user_id
        {where_sql}
        ORDER BY s.id DESC
        LIMIT :limit OFFSET :offset
    """

    rows = db.execute(text(query), params).fetchall()

    items = []
    for r in rows:
        b_id = getattr(r, "booking_id", None)
        c_id = getattr(r, "caretaker_user_id", None)
        items.append({
            "id": int(r.id),
            "sos_id": int(r.sos_id),
            "alert_id": int(r.alert_id),
            "user_id": int(r.user_id),
            "reporter_user_id": int(r.reporter_user_id),
            "booking_id": int(b_id) if b_id is not None else None,
            "formatted_booking_id": r.formatted_booking_id if b_id is not None else None,
            "message": r.message,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "status": str(r.status.value if hasattr(r.status, "value") else r.status),
            "created_at": _format_dt(r.created_at),
            "triggered_at": _format_dt(r.triggered_at),
            "resolved_at": None,
            "resolved_by_name": None,
            "location_text": r.location_text,
            "email": r.email,
            "username": r.username,
            "role": str(r.role.value if hasattr(r.role, "value") else r.role),
            "reporter_username": r.reporter_username,
            "reporter_name": r.reporter_name,
            "user_name": r.user_name,
            "raised_by_name": r.raised_by_name,
            "reporter_email": r.reporter_email,
            "reporter_role": str(r.reporter_role.value if hasattr(r.reporter_role, "value") else r.reporter_role),
            "reporter_phone": r.reporter_phone,
            "booking_status": str(r.booking_status.value if hasattr(r.booking_status, "value") else r.booking_status) if r.booking_status is not None else None,
            "booking_date": _format_date(r.booking_date),
            "start_time": _format_time(r.start_time),
            "end_time": _format_time(r.end_time),
            "address": r.address,
            "patient_name": r.patient_name,
            "family_name": r.family_name,
            "family_phone": r.family_phone,
            "caretaker_user_id": int(c_id) if c_id is not None else None,
            "caretaker_name": r.caretaker_name,
            "caregiver_name": r.caregiver_name,
            "caretaker_username": r.caretaker_username,
            "caretaker_phone": r.caretaker_phone,
            "caregiver_phone": r.caregiver_phone,
            "caretaker_email": r.caretaker_email,
        })

    total_pages = math.ceil(total / limit) if limit > 0 else 1

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "items": items,
        "alerts": items,
        "sos_alerts": items,
    }


def get_admin_sos_detail(
    db: Session,
    admin_user: Any,
    sos_id: Optional[Union[int, str]],
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/sos_detail
    Detailed individual view of an SOS alert with full joined patient, family,
    caretaker, booking, and visit tracking context.
    """
    if sos_id is None or str(sos_id).strip() == "":
        raise APIException(
            "SOS alert id is required",
            status_code=400,
            errors={"id": ["SOS alert id is required"]},
        )

    try:
        sos_id_int = int(sos_id)
    except (ValueError, TypeError):
        raise APIException(
            "SOS alert id is required",
            status_code=400,
            errors={"id": ["SOS alert id is required"]},
        )

    effective_booking_sql = """COALESCE(s.booking_id, (
        SELECT b2.id
        FROM bookings b2
        WHERE u.role = 'caretaker'
          AND b2.caretaker_user_id = s.user_id
          AND b2.status = 'in_progress'
        ORDER BY b2.id DESC
        LIMIT 1
    ))"""

    query = f"""
        SELECT s.id, s.id AS sos_id, s.id AS alert_id,
               s.user_id, s.user_id AS reporter_user_id,
               {effective_booking_sql} AS booking_id,
               CONCAT('#', {effective_booking_sql}) AS formatted_booking_id,
               s.message, s.latitude, s.longitude,
               CASE
                 WHEN s.latitude IS NOT NULL AND s.latitude <> '' AND s.longitude IS NOT NULL AND s.longitude <> ''
                   THEN CONCAT(s.latitude, ', ', s.longitude)
                 ELSE NULL
               END AS location_text,
               s.status, s.created_at, s.created_at AS triggered_at,
               NULL AS resolved_at, NULL AS resolved_by_name,
               u.username AS reporter_username,
               COALESCE(u.username, u.email, u.phone_number) AS reporter_name,
               u.email AS reporter_email, u.role AS reporter_role, u.phone_number AS reporter_phone
        FROM sos_alerts s
        INNER JOIN users u ON u.id = s.user_id
        WHERE s.id = :sos_id
    """

    row = db.execute(text(query), {"sos_id": sos_id_int}).fetchone()
    if not row:
        raise APIException("SOS alert not found", status_code=404)

    booking_id = getattr(row, "booking_id", None)
    booking_dict: Optional[Dict[str, Any]] = None
    patient_dict: Optional[Dict[str, Any]] = None
    family_dict: Optional[Dict[str, Any]] = None
    caretaker_dict: Optional[Dict[str, Any]] = None

    if booking_id is not None:
        b_query = """
            SELECT b.id, b.id AS booking_id, CONCAT('#', b.id) AS formatted_booking_id,
                   b.family_user_id, b.caretaker_user_id, b.patient_id,
                   b.status, b.status AS booking_status, b.service_type,
                   b.start_time, b.end_time, b.booking_date, b.address,
                   b.location_latitude, b.location_longitude,
                   p.patient_name, p.age AS patient_age, p.gender AS patient_gender,
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
                   vt.check_out_time AS checked_out_at
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
            WHERE b.id = :bid
            ORDER BY vt.id DESC
            LIMIT 1
        """
        b_row = db.execute(text(b_query), {"bid": int(booking_id)}).fetchone()
        if b_row:
            fam_uid = getattr(b_row, "family_user_id", None)
            car_uid = getattr(b_row, "caretaker_user_id", None)
            pat_id = getattr(b_row, "patient_id", None)
            v_id = getattr(b_row, "visit_id", None)

            booking_dict = {
                "id": int(b_row.id),
                "booking_id": int(b_row.id),
                "formatted_booking_id": b_row.formatted_booking_id,
                "family_user_id": int(fam_uid) if fam_uid is not None else None,
                "caretaker_user_id": int(car_uid) if car_uid is not None else None,
                "patient_id": int(pat_id) if pat_id is not None else None,
                "status": str(b_row.status.value if hasattr(b_row.status, "value") else b_row.status),
                "booking_status": str(b_row.booking_status.value if hasattr(b_row.booking_status, "value") else b_row.booking_status),
                "service_type": b_row.service_type,
                "start_time": _format_time(b_row.start_time),
                "end_time": _format_time(b_row.end_time),
                "booking_date": _format_date(b_row.booking_date),
                "address": b_row.address,
                "location_latitude": b_row.location_latitude,
                "location_longitude": b_row.location_longitude,
                "patient_name": b_row.patient_name,
                "patient_age": b_row.patient_age,
                "patient_gender": str(b_row.patient_gender.value if hasattr(b_row.patient_gender, "value") else b_row.patient_gender) if b_row.patient_gender is not None else None,
                "family_username": b_row.family_username,
                "family_email": b_row.family_email,
                "family_phone": b_row.family_phone,
                "family_name": b_row.family_name,
                "caretaker_username": b_row.caretaker_username,
                "caretaker_email": b_row.caretaker_email,
                "caretaker_phone": b_row.caretaker_phone,
                "caretaker_name": b_row.caretaker_name,
                "caregiver_name": b_row.caregiver_name,
                "caregiver_phone": b_row.caregiver_phone,
                "visit_id": int(v_id) if v_id is not None else None,
                "checked_in_at": _format_dt(b_row.checked_in_at),
                "checked_out_at": _format_dt(b_row.checked_out_at),
            }

            patient_dict = {
                "id": int(pat_id) if pat_id is not None else None,
                "name": b_row.patient_name,
                "patient_name": b_row.patient_name,
                "age": b_row.patient_age,
                "gender": str(b_row.patient_gender.value if hasattr(b_row.patient_gender, "value") else b_row.patient_gender) if b_row.patient_gender is not None else None,
            }

            family_dict = {
                "user_id": int(fam_uid) if fam_uid is not None else None,
                "name": b_row.family_name,
                "family_name": b_row.family_name,
                "username": b_row.family_username,
                "email": b_row.family_email,
                "phone": b_row.family_phone,
            }

            caretaker_dict = {
                "user_id": int(car_uid) if car_uid is not None else None,
                "name": b_row.caretaker_name,
                "caretaker_name": b_row.caretaker_name,
                "caregiver_name": b_row.caregiver_name,
                "username": b_row.caretaker_username,
                "email": b_row.caretaker_email,
                "phone": b_row.caretaker_phone,
            }

    location_dict = {
        "latitude": row.latitude,
        "longitude": row.longitude,
        "location_text": row.location_text,
    }

    reporter_dict = {
        "user_id": int(row.reporter_user_id),
        "name": row.reporter_name,
        "username": row.reporter_username,
        "email": row.reporter_email,
        "phone": row.reporter_phone,
        "role": str(row.reporter_role.value if hasattr(row.reporter_role, "value") else row.reporter_role),
    }

    resolution_dict = {
        "status": str(row.status.value if hasattr(row.status, "value") else row.status),
        "resolved_at": None,
        "resolved_by_name": None,
    }

    base_sos = {
        "id": int(row.id),
        "sos_id": int(row.sos_id),
        "alert_id": int(row.alert_id),
        "user_id": int(row.user_id),
        "reporter_user_id": int(row.reporter_user_id),
        "booking_id": int(booking_id) if booking_id is not None else None,
        "formatted_booking_id": row.formatted_booking_id if booking_id is not None else None,
        "message": row.message,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "location_text": row.location_text,
        "status": str(row.status.value if hasattr(row.status, "value") else row.status),
        "created_at": _format_dt(row.created_at),
        "triggered_at": _format_dt(row.triggered_at),
        "resolved_at": None,
        "resolved_by_name": None,
        "reporter_username": row.reporter_username,
        "reporter_name": row.reporter_name,
        "reporter_email": row.reporter_email,
        "reporter_role": str(row.reporter_role.value if hasattr(row.reporter_role, "value") else row.reporter_role),
        "reporter_phone": row.reporter_phone,
        "patient_name": booking_dict["patient_name"] if booking_dict else None,
        "family_name": booking_dict["family_name"] if booking_dict else None,
        "caretaker_user_id": booking_dict["caretaker_user_id"] if booking_dict else None,
        "caretaker_name": booking_dict["caretaker_name"] if booking_dict else None,
        "caregiver_name": booking_dict["caregiver_name"] if booking_dict else None,
        "caretaker_phone": booking_dict["caretaker_phone"] if booking_dict else None,
        "caregiver_phone": booking_dict["caregiver_phone"] if booking_dict else None,
        "caretaker_email": booking_dict["caretaker_email"] if booking_dict else None,
        "booking": booking_dict,
    }

    result_data = dict(base_sos)
    result_data["alert"] = base_sos
    result_data["booking"] = booking_dict
    result_data["patient"] = patient_dict
    result_data["family"] = family_dict
    result_data["caretaker"] = caretaker_dict
    result_data["reporter"] = reporter_dict
    result_data["location"] = location_dict
    result_data["resolution"] = resolution_dict

    return result_data

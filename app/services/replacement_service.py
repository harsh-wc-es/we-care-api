"""
WeCare — Replacement Ticket Service

Complete implementation of Replacement domain business logic mirroring Route: - api/v1/replacement/create_ticket
- api/v1/replacement/admin_list
- api/v1/replacement/admin_view
- api/v1/replacement/admin_assign
- api/v1/replacement/admin_update_status
- api/v1/replacement/admin_resolve
- api/v1/replacement/admin_cancel
- api/v1/replacement/admin_delete
- helpers/replacement_tickets
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.audit_service import audit_log
from app.services.notification_service import notify_replacement_updated


def _get_user_id(user: Any) -> int:
    """Extracts integer user ID from dict or User model."""
    if isinstance(user, dict):
        return int(user["id"])
    return int(user.id)


def _format_dt(val: Any) -> Optional[str]:
    """Formats datetime values to standard string representation."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def _format_date(val: Any) -> Optional[str]:
    """Formats date values to standard string representation."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    return str(val)


def _format_time(val: Any) -> Optional[str]:
    """Formats time / timedelta values."""
    if val is None:
        return None
    return str(val)


def _replacement_ticket_column_exists(db: Session, column: str) -> bool:
    """
    Route: replacement_ticket_column_exists() — helpers/replacement_tickets L3-14
    """
    try:
        row = db.execute(
            text(
                "SELECT COUNT(*) "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND TABLE_NAME = 'replacement_tickets' "
                "  AND COLUMN_NAME = :col"
            ),
            {"col": column},
        ).scalar()
        return bool(row and row > 0)
    except Exception:
        return False


def _replacement_ticket_admin_select_sql(db: Session) -> str:
    """
    Route: replacement_ticket_admin_select_sql() — helpers/replacement_tickets L88-149
    """
    has_req = _replacement_ticket_column_exists(db, "requested_by_user_id")
    has_orig = _replacement_ticket_column_exists(db, "original_caretaker_user_id")
    has_repl = _replacement_ticket_column_exists(db, "replacement_caretaker_user_id")
    has_note = _replacement_ticket_column_exists(db, "admin_note")
    has_up = _replacement_ticket_column_exists(db, "updated_at")
    has_res_by = _replacement_ticket_column_exists(db, "resolved_by")
    has_res_at = _replacement_ticket_column_exists(db, "resolved_at")

    req_sel = "rt.requested_by_user_id" if has_req else "NULL AS requested_by_user_id"
    orig_sel = "COALESCE(rt.original_caretaker_user_id, b.caretaker_user_id) AS original_caretaker_user_id" if has_orig else "b.caretaker_user_id AS original_caretaker_user_id"
    repl_sel = "rt.replacement_caretaker_user_id" if has_repl else "NULL AS replacement_caretaker_user_id"
    note_sel = "rt.admin_note" if has_note else "NULL AS admin_note"
    up_sel = "rt.updated_at" if has_up else "NULL AS updated_at"
    res_by_sel = "rt.resolved_by" if has_res_by else "NULL AS resolved_by"
    res_at_sel = "rt.resolved_at" if has_res_at else "NULL AS resolved_at"

    req_user_join = "LEFT JOIN users req ON req.id = rt.requested_by_user_id" if has_req else "LEFT JOIN users req ON 1=0"
    req_prof_join = "LEFT JOIN caretaker_profiles reqcp ON reqcp.user_id = req.id" if has_req else "LEFT JOIN caretaker_profiles reqcp ON 1=0"

    orig_user_on = "COALESCE(rt.original_caretaker_user_id, b.caretaker_user_id)" if has_orig else "b.caretaker_user_id"
    repl_user_on = "rt.replacement_caretaker_user_id" if has_repl else "NULL"

    return f"""
        SELECT rt.id,
               rt.complaint_id,
               rt.booking_id,
               CONCAT('#', rt.booking_id) AS booking_reference,
               COALESCE(rt.family_user_id, b.family_user_id) AS family_user_id,
               {req_sel},
               {orig_sel},
               {repl_sel},
               rt.reason,
               rt.status,
               {note_sel},
               {res_by_sel},
               {res_at_sel},
               rt.created_at,
               {up_sel},
               b.status AS booking_status,
               b.booking_date,
               b.start_time,
               b.end_time,
               b.service_type,
               b.address AS booking_address,
               fu.username AS family_username,
               fu.username AS family_name,
               fu.phone_number AS family_phone,
               fu.email AS family_email,
               COALESCE(NULLIF(ocp.full_name, ''), ou.username) AS original_caretaker_name,
               ou.phone_number AS original_caretaker_phone,
               ou.email AS original_caretaker_email,
               COALESCE(NULLIF(rcp.full_name, ''), ru.username) AS replacement_caretaker_name,
               ru.phone_number AS replacement_caretaker_phone,
               ru.email AS replacement_caretaker_email,
               COALESCE(NULLIF(reqcp.full_name, ''), req.username) AS requested_by_name,
               req.phone_number AS requested_by_phone,
               req.email AS requested_by_email,
               pd.id AS patient_id,
               pd.patient_name,
               pd.age AS patient_age,
               pd.gender AS patient_gender,
               pd.medical_condition,
               pd.mobility_status,
               pd.care_type,
               c.subject AS complaint_subject,
               c.description AS complaint_description,
               c.status AS complaint_status
        FROM replacement_tickets rt
        LEFT JOIN bookings b ON b.id = rt.booking_id
        LEFT JOIN users fu ON fu.id = COALESCE(rt.family_user_id, b.family_user_id)
        LEFT JOIN patient_details pd ON pd.id = b.patient_id
        LEFT JOIN users ou ON ou.id = {orig_user_on}
        LEFT JOIN caretaker_profiles ocp ON ocp.user_id = ou.id
        LEFT JOIN users ru ON ru.id = {repl_user_on}
        LEFT JOIN caretaker_profiles rcp ON rcp.user_id = ru.id
        {req_user_join}
        {req_prof_join}
        LEFT JOIN complaints c ON c.id = rt.complaint_id
    """


def _normalize_ticket_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route: replacement_ticket_normalize_row() — helpers/replacement_tickets L151-166
    """
    result = dict(row)

    orig_name = result.get("original_caretaker_name") or None
    repl_name = result.get("replacement_caretaker_name") or None
    req_name = result.get("requested_by_name") or None
    fam_name = result.get("family_name") or result.get("family_username") or None

    result["id"] = int(result["id"])
    result["booking_id"] = int(result["booking_id"])
    result["complaint_id"] = int(result["complaint_id"]) if result.get("complaint_id") is not None else None
    result["family_user_id"] = int(result["family_user_id"]) if result.get("family_user_id") is not None else None
    result["requested_by_user_id"] = int(result["requested_by_user_id"]) if result.get("requested_by_user_id") is not None else None
    result["original_caretaker_user_id"] = int(result["original_caretaker_user_id"]) if result.get("original_caretaker_user_id") is not None else None
    result["replacement_caretaker_user_id"] = int(result["replacement_caretaker_user_id"]) if result.get("replacement_caretaker_user_id") is not None else None
    result["resolved_by"] = int(result["resolved_by"]) if result.get("resolved_by") is not None else None

    result["booking_reference"] = result.get("booking_reference") or f"#{result['booking_id']}"
    result["original_caretaker_name"] = orig_name
    result["replacement_caretaker_name"] = repl_name
    result["requested_by_name"] = req_name
    result["family_name"] = fam_name

    result["caregiver_name"] = orig_name
    result["caretaker_name"] = orig_name
    result["replacement_name"] = repl_name
    result["booking"] = result["booking_id"]

    result["created_at"] = _format_dt(result.get("created_at"))
    result["updated_at"] = _format_dt(result.get("updated_at"))
    result["resolved_at"] = _format_dt(result.get("resolved_at"))
    result["created"] = result["created_at"]

    result["booking_date"] = _format_date(result.get("booking_date"))
    result["start_time"] = _format_time(result.get("start_time"))
    result["end_time"] = _format_time(result.get("end_time"))

    # Convert status to str if enum
    if hasattr(result.get("status"), "value"):
        result["status"] = result["status"].value
    if hasattr(result.get("booking_status"), "value"):
        result["booking_status"] = result["booking_status"].value
    if hasattr(result.get("complaint_status"), "value"):
        result["complaint_status"] = result["complaint_status"].value

    return result


def _fetch_available_replacement_caretakers(db: Session, exclude_user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Route: replacement_ticket_available_caretakers() — helpers/replacement_tickets L178-216
    """
    params: Dict[str, Any] = {}
    exclude_sql = ""
    if exclude_user_id:
        exclude_sql = "AND u.id <> :exclude_id"
        params["exclude_id"] = int(exclude_user_id)

    query = f"""
        SELECT u.id,
               u.id AS user_id,
               COALESCE(NULLIF(cp.full_name, ''), u.username) AS name,
               COALESCE(NULLIF(cp.full_name, ''), u.username) AS caretaker_name,
               u.phone_number AS phone,
               u.email,
               cp.pricing_tier,
               pt.name AS pricing_tier_name,
               cp.rating,
               cp.total_reviews,
               cp.is_available,
               cp.verification_status,
               cp.availability_reason
        FROM users u
        INNER JOIN caretaker_profiles cp ON cp.user_id = u.id
        LEFT JOIN pricing_tiers pt ON pt.id = cp.pricing_tier_id
        WHERE u.role = 'caretaker'
          AND u.is_active = 1
          AND u.is_verified = 1
          AND cp.verification_status = 'approved'
          AND cp.is_available = 1
          {exclude_sql}
        ORDER BY cp.rating DESC, cp.full_name ASC, u.username ASC
        LIMIT 100
    """
    rows = db.execute(text(query), params).mappings().all()

    items = []
    for r in rows:
        d = dict(r)
        d["id"] = int(d["id"])
        d["user_id"] = int(d["user_id"])
        d["rating"] = float(d["rating"]) if d.get("rating") is not None else 0.0
        d["total_reviews"] = int(d["total_reviews"]) if d.get("total_reviews") is not None else 0
        d["is_available"] = int(d["is_available"]) if d.get("is_available") is not None else 0
        items.append(d)

    return items


# ── Create Ticket ─────────────────────────────────────────────────────────────

def create_replacement_ticket(
    db: Session,
    caretaker_user: Any,
    booking_id: Optional[Union[int, str]],
    reason: Optional[str],
    complaint_id: Optional[Union[int, str]] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/replacement/create_ticket
    Caretaker submits a replacement ticket request for their assigned booking.
    """
    user_id = _get_user_id(caretaker_user)
    reason_str = str(reason).strip() if reason is not None else ""

    if booking_id is None or str(booking_id).strip() == "" or not reason_str:
        raise APIException("Booking id and reason are required", status_code=400)

    try:
        bid = int(booking_id)
    except (ValueError, TypeError):
        raise APIException("Booking id and reason are required", status_code=400)

    b_row = db.execute(
        text("SELECT id, family_user_id, caretaker_user_id FROM bookings WHERE id = :bid LIMIT 1"),
        {"bid": bid},
    ).fetchone()

    if not b_row:
        raise APIException("Booking not found", status_code=404)

    if int(b_row.caretaker_user_id or 0) != user_id:
        raise APIException(
            "You are not allowed to create a replacement ticket for this booking",
            status_code=403,
        )

    cid_int: Optional[int] = None
    if complaint_id is not None and str(complaint_id).strip() != "":
        try:
            cid_int = int(complaint_id)
            c_row = db.execute(
                text("SELECT id FROM complaints WHERE id = :cid AND booking_id = :bid LIMIT 1"),
                {"cid": cid_int, "bid": bid},
            ).fetchone()
            if not c_row:
                raise APIException("Complaint not found for this booking", status_code=404)
        except (ValueError, TypeError):
            raise APIException("Complaint not found for this booking", status_code=404)

    has_req = _replacement_ticket_column_exists(db, "requested_by_user_id")
    cols = ["complaint_id", "booking_id", "family_user_id", "original_caretaker_user_id", "reason"]
    placeholders = [":cid", ":bid", ":fid", ":orig_id", ":reason"]
    params = {
        "cid": cid_int,
        "bid": bid,
        "fid": b_row.family_user_id,
        "orig_id": user_id,
        "reason": reason_str,
    }
    if has_req:
        cols.append("requested_by_user_id")
        placeholders.append(":req_id")
        params["req_id"] = user_id

    db.execute(
        text(
            f"INSERT INTO replacement_tickets ({', '.join(cols)}) "
            f"VALUES ({', '.join(placeholders)})"
        ),
        params,
    )
    new_ticket_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())
    db.commit()

    return {
        "replacement_ticket_id": new_ticket_id,
        "booking_id": bid,
        "requested_by_user_id": user_id,
        "original_caretaker_user_id": user_id,
    }


# ── Admin Tickets List ────────────────────────────────────────────────────────

def get_admin_replacement_tickets_list(
    db: Session,
    admin_user: Any,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/replacement/admin_list
    Admin listing of replacement tickets with filtering, pagination, and aliased tickets/replacements.
    """
    page = max(1, int(page))
    limit = min(100, max(1, int(limit)))
    offset = (page - 1) * limit

    status_str = str(status).strip() if status is not None else ""
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    where_sql = ""

    if status_str != "" and status_str != "all":
        if status_str not in ("open", "assigned", "resolved", "cancelled"):
            raise APIException("Invalid replacement status", status_code=400)
        where_sql = "WHERE rt.status = :status_filter"
        params["status_filter"] = status_str

    count_query = f"SELECT COUNT(*) AS total FROM replacement_tickets rt {where_sql}"
    count_row = db.execute(text(count_query), params).fetchone()
    total = int(count_row.total) if count_row else 0

    query = f"""
        {_replacement_ticket_admin_select_sql(db)}
        {where_sql}
        ORDER BY rt.id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(query), params).mappings().all()
    items = [_normalize_ticket_row(dict(r)) for r in rows]

    total_pages = math.ceil(total / limit) if limit > 0 else 1

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "items": items,
        "tickets": items,
        "replacements": items,
    }


# ── Admin Ticket View Detail ──────────────────────────────────────────────────

def get_admin_replacement_ticket_detail(
    db: Session,
    admin_user: Any,
    ticket_id: Optional[Union[int, str]],
) -> Dict[str, Any]:
    """
    Route: api/v1/replacement/admin_view
    Admin single ticket view with available replacement caretakers if open.
    """
    if ticket_id is None or str(ticket_id).strip() == "":
        raise APIException("Replacement ticket id is required", status_code=400)

    try:
        tid = int(ticket_id)
    except (ValueError, TypeError):
        raise APIException("Replacement ticket id is required", status_code=400)

    query = f"{_replacement_ticket_admin_select_sql(db)} WHERE rt.id = :tid LIMIT 1"
    row = db.execute(text(query), {"tid": tid}).mappings().first()

    if not row:
        raise APIException("Replacement ticket not found", status_code=404)

    ticket = _normalize_ticket_row(dict(row))
    ticket["available_replacement_caretakers"] = []

    if ticket.get("status") == "open":
        orig_id = ticket.get("original_caretaker_user_id")
        ticket["available_replacement_caretakers"] = _fetch_available_replacement_caretakers(
            db=db,
            exclude_user_id=int(orig_id) if orig_id else None,
        )

    return ticket


# ── Admin Assign Caretaker ───────────────────────────────────────────────────

def admin_assign_replacement_caretaker(
    db: Session,
    admin_user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/replacement/admin_assign
    Assigns an approved caretaker to an open replacement ticket and updates the booking.
    """
    admin_id = _get_user_id(admin_user)

    tid_raw = data.get("ticket_id") or data.get("id")
    repl_user_id_raw = data.get("replacement_caretaker_user_id")
    admin_note = str(data.get("admin_note") or data.get("admin_notes") or "").strip()

    if (
        tid_raw is None
        or str(tid_raw).strip() == ""
        or repl_user_id_raw is None
        or str(repl_user_id_raw).strip() == ""
    ):
        raise APIException("Ticket id and replacement caretaker are required", status_code=400)

    try:
        tid = int(tid_raw)
        repl_user_id = int(repl_user_id_raw)
    except (ValueError, TypeError):
        raise APIException("Ticket id and replacement caretaker are required", status_code=400)

    query = f"{_replacement_ticket_admin_select_sql(db)} WHERE rt.id = :tid LIMIT 1"
    row = db.execute(text(query), {"tid": tid}).mappings().first()
    if not row:
        raise APIException("Replacement ticket not found", status_code=404)

    ticket = _normalize_ticket_row(dict(row))

    if ticket.get("status") != "open":
        raise APIException("Only open replacement tickets can be assigned", status_code=409)

    orig_id = ticket.get("original_caretaker_user_id")
    if orig_id is not None and int(orig_id) == repl_user_id:
        raise APIException("Replacement caretaker cannot be the original caretaker", status_code=400)

    # Verify replacement caretaker eligibility
    repl_row = db.execute(
        text(
            "SELECT u.id, u.role, u.is_active, u.is_verified, "
            "       COALESCE(NULLIF(cp.full_name, ''), u.username) AS caretaker_name, "
            "       cp.verification_status, cp.is_available "
            "FROM users u "
            "INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "WHERE u.id = :uid AND u.role = 'caretaker' "
            "LIMIT 1"
        ),
        {"uid": repl_user_id},
    ).fetchone()

    if not repl_row:
        raise APIException("Replacement caretaker not found", status_code=404)

    if int(repl_row.is_active) != 1 or int(repl_row.is_verified) != 1:
        raise APIException("Replacement caretaker must be active and verified", status_code=400)

    ver_status = str(repl_row.verification_status.value if hasattr(repl_row.verification_status, "value") else repl_row.verification_status)
    if ver_status != "approved":
        raise APIException("Replacement caretaker must be approved", status_code=400)

    if int(repl_row.is_available or 0) != 1:
        raise APIException("Replacement caretaker must be available", status_code=400)

    b_row = db.execute(
        text("SELECT id FROM bookings WHERE id = :bid LIMIT 1"),
        {"bid": ticket["booking_id"]},
    ).fetchone()

    if not b_row:
        raise APIException("Booking not found for this ticket", status_code=404)

    has_note = _replacement_ticket_column_exists(db, "admin_note")
    has_up = _replacement_ticket_column_exists(db, "updated_at")

    note_sql = ", admin_note = :note" if has_note else ""
    up_sql = ", updated_at = NOW()" if has_up else ""

    params = {
        "rcid": repl_user_id,
        "tid": tid,
    }
    if has_note:
        params["note"] = admin_note if admin_note != "" else None

    # Perform updates within transaction
    try:
        db.execute(
            text(
                f"UPDATE replacement_tickets "
                f"SET replacement_caretaker_user_id = :rcid, "
                f"    status = 'assigned' "
                f"    {note_sql} "
                f"    {up_sql} "
                f"WHERE id = :tid"
            ),
            params,
        )

        db.execute(
            text("UPDATE bookings SET caretaker_user_id = :rcid, updated_at = NOW() WHERE id = :bid"),
            {"rcid": repl_user_id, "bid": ticket["booking_id"]},
        )

        audit_log(
            db=db,
            admin_user_id=admin_id,
            action="assign_replacement_ticket",
            entity_type="replacement_ticket",
            entity_id=tid,
            old_values=ticket,
            new_values={
                "replacement_caretaker_user_id": repl_user_id,
                "admin_note": admin_note,
            },
        )

        notify_replacement_updated(db, tid)
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException("Failed to assign replacement caretaker", status_code=500, errors={"exception": str(e)})

    return get_admin_replacement_ticket_detail(db, admin_user, tid)


# ── Admin Update Status ───────────────────────────────────────────────────────

def admin_update_replacement_ticket_status(
    db: Session,
    admin_user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/replacement/admin_update_status
    Generic status update for replacement tickets.
    """
    admin_id = _get_user_id(admin_user)

    tid_raw = data.get("ticket_id") or data.get("id")
    status_str = str(data.get("status") or "").strip()
    repl_user_id_raw = data.get("replacement_caretaker_user_id")
    admin_note = str(data.get("admin_note") or "").strip()

    if (
        tid_raw is None
        or str(tid_raw).strip() == ""
        or not status_str
        or status_str not in ("open", "assigned", "resolved", "cancelled")
    ):
        raise APIException("Valid replacement ticket id and status are required", status_code=400)

    try:
        tid = int(tid_raw)
    except (ValueError, TypeError):
        raise APIException("Valid replacement ticket id and status are required", status_code=400)

    repl_user_id: Optional[int] = None
    if repl_user_id_raw is not None and str(repl_user_id_raw).strip() != "":
        try:
            repl_user_id = int(repl_user_id_raw)
            c_check = db.execute(
                text(
                    "SELECT u.id FROM users u "
                    "INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
                    "WHERE u.id = :uid AND u.role = 'caretaker' AND cp.verification_status = 'approved'"
                ),
                {"uid": repl_user_id},
            ).fetchone()
            if not c_check:
                raise APIException("Replacement caretaker not approved or not found", status_code=400)
        except (ValueError, TypeError):
            raise APIException("Replacement caretaker not approved or not found", status_code=400)

    has_req = _replacement_ticket_column_exists(db, "requested_by_user_id")
    req_sel = "requested_by_user_id" if has_req else "NULL AS requested_by_user_id"

    old_row = db.execute(
        text(
            f"SELECT id, complaint_id, booking_id, family_user_id, {req_sel}, "
            f"       original_caretaker_user_id, replacement_caretaker_user_id, reason, "
            f"       status, admin_note, resolved_by, resolved_at, created_at, updated_at "
            f"FROM replacement_tickets "
            f"WHERE id = :tid"
        ),
        {"tid": tid},
    ).fetchone()

    if not old_row:
        raise APIException("Replacement ticket not found", status_code=404)

    resolved_by = admin_id if status_str == "resolved" else None
    resolved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if status_str == "resolved" else None

    db.execute(
        text(
            "UPDATE replacement_tickets "
            "SET status = :status, "
            "    replacement_caretaker_user_id = :rcid, "
            "    admin_note = :note, "
            "    resolved_by = :res_by, "
            "    resolved_at = :res_at, "
            "    updated_at = NOW() "
            "WHERE id = :tid"
        ),
        {
            "status": status_str,
            "rcid": repl_user_id,
            "note": admin_note if admin_note != "" else None,
            "res_by": resolved_by,
            "res_at": resolved_at,
            "tid": tid,
        },
    )

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_replacement_status",
        entity_type="replacement_ticket",
        entity_id=tid,
        old_values=dict(old_row._mapping) if hasattr(old_row, "_mapping") else dict(old_row),
        new_values={
            "status": status_str,
            "replacement_caretaker_user_id": repl_user_id,
            "admin_note": admin_note,
        },
    )

    notify_replacement_updated(db, tid)
    db.commit()

    return get_admin_replacement_ticket_detail(db, admin_user, tid)


# ── Admin Resolve Ticket ──────────────────────────────────────────────────────

def admin_resolve_replacement_ticket(
    db: Session,
    admin_user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/replacement/admin_resolve
    Transitions an assigned ticket to resolved status.
    """
    admin_id = _get_user_id(admin_user)

    tid_raw = data.get("ticket_id") or data.get("id")
    admin_note = str(data.get("admin_note") or data.get("admin_notes") or "").strip()

    if tid_raw is None or str(tid_raw).strip() == "":
        raise APIException("Ticket id is required", status_code=400)

    try:
        tid = int(tid_raw)
    except (ValueError, TypeError):
        raise APIException("Ticket id is required", status_code=400)

    query = f"{_replacement_ticket_admin_select_sql(db)} WHERE rt.id = :tid LIMIT 1"
    row = db.execute(text(query), {"tid": tid}).mappings().first()
    if not row:
        raise APIException("Replacement ticket not found", status_code=404)

    ticket = _normalize_ticket_row(dict(row))

    if ticket.get("status") != "assigned":
        raise APIException("Only assigned replacement tickets can be resolved", status_code=409)

    has_res_by = _replacement_ticket_column_exists(db, "resolved_by")
    has_res_at = _replacement_ticket_column_exists(db, "resolved_at")
    has_note = _replacement_ticket_column_exists(db, "admin_note")
    has_up = _replacement_ticket_column_exists(db, "updated_at")

    res_by_sql = ", resolved_by = :res_by" if has_res_by else ""
    res_at_sql = ", resolved_at = NOW()" if has_res_at else ""
    note_sql = ", admin_note = :note" if has_note else ""
    up_sql = ", updated_at = NOW()" if has_up else ""

    params = {"tid": tid}
    if has_res_by:
        params["res_by"] = admin_id
    if has_note:
        params["note"] = admin_note if admin_note != "" else None

    db.execute(
        text(
            f"UPDATE replacement_tickets "
            f"SET status = 'resolved' "
            f"    {res_by_sql} "
            f"    {res_at_sql} "
            f"    {note_sql} "
            f"    {up_sql} "
            f"WHERE id = :tid"
        ),
        params,
    )

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="resolve_replacement_ticket",
        entity_type="replacement_ticket",
        entity_id=tid,
        old_values=ticket,
        new_values={"admin_note": admin_note},
    )

    notify_replacement_updated(db, tid)
    db.commit()

    return get_admin_replacement_ticket_detail(db, admin_user, tid)


# ── Admin Cancel Ticket ───────────────────────────────────────────────────────

def admin_cancel_replacement_ticket(
    db: Session,
    admin_user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/replacement/admin_cancel
    Cancels an open or assigned replacement ticket.
    """
    admin_id = _get_user_id(admin_user)

    tid_raw = data.get("ticket_id") or data.get("id")
    admin_note = str(data.get("admin_note") or data.get("admin_notes") or "").strip()

    if tid_raw is None or str(tid_raw).strip() == "":
        raise APIException("Ticket id is required", status_code=400)

    try:
        tid = int(tid_raw)
    except (ValueError, TypeError):
        raise APIException("Ticket id is required", status_code=400)

    query = f"{_replacement_ticket_admin_select_sql(db)} WHERE rt.id = :tid LIMIT 1"
    row = db.execute(text(query), {"tid": tid}).mappings().first()
    if not row:
        raise APIException("Replacement ticket not found", status_code=404)

    ticket = _normalize_ticket_row(dict(row))

    if ticket.get("status") not in ("open", "assigned"):
        raise APIException("Only open or assigned replacement tickets can be cancelled", status_code=409)

    has_note = _replacement_ticket_column_exists(db, "admin_note")
    has_up = _replacement_ticket_column_exists(db, "updated_at")

    note_sql = ", admin_note = :note" if has_note else ""
    up_sql = ", updated_at = NOW()" if has_up else ""

    params = {"tid": tid}
    if has_note:
        params["note"] = admin_note if admin_note != "" else None

    db.execute(
        text(
            f"UPDATE replacement_tickets "
            f"SET status = 'cancelled' "
            f"    {note_sql} "
            f"    {up_sql} "
            f"WHERE id = :tid"
        ),
        params,
    )

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="cancel_replacement_ticket",
        entity_type="replacement_ticket",
        entity_id=tid,
        old_values=ticket,
        new_values={"admin_note": admin_note},
    )

    notify_replacement_updated(db, tid)
    db.commit()

    return get_admin_replacement_ticket_detail(db, admin_user, tid)


# ── Admin Delete Ticket ───────────────────────────────────────────────────────

def admin_delete_replacement_ticket(
    db: Session,
    admin_user: Any,
    ticket_id: Optional[Union[int, str]],
) -> None:
    """
    Route: api/v1/replacement/admin_delete
    Deletes a resolved replacement ticket and writes an audit log.
    """
    admin_id = _get_user_id(admin_user)

    if ticket_id is None or str(ticket_id).strip() == "":
        raise APIException("Replacement ticket id is required", status_code=400)

    try:
        tid = int(ticket_id)
    except (ValueError, TypeError):
        raise APIException("Replacement ticket id is required", status_code=400)

    has_req = _replacement_ticket_column_exists(db, "requested_by_user_id")
    req_sel = "requested_by_user_id" if has_req else "NULL AS requested_by_user_id"

    row = db.execute(
        text(
            f"SELECT id, complaint_id, booking_id, family_user_id, {req_sel}, "
            f"       original_caretaker_user_id, replacement_caretaker_user_id, reason, "
            f"       status, admin_note, resolved_by, resolved_at, created_at, updated_at "
            f"FROM replacement_tickets "
            f"WHERE id = :tid"
        ),
        {"tid": tid},
    ).fetchone()

    if not row:
        raise APIException("Replacement ticket not found", status_code=404)

    status_str = str(row.status.value if hasattr(row.status, "value") else row.status)
    if status_str != "resolved":
        raise APIException("Only resolved replacement tickets can be deleted", status_code=400)

    old_values = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

    db.execute(text("DELETE FROM replacement_tickets WHERE id = :tid"), {"tid": tid})

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="delete_replacement_ticket",
        entity_type="replacement_ticket",
        entity_id=tid,
        old_values=old_values,
        new_values=None,
    )
    db.commit()

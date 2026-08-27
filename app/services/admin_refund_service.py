"""
WeCare — Admin Refund Processing Service (Part 12C)

Migrated from:
- api/v1/admin/refunds
- api/v1/admin/refund_detail
- api/v1/admin/approve_refund
- api/v1/admin/reject_refund
- api/v1/admin/mark_refund_processed
- helpers/refunds

Provides:
- get_admin_refunds_list
- get_admin_refund_detail
- approve_admin_refund
- reject_admin_refund
- mark_admin_refund_processed
"""

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.audit_service import audit_log
from app.services.refund_service import (
    refund_iso,
    refund_statuses,
    refund_validate_status_filter,
)

logger = logging.getLogger(__name__)


def refund_allowed_methods() -> List[str]:
    """
    Allowed refund payment methods mirroring helpers/refunds:
    card, upi, netbanking, wallet, cash, insurance, bank_transfer, other
    """
    return [
        "card",
        "upi",
        "netbanking",
        "wallet",
        "cash",
        "insurance",
        "bank_transfer",
        "other",
    ]


def refund_validate_admin_method(method: Any) -> Tuple[bool, str, Dict[str, List[str]]]:
    """
    Route: refund_validate_method() — helpers/refunds L159-176
    Preserves exact legacy error dictionary keys:
    - empty -> 'payment_method': ['Payment method is required']
    - invalid non-empty -> 'refund_method': ['Refund method must be one of: card, upi, netbanking, wallet, cash, insurance, bank_transfer, other']
    """
    method_clean = str(method or "").strip().lower()
    if not method_clean:
        return False, method_clean, {"payment_method": ["Payment method is required"]}

    if method_clean not in refund_allowed_methods():
        return False, method_clean, {
            "refund_method": [
                "Refund method must be one of: card, upi, netbanking, wallet, cash, insurance, bank_transfer, other"
            ]
        }

    return True, method_clean, {}


def _parse_date_bound(date_str: str) -> Optional[datetime]:
    """
    Attempts to parse date string for date_from / date_to.
    Returns datetime or None if invalid.
    """
    cleaned = date_str.strip()
    if not cleaned:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def get_admin_refunds_list(
    db: Session,
    page: Any = 1,
    limit: Any = 50,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/refunds
    """
    try:
        page_val = max(1, int(page or 1))
    except (ValueError, TypeError):
        page_val = 1

    try:
        limit_val = max(1, min(100, int(limit or 50)))
    except (ValueError, TypeError):
        limit_val = 50

    offset = (page_val - 1) * limit_val
    status_filter = refund_validate_status_filter(status or "")
    search_term = str(search or "").strip()
    date_from_str = str(date_from or "").strip()
    date_to_str = str(date_to or "").strip()

    errors: Dict[str, List[str]] = {}
    if status_filter == "__invalid__":
        errors["status"] = [
            "Status must be one of: pending, approved, rejected, processed, failed, all"
        ]

    df_dt = None
    if date_from_str != "":
        df_dt = _parse_date_bound(date_from_str)
        if df_dt is None:
            errors["date_from"] = ["date_from must be a valid date"]

    dt_dt = None
    if date_to_str != "":
        dt_dt = _parse_date_bound(date_to_str)
        if dt_dt is None:
            errors["date_to"] = ["date_to must be a valid date"]

    if errors:
        raise APIException("Validation failed", errors=errors, status_code=400)

    where: List[str] = []
    params: Dict[str, Any] = {}

    if status_filter is not None:
        where.append("br.status = :status_filter")
        params["status_filter"] = status_filter

    if search_term != "":
        where.append(
            "(CAST(br.id AS CHAR) LIKE :search OR "
            " CAST(br.booking_id AS CHAR) LIKE :search OR "
            " fu.email LIKE :search OR "
            " fu.username LIKE :search OR "
            " p.patient_name LIKE :search)"
        )
        params["search"] = f"%{search_term}%"

    if df_dt is not None:
        where.append("br.created_at >= :date_from")
        params["date_from"] = df_dt.strftime("%Y-%m-%d 00:00:00")

    if dt_dt is not None:
        where.append("br.created_at <= :date_to")
        params["date_to"] = dt_dt.strftime("%Y-%m-%d 23:59:59")

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_stmt = db.execute(
        text(
            f"SELECT COUNT(*) "
            f"FROM booking_refunds br "
            f"INNER JOIN bookings b ON b.id = br.booking_id "
            f"INNER JOIN users fu ON fu.id = br.family_user_id "
            f"LEFT JOIN patient_details p ON p.id = b.patient_id "
            f"{where_sql}"
        ),
        params,
    )
    total = int(count_stmt.scalar() or 0)

    rows = db.execute(
        text(
            f"SELECT br.id, br.booking_id, br.family_user_id, br.caretaker_user_id, br.payment_id, "
            f"       br.paid_amount, br.refund_amount, br.refund_percentage, br.refund_method, "
            f"       br.refund_transaction_id, br.reason, br.status, br.admin_note, "
            f"       br.processed_by_admin_id, br.approved_at, br.rejected_at, br.processed_at, "
            f"       br.created_at, br.updated_at, "
            f"       b.booking_date, b.start_time, b.end_time, "
            f"       fu.username AS family_username, fu.email AS family_email, "
            f"       cu.username AS caretaker_username, "
            f"       p.patient_name "
            f"FROM booking_refunds br "
            f"INNER JOIN bookings b ON b.id = br.booking_id "
            f"INNER JOIN users fu ON fu.id = br.family_user_id "
            f"LEFT JOIN users cu ON cu.id = br.caretaker_user_id "
            f"LEFT JOIN patient_details p ON p.id = b.patient_id "
            f"{where_sql} "
            f"ORDER BY br.created_at DESC, br.id DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit_val, "offset": offset},
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for r in rows:
        m = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        items.append({
            "id": int(m["id"]),
            "booking_id": int(m["booking_id"]),
            "family_user_id": int(m["family_user_id"]),
            "caretaker_user_id": int(m["caretaker_user_id"]) if m.get("caretaker_user_id") is not None else None,
            "payment_id": int(m["payment_id"]) if m.get("payment_id") is not None else None,
            "paid_amount": round(float(m.get("paid_amount") or 0), 2),
            "refund_amount": round(float(m.get("refund_amount") or 0), 2),
            "refund_percentage": round(float(m.get("refund_percentage") or 0), 2),
            "refund_method": m.get("refund_method"),
            "refund_transaction_id": m.get("refund_transaction_id"),
            "reason": m.get("reason"),
            "status": m.get("status"),
            "admin_note": m.get("admin_note"),
            "processed_by_admin_id": int(m["processed_by_admin_id"]) if m.get("processed_by_admin_id") is not None else None,
            "patient_name": m.get("patient_name") or "",
            "family": {
                "id": int(m["family_user_id"]),
                "username": m.get("family_username"),
                "email": m.get("family_email"),
            },
            "caretaker": {
                "id": int(m["caretaker_user_id"]) if m.get("caretaker_user_id") is not None else None,
                "username": m.get("caretaker_username"),
            },
            "booking_date": str(m["booking_date"]) if m.get("booking_date") else None,
            "start_time": str(m["start_time"]) if m.get("start_time") else None,
            "end_time": str(m["end_time"]) if m.get("end_time") else None,
            "approved_at": refund_iso(m.get("approved_at")),
            "rejected_at": refund_iso(m.get("rejected_at")),
            "processed_at": refund_iso(m.get("processed_at")),
            "created_at": refund_iso(m.get("created_at")),
            "updated_at": refund_iso(m.get("updated_at")),
        })

    # Global summary initialized with all 5 statuses
    summary: Dict[str, Dict[str, Any]] = {
        s: {"count": 0, "amount": 0.00} for s in refund_statuses()
    }
    summary_rows = db.execute(
        text(
            "SELECT status, COUNT(*) AS count, COALESCE(SUM(refund_amount), 0) AS amount "
            "FROM booking_refunds "
            "GROUP BY status"
        )
    ).fetchall()
    for r in summary_rows:
        m = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        st = m.get("status")
        if st in summary:
            summary[st] = {
                "count": int(m.get("count") or 0),
                "amount": round(float(m.get("amount") or 0), 2),
            }

    return {
        "items": items,
        "pagination": {
            "page": page_val,
            "limit": limit_val,
            "total": total,
            "total_pages": math.ceil(total / limit_val) if limit_val > 0 else 0,
        },
        "summary": summary,
    }


def get_admin_refund_detail(db: Session, refund_id: Any) -> Dict[str, Any]:
    """
    Route: api/v1/admin/refund_detail
    """
    try:
        r_id = int(refund_id)
        if r_id < 1:
            raise ValueError()
    except (ValueError, TypeError):
        raise APIException(
            message="Invalid refund id",
            errors={"id": ["Refund id must be a positive integer"]},
            status_code=400,
        )

    row = db.execute(
        text(
            "SELECT br.id, br.booking_id, br.family_user_id, br.caretaker_user_id, br.payment_id, "
            "       br.paid_amount, br.refund_amount, br.refund_percentage, br.refund_method, "
            "       br.refund_transaction_id, br.reason, br.status, br.admin_note, "
            "       br.processed_by_admin_id, br.approved_at, br.rejected_at, br.processed_at, "
            "       br.created_at, br.updated_at, "
            "       b.booking_date, b.start_time, b.end_time, b.status AS booking_status, "
            "       fu.username AS family_username, fu.email AS family_email, "
            "       cu.username AS caretaker_username, cu.email AS caretaker_email, "
            "       p.patient_name "
            "FROM booking_refunds br "
            "INNER JOIN bookings b ON b.id = br.booking_id "
            "INNER JOIN users fu ON fu.id = br.family_user_id "
            "LEFT JOIN users cu ON cu.id = br.caretaker_user_id "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE br.id = :id "
            "LIMIT 1"
        ),
        {"id": r_id},
    ).fetchone()

    if not row:
        raise APIException("Refund not found", status_code=404)

    m = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

    return {
        "id": int(m["id"]),
        "booking_id": int(m["booking_id"]),
        "payment_id": int(m["payment_id"]) if m.get("payment_id") is not None else None,
        "paid_amount": round(float(m.get("paid_amount") or 0), 2),
        "refund_amount": round(float(m.get("refund_amount") or 0), 2),
        "refund_percentage": round(float(m.get("refund_percentage") or 0), 2),
        "refund_method": m.get("refund_method"),
        "refund_transaction_id": m.get("refund_transaction_id"),
        "reason": m.get("reason"),
        "status": m.get("status"),
        "admin_note": m.get("admin_note"),
        "processed_by_admin_id": int(m["processed_by_admin_id"]) if m.get("processed_by_admin_id") is not None else None,
        "family": {
            "id": int(m["family_user_id"]),
            "username": m.get("family_username"),
            "email": m.get("family_email"),
        },
        "caretaker": {
            "id": int(m["caretaker_user_id"]) if m.get("caretaker_user_id") is not None else None,
            "username": m.get("caretaker_username"),
            "email": m.get("caretaker_email"),
        },
        "patient_name": m.get("patient_name") or "",
        "booking": {
            "status": m.get("booking_status"),
            "booking_date": str(m["booking_date"]) if m.get("booking_date") else None,
            "start_time": str(m["start_time"]) if m.get("start_time") else None,
            "end_time": str(m["end_time"]) if m.get("end_time") else None,
        },
        "approved_at": refund_iso(m.get("approved_at")),
        "rejected_at": refund_iso(m.get("rejected_at")),
        "processed_at": refund_iso(m.get("processed_at")),
        "created_at": refund_iso(m.get("created_at")),
        "updated_at": refund_iso(m.get("updated_at")),
    }


def approve_admin_refund(
    db: Session,
    admin_user: Dict[str, Any],
    refund_id: Any,
    admin_note: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/approve_refund
    """
    admin_id = int(admin_user["id"])
    errors: Dict[str, List[str]] = {}

    r_id = 0
    try:
        r_id = int(refund_id)
        if r_id < 1:
            errors["refund_id"] = ["Refund id must be a positive integer"]
    except (ValueError, TypeError):
        errors["refund_id"] = ["Refund id must be a positive integer"]

    admin_note_str = str(admin_note or "").strip()
    if len(admin_note_str) > 1000:
        errors["admin_note"] = ["Admin note must not exceed 1000 characters"]

    if errors:
        raise APIException("Validation failed", errors=errors, status_code=400)

    try:
        row = db.execute(
            text("SELECT id, status FROM booking_refunds WHERE id = :id FOR UPDATE"),
            {"id": r_id},
        ).fetchone()

        if not row:
            db.rollback()
            raise APIException("Refund not found", status_code=404)

        m = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        if m["status"] != "pending":
            db.rollback()
            raise APIException(
                message="Only pending refunds can be approved",
                errors={"status": ["Refund status must be pending"]},
                status_code=409,
            )

        db.execute(
            text(
                "UPDATE booking_refunds "
                "SET status = 'approved', "
                "    admin_note = :note, "
                "    processed_by_admin_id = :aid, "
                "    approved_at = NOW(), "
                "    updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "note": admin_note_str if admin_note_str != "" else None,
                "aid": admin_id,
                "id": r_id,
            },
        )

        audit_log(
            db=db,
            admin_user_id=admin_id,
            action="approve_refund",
            entity_type="booking_refund",
            entity_id=r_id,
            old_values={"status": "pending"},
            new_values={"status": "approved", "admin_note": admin_note_str},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.commit()
    except APIException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"approve_refund_failed: {e}")
        raise APIException("Failed to approve refund", status_code=500)

    return {"refund_id": r_id, "status": "approved"}


def reject_admin_refund(
    db: Session,
    admin_user: Dict[str, Any],
    refund_id: Any,
    admin_note: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/reject_refund
    """
    admin_id = int(admin_user["id"])
    errors: Dict[str, List[str]] = {}

    r_id = 0
    try:
        r_id = int(refund_id)
        if r_id < 1:
            errors["refund_id"] = ["Refund id must be a positive integer"]
    except (ValueError, TypeError):
        errors["refund_id"] = ["Refund id must be a positive integer"]

    admin_note_str = str(admin_note or "").strip()
    if len(admin_note_str) > 1000:
        errors["admin_note"] = ["Admin note must not exceed 1000 characters"]

    if errors:
        raise APIException("Validation failed", errors=errors, status_code=400)

    try:
        row = db.execute(
            text("SELECT id, status FROM booking_refunds WHERE id = :id FOR UPDATE"),
            {"id": r_id},
        ).fetchone()

        if not row:
            db.rollback()
            raise APIException("Refund not found", status_code=404)

        m = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        if m["status"] != "pending":
            db.rollback()
            raise APIException(
                message="Only pending refunds can be rejected",
                errors={"status": ["Refund status must be pending"]},
                status_code=409,
            )

        db.execute(
            text(
                "UPDATE booking_refunds "
                "SET status = 'rejected', "
                "    admin_note = :note, "
                "    processed_by_admin_id = :aid, "
                "    rejected_at = NOW(), "
                "    updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "note": admin_note_str if admin_note_str != "" else None,
                "aid": admin_id,
                "id": r_id,
            },
        )

        audit_log(
            db=db,
            admin_user_id=admin_id,
            action="reject_refund",
            entity_type="booking_refund",
            entity_id=r_id,
            old_values={"status": "pending"},
            new_values={"status": "rejected", "admin_note": admin_note_str},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.commit()
    except APIException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"reject_refund_failed: {e}")
        raise APIException("Failed to reject refund", status_code=500)

    return {"refund_id": r_id, "status": "rejected"}


def mark_admin_refund_processed(
    db: Session,
    admin_user: Dict[str, Any],
    refund_id: Any,
    refund_method: Any,
    refund_transaction_id: Any,
    admin_note: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/mark_refund_processed
    """
    admin_id = int(admin_user["id"])
    errors: Dict[str, List[str]] = {}

    r_id = 0
    try:
        r_id = int(refund_id)
        if r_id < 1:
            errors["refund_id"] = ["Refund id must be a positive integer"]
    except (ValueError, TypeError):
        errors["refund_id"] = ["Refund id must be a positive integer"]

    is_valid_method, method_clean, method_errs = refund_validate_admin_method(refund_method)
    if not is_valid_method:
        errors.update(method_errs)

    tx_id_str = str(refund_transaction_id or "").strip()
    if tx_id_str == "":
        errors["refund_transaction_id"] = ["Refund transaction id is required"]
    elif len(tx_id_str) > 255:
        errors["refund_transaction_id"] = [
            "Refund transaction id must not exceed 255 characters"
        ]

    admin_note_str = str(admin_note or "").strip()
    if len(admin_note_str) > 1000:
        errors["admin_note"] = ["Admin note must not exceed 1000 characters"]

    if errors:
        raise APIException("Validation failed", errors=errors, status_code=400)

    try:
        row = db.execute(
            text(
                "SELECT id, booking_id, status "
                "FROM booking_refunds "
                "WHERE id = :id "
                "FOR UPDATE"
            ),
            {"id": r_id},
        ).fetchone()

        if not row:
            db.rollback()
            raise APIException("Refund not found", status_code=404)

        m = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        if m["status"] != "approved":
            db.rollback()
            raise APIException(
                message="Only approved refunds can be marked processed",
                errors={"status": ["Refund status must be approved"]},
                status_code=409,
            )

        booking_id = int(m["booking_id"])

        db.execute(
            text(
                "UPDATE booking_refunds "
                "SET status = 'processed', "
                "    refund_method = :rm, "
                "    refund_transaction_id = :tx, "
                "    admin_note = :note, "
                "    processed_by_admin_id = :aid, "
                "    processed_at = NOW(), "
                "    updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "rm": method_clean,
                "tx": tx_id_str,
                "note": admin_note_str if admin_note_str != "" else None,
                "aid": admin_id,
                "id": r_id,
            },
        )

        db.execute(
            text(
                "UPDATE bookings "
                "SET refund_status = 'processed', "
                "    updated_at = NOW() "
                "WHERE id = :bid"
            ),
            {"bid": booking_id},
        )

        audit_log(
            db=db,
            admin_user_id=admin_id,
            action="mark_refund_processed",
            entity_type="booking_refund",
            entity_id=r_id,
            old_values={"status": "approved"},
            new_values={
                "status": "processed",
                "refund_method": method_clean,
                "refund_transaction_id": tx_id_str,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.commit()
    except APIException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"mark_refund_processed_failed: {e}")
        raise APIException("Failed to mark refund processed", status_code=500)

    return {
        "refund_id": r_id,
        "status": "processed",
        "refund_method": method_clean,
        "refund_transaction_id": tx_id_str,
    }

"""
WeCare — Admin Payout, Settlement & Reports Service (Part 12B)

Migrated from:
- api/v1/admin/earnings
- api/v1/admin/earnings_export
- api/v1/admin/create_payout
- api/v1/admin/update_payout
- api/v1/admin/refresh_payout_eligibility
- api/v1/admin/reports_summary
- helpers/payout

Provides:
- payout_week_window
- payout_eligible_bookings_locked
- get_admin_earnings_summary
- get_admin_earnings_tab
- get_admin_earnings_export
- create_admin_payout_batch
- update_admin_payout
- refresh_admin_payout_eligibility
- get_admin_reports_summary
"""

import logging
import math
import re
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.audit_service import audit_log
from app.services.caretaker_earnings_service import (
    caretaker_money,
    payout_refresh_eligibility,
)
from app.services.notification_service import notify_payout_processed
from app.services.rate_limit_service import enforce_rate_limit

logger = logging.getLogger(__name__)


def payout_week_window(week_end: Optional[str] = None) -> Dict[str, str]:
    """
    Route: payout_week_window() — helpers/payout L89-103

    Calculates week_start (Monday), week_end (Sunday), and week_end_at (Sunday 23:59:59).
    If week_end is omitted, calculates relative to last Sunday.
    """
    if week_end and str(week_end).strip():
        val = str(week_end).strip()
        try:
            dt = datetime.strptime(val[:10], "%Y-%m-%d")
        except ValueError:
            dt = None
    else:
        dt = None

    if dt is None:
        now = datetime.now()
        # In calculation, strtotime("last sunday 23:59:59") refers to previous Sunday:
        # ISO weekday: 1=Mon, 2=Tue, ..., 7=Sun
        # On Monday (1) -> 1 day back (yesterday)
        # On Sunday (7) -> 7 days back (previous Sunday)
        days_back = now.isoweekday()
        sunday_date = (now - timedelta(days=days_back)).date()
        end_dt = datetime.combine(sunday_date, time(23, 59, 59))
    else:
        end_dt = datetime.combine(dt.date(), time(23, 59, 59))

    # Calculate Monday of that week: end_dt - (isoweekday - 1) days
    start_dt = end_dt - timedelta(days=(end_dt.isoweekday() - 1))

    return {
        "week_start": start_dt.strftime("%Y-%m-%d"),
        "week_end": end_dt.strftime("%Y-%m-%d"),
        "week_end_at": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
    }


def payout_eligible_bookings_locked(
    db: Session,
    caretaker_user_id: Optional[int] = None,
    week_end_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Route: payout_eligible_bookings_locked() — helpers/payout L109-137

    MUST be called inside a transaction.
    Uses SELECT ... FOR UPDATE to lock candidate booking rows and prevent race conditions.
    """
    effective_week_end = week_end_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    where = (
        "b.status = 'completed' "
        "AND b.payout_status = 'ready_for_payout' "
        "AND b.completed_at <= :week_end_at "
        "AND b.payout_hold_until <= NOW() "
        "AND b.payment_status <> 'refunded' "
        "AND b.payout_id IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM caretaker_payout_items pi WHERE pi.booking_id = b.id)"
    )
    params: Dict[str, Any] = {"week_end_at": effective_week_end}

    if caretaker_user_id is not None:
        where += " AND b.caretaker_user_id = :caretaker_user_id"
        params["caretaker_user_id"] = int(caretaker_user_id)

    stmt = text(
        f"SELECT b.id, b.caretaker_user_id, b.caretaker_earning_amount, b.total_customer_amount, b.platform_commission_amount "
        f"FROM bookings b "
        f"WHERE {where} "
        f"ORDER BY b.caretaker_user_id ASC, b.completed_at ASC, b.id ASC "
        f"FOR UPDATE"
    )
    rows = db.execute(stmt, params).fetchall()
    return [dict(r._mapping) for r in rows]


def get_admin_earnings_summary(
    db: Session,
    page: Any = 1,
    limit: Any = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/earnings (Default summary view — lines 18-20, 180-256)
    """
    # Always refresh eligibility first
    payout_refresh_eligibility(db)

    def _coerce_int(val: Any, default: int) -> int:
        if val is None or val == "":
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            try:
                m = re.match(r"^[-+]?\d+", str(val).strip())
                if m:
                    return int(m.group(0))
            except Exception:
                pass
            return 0

    page_int = max(1, _coerce_int(page, 1))
    limit_int = min(100, max(1, _coerce_int(limit, 50)))
    offset = (page_int - 1) * limit_int

    total_row = db.execute(
        text("SELECT COUNT(*) FROM users WHERE role = 'caretaker'")
    ).scalar()
    total = int(total_row or 0)

    stmt = text(
        "SELECT "
        "    u.id AS caretaker_user_id, "
        "    u.username, "
        "    u.email, "
        "    COALESCE(ready.ready_amount, 0) AS ready_to_pay, "
        "    COALESCE(hold.hold_amount, 0) AS under_review_hold, "
        "    COALESCE(disputed.disputed_amount, 0) AS disputed, "
        "    COALESCE(failed.failed_amount, 0) AS failed_amount, "
        "    COALESCE(pay.total_collected, 0) AS total_collected, "
        "    COALESCE(outp.total_settled, 0) AS total_settled, "
        "    COALESCE(ready.ready_amount, 0) AS pending_settlement, "
        "    COALESCE(ready.ready_customer_amount, 0) AS ready_customer_amount, "
        "    COALESCE(ready.ready_platform_commission, 0) AS ready_platform_commission, "
        "    COALESCE(hold.hold_platform_commission, 0) AS pending_platform_earnings, "
        "    COALESCE(outp.paid_platform_commission, 0) AS paid_platform_earnings, "
        "    COALESCE(ready.ready_count, 0) AS ready_for_payout_count, "
        "    COALESCE(hold.hold_count, 0) AS hold_count, "
        "    COALESCE(disputed.disputed_count, 0) AS disputed_count, "
        "    COALESCE(failed.failed_count, 0) AS failed_count, "
        "    COALESCE(outp.paid_count, 0) AS paid_count "
        "FROM users u "
        "LEFT JOIN ( "
        "    SELECT caretaker_user_id, "
        "           COUNT(*) AS ready_count, "
        "           SUM(caretaker_earning_amount) AS ready_amount, "
        "           SUM(total_customer_amount) AS ready_customer_amount, "
        "           SUM(platform_commission_amount) AS ready_platform_commission "
        "    FROM bookings "
        "    WHERE payout_status = 'ready_for_payout' "
        "    GROUP BY caretaker_user_id "
        ") ready ON ready.caretaker_user_id = u.id "
        "LEFT JOIN ( "
        "    SELECT caretaker_user_id, "
        "           COUNT(*) AS hold_count, "
        "           SUM(caretaker_earning_amount) AS hold_amount, "
        "           SUM(platform_commission_amount) AS hold_platform_commission "
        "    FROM bookings "
        "    WHERE payout_status = 'hold' "
        "    GROUP BY caretaker_user_id "
        ") hold ON hold.caretaker_user_id = u.id "
        "LEFT JOIN ( "
        "    SELECT caretaker_user_id, "
        "           COUNT(*) AS disputed_count, "
        "           SUM(caretaker_earning_amount) AS disputed_amount "
        "    FROM bookings "
        "    WHERE payout_status = 'disputed' "
        "    GROUP BY caretaker_user_id "
        ") disputed ON disputed.caretaker_user_id = u.id "
        "LEFT JOIN ( "
        "    SELECT caretaker_user_id, "
        "           COUNT(*) AS failed_count, "
        "           SUM(total_caretaker_earnings) AS failed_amount "
        "    FROM caretaker_payouts "
        "    WHERE status = 'failed' "
        "    GROUP BY caretaker_user_id "
        ") failed ON failed.caretaker_user_id = u.id "
        "LEFT JOIN ( "
        "    SELECT caretaker_user_id, "
        "           SUM(amount) AS total_collected "
        "    FROM payments "
        "    WHERE status = 'success' "
        "    GROUP BY caretaker_user_id "
        ") pay ON pay.caretaker_user_id = u.id "
        "LEFT JOIN ( "
        "    SELECT caretaker_user_id, "
        "           COUNT(*) AS paid_count, "
        "           SUM(total_caretaker_earnings) AS total_settled, "
        "           SUM(total_platform_commission) AS paid_platform_commission "
        "    FROM caretaker_payouts "
        "    WHERE status = 'paid' "
        "    GROUP BY caretaker_user_id "
        ") outp ON outp.caretaker_user_id = u.id "
        "WHERE u.role = 'caretaker' "
        "ORDER BY pending_settlement DESC "
        "LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(stmt, {"limit": limit_int, "offset": offset}).fetchall()

    items = []
    for r in rows:
        m = dict(r._mapping)
        item = {
            "caretaker_user_id": int(m["caretaker_user_id"]),
            "username": m["username"],
            "email": m["email"],
            "ready_to_pay": round(float(m["ready_to_pay"] or 0), 2),
            "under_review_hold": round(float(m["under_review_hold"] or 0), 2),
            "disputed": round(float(m["disputed"] or 0), 2),
            "failed_amount": round(float(m["failed_amount"] or 0), 2),
            "total_collected": round(float(m["total_collected"] or 0), 2),
            "total_settled": round(float(m["total_settled"] or 0), 2),
            "pending_settlement": round(float(m["pending_settlement"] or 0), 2),
            "ready_customer_amount": round(float(m["ready_customer_amount"] or 0), 2),
            "ready_platform_commission": round(float(m["ready_platform_commission"] or 0), 2),
            "pending_platform_earnings": round(float(m["pending_platform_earnings"] or 0), 2),
            "paid_platform_earnings": round(float(m["paid_platform_earnings"] or 0), 2),
            "ready_for_payout_count": int(m["ready_for_payout_count"] or 0),
            "hold_count": int(m["hold_count"] or 0),
            "disputed_count": int(m["disputed_count"] or 0),
            "failed_count": int(m["failed_count"] or 0),
            "paid_count": int(m["paid_count"] or 0),
        }
        items.append(item)

    return {
        "page": page_int,
        "limit": limit_int,
        "total": total,
        "total_pages": math.ceil(total / limit_int) if limit_int > 0 else 0,
        "items": items,
    }


def get_admin_earnings_tab(
    db: Session,
    tab: str,
    page: Any = 1,
    limit: Any = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/earnings (Tabbed queue view — lines 27-178)
    Allowed tabs: ready_to_pay, hold, disputed, failed, paid_history
    """
    # Always refresh eligibility first
    payout_refresh_eligibility(db)

    tab_clean = str(tab or "").strip().lower()
    allowed_tabs = ["ready_to_pay", "hold", "disputed", "failed", "paid_history"]

    if tab_clean not in allowed_tabs:
        raise APIException(
            message="Invalid payout tab",
            errors={"tab": ["Allowed values: ready_to_pay, hold, disputed, failed, paid_history"]},
            status_code=400,
        )

    def _coerce_int(val: Any, default: int) -> int:
        if val is None or val == "":
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            try:
                m = re.match(r"^[-+]?\d+", str(val).strip())
                if m:
                    return int(m.group(0))
            except Exception:
                pass
            return 0

    page_int = max(1, _coerce_int(page, 1))
    limit_int = min(100, max(1, _coerce_int(limit, 50)))
    offset = (page_int - 1) * limit_int

    if tab_clean == "failed":
        count_stmt = text("SELECT COUNT(*) FROM caretaker_payouts cp WHERE cp.status = 'failed'")
        total = int(db.execute(count_stmt).scalar() or 0)

        stmt = text(
            "SELECT "
            "    MIN(pi.booking_id) AS booking_id, "
            "    cp.id AS payout_id, "
            "    cp.id AS id, "
            "    cp.caretaker_user_id, "
            "    COALESCE(cprof.full_name, cu.username, cu.email) AS caretaker_name, "
            "    COALESCE(cprof.full_name, cu.username, cu.email) AS caregiver_name, "
            "    cu.username AS caretaker_username, "
            "    cu.email AS caretaker_email, "
            "    cu.phone_number AS caretaker_phone, "
            "    cp.amount AS caretaker_earning_amount, "
            "    cp.amount AS caretaker_earning, "
            "    cp.total_caretaker_earnings, "
            "    cp.gross_customer_amount AS total_customer_amount, "
            "    cp.total_platform_commission AS platform_commission_amount, "
            "    cp.status AS payout_status, "
            "    cp.status AS status, "
            "    cp.admin_note AS failure_reason, "
            "    cp.admin_note AS hold_reason, "
            "    cp.created_at AS payout_created_at, "
            "    cp.settled_at AS payout_processed_at, "
            "    cp.settled_at AS paid_at, "
            "    cp.payment_method, "
            "    cp.transaction_reference, "
            "    cp.payment_reference, "
            "    COUNT(pi.booking_id) AS included_booking_count, "
            "    GROUP_CONCAT(pi.booking_id ORDER BY pi.booking_id ASC) AS booking_ids, "
            "    0 AS complaint_count, "
            "    0 AS dispute_count, "
            "    0 AS sos_count "
            "FROM caretaker_payouts cp "
            "INNER JOIN users cu ON cu.id = cp.caretaker_user_id "
            "LEFT JOIN caretaker_profiles cprof ON cprof.user_id = cp.caretaker_user_id "
            "LEFT JOIN caretaker_payout_items pi ON pi.payout_id = cp.id "
            "WHERE cp.status = 'failed' "
            "GROUP BY cp.id "
            "ORDER BY cp.updated_at DESC, cp.id DESC "
            "LIMIT :limit OFFSET :offset"
        )
        rows = db.execute(stmt, {"limit": limit_int, "offset": offset}).fetchall()

        bookings = []
        for r in rows:
            m = dict(r._mapping)
            # Match type casting: amounts as strings, counts as ints
            for k in [
                "total_amount", "total_customer_amount", "caretaker_earning_amount",
                "caretaker_earning", "total_caretaker_earnings", "platform_commission_amount",
                "paid_amount", "remaining_amount"
            ]:
                if k in m:
                    m[k] = str(m[k]) if m[k] is not None else None
            for k in ["complaint_count", "dispute_count", "sos_count", "included_booking_count"]:
                if k in m:
                    m[k] = int(m[k] or 0)
            # Datetime formatting to string if needed
            for k in ["payout_created_at", "payout_processed_at", "paid_at"]:
                if m.get(k) and hasattr(m[k], "strftime"):
                    m[k] = m[k].strftime("%Y-%m-%d %H:%M:%S")
            bookings.append(m)
    else:
        tab_filters = {
            "ready_to_pay": "b.payout_status = 'ready_for_payout'",
            "hold": "b.payout_status = 'hold'",
            "disputed": "b.payout_status = 'disputed'",
            "paid_history": "b.payout_status = 'paid'",
        }
        where_cond = tab_filters[tab_clean]

        count_stmt = text(
            f"SELECT COUNT(*) "
            f"FROM bookings b "
            f"INNER JOIN users cu ON cu.id = b.caretaker_user_id "
            f"WHERE {where_cond}"
        )
        total = int(db.execute(count_stmt).scalar() or 0)

        stmt = text(
            f"SELECT "
            f"    b.id AS booking_id, "
            f"    b.id AS id, "
            f"    b.family_user_id, "
            f"    b.caretaker_user_id, "
            f"    COALESCE(cprof.full_name, cu.username, cu.email) AS caretaker_name, "
            f"    COALESCE(cprof.full_name, cu.username, cu.email) AS caregiver_name, "
            f"    cu.username AS caretaker_username, "
            f"    cu.email AS caretaker_email, "
            f"    cu.phone_number AS caretaker_phone, "
            f"    COALESCE(fprof.full_name, fu.username, fu.email) AS family_name, "
            f"    fu.username AS family_username, "
            f"    fu.email AS family_email, "
            f"    fu.phone_number AS family_phone, "
            f"    p.patient_name, "
            f"    b.service_type, "
            f"    b.status AS booking_status, "
            f"    b.total_amount, "
            f"    b.total_customer_amount, "
            f"    b.caretaker_earning_amount, "
            f"    b.caretaker_earning_amount AS caretaker_earning, "
            f"    b.platform_commission_amount, "
            f"    b.paid_amount, "
            f"    b.remaining_amount, "
            f"    b.payment_status, "
            f"    b.completed_at, "
            f"    b.completed_at AS booking_completed_at, "
            f"    b.payout_status, "
            f"    b.payout_status AS status, "
            f"    b.payout_hold_until, "
            f"    b.payout_hold_until AS hold_until, "
            f"    b.payout_paid_at, "
            f"    b.payout_paid_at AS paid_at, "
            f"    b.payout_id, "
            f"    cp.created_at AS payout_created_at, "
            f"    cp.settled_at AS payout_processed_at, "
            f"    cp.status AS payout_batch_status, "
            f"    cp.admin_note AS failure_reason, "
            f"    (SELECT COUNT(*) FROM complaints c WHERE c.booking_id = b.id) AS complaint_count, "
            f"    (SELECT COUNT(*) FROM complaints c WHERE c.booking_id = b.id AND c.status IN ('open','in_review')) AS dispute_count, "
            f"    (SELECT COUNT(*) FROM sos_alerts s WHERE s.booking_id = b.id) AS sos_count, "
            f"    (SELECT COUNT(*) FROM complaints c WHERE c.booking_id = b.id) > 0 AS has_complaint, "
            f"    (SELECT COUNT(*) FROM sos_alerts s WHERE s.booking_id = b.id) > 0 AS has_sos_incident, "
            f"    (SELECT COUNT(*) FROM booking_checklist_tasks t WHERE t.booking_id = b.id AND t.status <> 'completed') > 0 AS has_pending_checklist, "
            f"    (SELECT COUNT(*) FROM payments pay WHERE pay.booking_id = b.id AND pay.status = 'refunded') > 0 AS has_refund, "
            f"    CASE "
            f"        WHEN b.payout_status = 'hold' THEN '24-hour completion hold is active' "
            f"        WHEN b.payout_status = 'disputed' THEN 'Complaint, SOS, checklist, or refund review blocks payout' "
            f"        WHEN cp.status = 'failed' THEN COALESCE(cp.admin_note, 'Payout failed') "
            f"        ELSE NULL "
            f"    END AS hold_reason "
            f"FROM bookings b "
            f"INNER JOIN users cu ON cu.id = b.caretaker_user_id "
            f"LEFT JOIN caretaker_profiles cprof ON cprof.user_id = b.caretaker_user_id "
            f"LEFT JOIN users fu ON fu.id = b.family_user_id "
            f"LEFT JOIN family_profiles fprof ON fprof.user_id = b.family_user_id "
            f"LEFT JOIN patient_details p ON p.id = b.patient_id "
            f"LEFT JOIN caretaker_payouts cp ON cp.id = b.payout_id "
            f"WHERE {where_cond} "
            f"ORDER BY b.completed_at DESC, b.id DESC "
            f"LIMIT :limit OFFSET :offset"
        )
        rows = db.execute(stmt, {"limit": limit_int, "offset": offset}).fetchall()

        bookings = []
        for r in rows:
            m = dict(r._mapping)
            for k in [
                "total_amount", "total_customer_amount", "caretaker_earning_amount",
                "caretaker_earning", "platform_commission_amount", "paid_amount", "remaining_amount"
            ]:
                if k in m:
                    m[k] = str(m[k]) if m[k] is not None else None
            for k in [
                "complaint_count", "dispute_count", "sos_count",
                "has_complaint", "has_sos_incident", "has_pending_checklist", "has_refund"
            ]:
                if k in m:
                    m[k] = int(m[k] or 0)
            for k in [
                "completed_at", "booking_completed_at", "payout_hold_until", "hold_until",
                "payout_paid_at", "paid_at", "payout_created_at", "payout_processed_at"
            ]:
                if m.get(k) and hasattr(m[k], "strftime"):
                    m[k] = m[k].strftime("%Y-%m-%d %H:%M:%S")
            bookings.append(m)

    return {
        "tab": tab_clean,
        "page": page_int,
        "limit": limit_int,
        "total": total,
        "total_pages": math.ceil(total / limit_int) if limit_int > 0 else 0,
        "bookings": bookings,
    }


def get_admin_earnings_export(
    db: Session,
    caretaker_user_id: Optional[Any] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/earnings_export
    """
    # Always refresh eligibility first
    payout_refresh_eligibility(db)

    cid_str = str(caretaker_user_id or "").strip()
    status_str = str(status or "").strip().lower()
    start_date_str = str(start_date or "").strip()
    end_date_str = str(end_date or "").strip()

    if status_str != "":
        if status_str not in ["hold", "ready_for_payout", "paid", "disputed"]:
            raise APIException(
                message="Invalid payout status filter",
                errors={"status": ["Allowed: hold, ready_for_payout, paid, disputed"]},
                status_code=400,
            )

    if start_date_str != "":
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date_str):
            raise APIException(
                message="Invalid start_date format",
                errors={"start_date": ["Use YYYY-MM-DD"]},
                status_code=400,
            )

    if end_date_str != "":
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date_str):
            raise APIException(
                message="Invalid end_date format",
                errors={"end_date": ["Use YYYY-MM-DD"]},
                status_code=400,
            )

    where = ["b.status = 'completed'"]
    params: Dict[str, Any] = {}

    if cid_str != "":
        try:
            cid_int = int(cid_str)
            where.append("b.caretaker_user_id = :cid")
            params["cid"] = cid_int
        except ValueError:
            pass

    if status_str != "":
        where.append("b.payout_status = :pstatus")
        params["pstatus"] = status_str

    if start_date_str != "":
        where.append("b.completed_at >= :start_dt")
        params["start_dt"] = f"{start_date_str} 00:00:00"

    if end_date_str != "":
        where.append("b.completed_at <= :end_dt")
        params["end_dt"] = f"{end_date_str} 23:59:59"

    where_sql = " AND ".join(where)

    stmt = text(
        f"SELECT "
        f"    b.id AS booking_id, "
        f"    b.caretaker_user_id, "
        f"    cu.username AS caretaker_username, "
        f"    cu.email AS caretaker_email, "
        f"    b.booking_date, "
        f"    b.start_time, "
        f"    b.end_time, "
        f"    b.completed_at, "
        f"    b.total_customer_amount, "
        f"    b.caretaker_earning_amount, "
        f"    b.platform_commission_amount, "
        f"    b.payout_status, "
        f"    b.payout_paid_at, "
        f"    b.payout_id "
        f"FROM bookings b "
        f"INNER JOIN users cu ON cu.id = b.caretaker_user_id "
        f"WHERE {where_sql} "
        f"ORDER BY b.completed_at DESC, b.id DESC "
        f"LIMIT 5000"
    )
    raw_rows = db.execute(stmt, params).fetchall()

    rows = []
    total_cust = 0.0
    total_ct_earn = 0.0
    total_plat_comm = 0.0

    for r in raw_rows:
        m = dict(r._mapping)
        cust_amt = float(m.get("total_customer_amount") or 0.0)
        ct_amt = float(m.get("caretaker_earning_amount") or 0.0)
        comm_amt = float(m.get("platform_commission_amount") or 0.0)

        total_cust += cust_amt
        total_ct_earn += ct_amt
        total_plat_comm += comm_amt

        # Format datetimes/times for output
        if m.get("booking_date") and hasattr(m["booking_date"], "strftime"):
            m["booking_date"] = m["booking_date"].strftime("%Y-%m-%d")
        if m.get("start_time") and hasattr(m["start_time"], "strftime"):
            m["start_time"] = m["start_time"].strftime("%H:%M:%S")
        elif m.get("start_time") and hasattr(m["start_time"], "total_seconds"):
            sec = int(m["start_time"].total_seconds())
            m["start_time"] = f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"
        if m.get("end_time") and hasattr(m["end_time"], "strftime"):
            m["end_time"] = m["end_time"].strftime("%H:%M:%S")
        elif m.get("end_time") and hasattr(m["end_time"], "total_seconds"):
            sec = int(m["end_time"].total_seconds())
            m["end_time"] = f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"
        if m.get("completed_at") and hasattr(m["completed_at"], "strftime"):
            m["completed_at"] = m["completed_at"].strftime("%Y-%m-%d %H:%M:%S")
        if m.get("payout_paid_at") and hasattr(m["payout_paid_at"], "strftime"):
            m["payout_paid_at"] = m["payout_paid_at"].strftime("%Y-%m-%d %H:%M:%S")

        # Amount fields formatted as strings in items, consistent with PDO default
        for k in ["total_customer_amount", "caretaker_earning_amount", "platform_commission_amount"]:
            if m.get(k) is not None:
                m[k] = str(m[k])

        rows.append(m)

    totals = {
        "total_customer_amount": round(total_cust, 2),
        "total_caretaker_earnings": round(total_ct_earn, 2),
        "total_platform_commission": round(total_plat_comm, 2),
        "record_count": len(rows),
    }

    return {
        "totals": totals,
        "items": rows,
    }


def create_admin_payout_batch(
    db: Session,
    admin_user: Dict[str, Any],
    caretaker_user_id: Any,
    week_end: Optional[str] = None,
    force: Any = False,
    admin_note: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/create_payout
    """
    admin_id = int(admin_user["id"])

    # Rate limit admin payout creation — 10 per minute per admin
    enforce_rate_limit(
        db=db,
        action="create_payout",
        key=f"admin_{admin_id}",
        max_attempts=10,
        window_seconds=60,
        block_seconds=60,
        ip=ip_address,
    )

    cid_str = str(caretaker_user_id or "").strip()
    if not cid_str:
        raise APIException("Caretaker user id is required", status_code=400)

    try:
        cid = int(cid_str)
    except ValueError:
        raise APIException("Caretaker user id is required", status_code=400)

    ct_exists = db.execute(
        text("SELECT id FROM users WHERE id = :id AND role = 'caretaker'"),
        {"id": cid},
    ).fetchone()
    if not ct_exists:
        raise APIException("Caretaker not found", status_code=404)

    window = payout_week_window(week_end)

    force_bool = str(force).strip() in ["1", "true", "True"] if not isinstance(force, bool) else force
    weekday_iso = datetime.now().isoweekday()  # 1=Mon, 2=Tue
    if weekday_iso not in [1, 2] and not force_bool:
        raise APIException(
            message="Weekly payout batches can be generated only on Monday or Tuesday",
            errors={"day": ["Use Monday or Tuesday, or pass force=1 for an admin override"]},
            status_code=400,
        )

    # Refresh eligibility BEFORE entering the transaction
    payout_refresh_eligibility(db)

    try:
        eligible = payout_eligible_bookings_locked(
            db=db,
            caretaker_user_id=cid,
            week_end_at=window["week_end_at"],
        )

        if not eligible:
            db.rollback()
            raise APIException("No eligible bookings found for weekly payout", status_code=400)

        amount = sum(float(b["caretaker_earning_amount"] or 0) for b in eligible)
        gross_customer_amount = sum(float(b["total_customer_amount"] or 0) for b in eligible)
        total_platform_commission = sum(float(b["platform_commission_amount"] or 0) for b in eligible)

        # Check for duplicate payout in same week for same caretaker
        dup_check = db.execute(
            text(
                "SELECT id FROM caretaker_payouts "
                "WHERE caretaker_user_id = :cid AND week_start = :wstart AND week_end = :wend "
                "LIMIT 1"
            ),
            {"cid": cid, "wstart": window["week_start"], "wend": window["week_end"]},
        ).fetchone()

        if dup_check:
            db.rollback()
            raise APIException(
                "A payout batch already exists for this caretaker in the selected week",
                status_code=409,
            )

        note_val = admin_note.strip() if admin_note and str(admin_note).strip() else None

        res = db.execute(
            text(
                "INSERT INTO caretaker_payouts "
                "(caretaker_user_id, amount, gross_customer_amount, total_caretaker_earnings, total_platform_commission, week_start, week_end, admin_note) "
                "VALUES (:cid, :amount, :gross, :earnings, :comm, :wstart, :wend, :note)"
            ),
            {
                "cid": cid,
                "amount": amount,
                "gross": gross_customer_amount,
                "earnings": amount,
                "comm": total_platform_commission,
                "wstart": window["week_start"],
                "wend": window["week_end"],
                "note": note_val,
            },
        )
        payout_id = res.lastrowid

        for b in eligible:
            db.execute(
                text(
                    "INSERT INTO caretaker_payout_items (payout_id, booking_id, caretaker_user_id, amount) "
                    "VALUES (:pid, :bid, :cid, :amt)"
                ),
                {"pid": payout_id, "bid": b["id"], "cid": cid, "amt": b["caretaker_earning_amount"]},
            )
            db.execute(
                text(
                    "UPDATE bookings "
                    "SET payout_id = :pid, payout_status = 'ready_for_payout' "
                    "WHERE id = :bid AND payout_status = 'ready_for_payout' AND payout_id IS NULL"
                ),
                {"pid": payout_id, "bid": b["id"]},
            )

        db.commit()
    except APIException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Payout creation failed: {e}")
        raise APIException("Payout batch could not be created", status_code=500)

    booking_ids = [b["id"] for b in eligible]

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="create_payout",
        entity_type="caretaker_payout",
        entity_id=payout_id,
        old_values=None,
        new_values={
            "caretaker_user_id": cid,
            "amount": amount,
            "gross_customer_amount": gross_customer_amount,
            "total_caretaker_earnings": amount,
            "total_platform_commission": total_platform_commission,
            "booking_ids": booking_ids,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "payout_id": payout_id,
        "amount": amount,
        "gross_customer_amount": gross_customer_amount,
        "total_caretaker_earnings": amount,
        "total_platform_commission": total_platform_commission,
        "week_start": window["week_start"],
        "week_end": window["week_end"],
        "booking_ids": booking_ids,
    }


def update_admin_payout(
    db: Session,
    admin_user: Dict[str, Any],
    payout_id: Any,
    status: str,
    payment_method: Optional[str] = None,
    transaction_reference: Optional[str] = None,
    payment_reference: Optional[str] = None,
    admin_note: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    Route: api/v1/admin/update_payout
    """
    admin_id = int(admin_user["id"])

    try:
        pid = int(payout_id)
    except (ValueError, TypeError):
        pid = 0

    status_clean = str(status or "").strip().lower()
    if not pid or status_clean not in ["pending", "processing", "paid", "failed"]:
        raise APIException("Payout id and valid status are required", status_code=400)

    old_row = db.execute(
        text(
            "SELECT id, caretaker_user_id, amount, gross_customer_amount, total_caretaker_earnings, "
            "       total_platform_commission, week_start, week_end, status, payment_method, "
            "       transaction_reference, payment_reference, admin_note, settled_by, settled_at, "
            "       created_at, updated_at "
            "FROM caretaker_payouts "
            "WHERE id = :id"
        ),
        {"id": pid},
    ).mappings().first()

    if not old_row:
        raise APIException("Payout not found", status_code=404)

    old_dict = dict(old_row)

    tx_ref = (transaction_reference or payment_reference or "").strip()
    pay_ref = (payment_reference or transaction_reference or "").strip()
    pay_method = (payment_method or "").strip()
    note = (admin_note or "").strip()

    try:
        settled_by = admin_id if status_clean == "paid" else None
        settled_at = datetime.now() if status_clean == "paid" else None

        db.execute(
            text(
                "UPDATE caretaker_payouts "
                "SET status = :status, "
                "    payment_method = :pm, "
                "    transaction_reference = :tx, "
                "    payment_reference = :pr, "
                "    admin_note = :note, "
                "    settled_by = :settled_by, "
                "    settled_at = :settled_at "
                "WHERE id = :id"
            ),
            {
                "status": status_clean,
                "pm": pay_method or None,
                "tx": tx_ref or None,
                "pr": pay_ref or None,
                "note": note or None,
                "settled_by": settled_by,
                "settled_at": settled_at,
                "id": pid,
            },
        )

        if status_clean == "paid":
            db.execute(
                text(
                    "UPDATE bookings b "
                    "INNER JOIN caretaker_payout_items pi ON pi.booking_id = b.id "
                    "SET b.payout_status = 'paid', "
                    "    b.payout_paid_at = :settled_at, "
                    "    b.payout_id = :payout_id "
                    "WHERE pi.payout_id = :payout_id "
                    "  AND b.payout_status = 'ready_for_payout'"
                ),
                {"settled_at": settled_at, "payout_id": pid},
            )

        db.commit()
    except APIException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Payout update failed: {e}")
        raise APIException("Payout update failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_payout",
        entity_type="caretaker_payout",
        entity_id=pid,
        old_values=old_dict,
        new_values={
            "status": status_clean,
            "payment_method": pay_method or None,
            "transaction_reference": tx_ref or None,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if status_clean == "paid" and str(old_dict.get("status") or "").lower() != "paid":
        notify_payout_processed(db, pid)


def refresh_admin_payout_eligibility(
    db: Session,
    admin_user: Dict[str, Any],
    booking_id: Optional[Any] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, int]:
    """
    Route: api/v1/admin/refresh_payout_eligibility
    """
    admin_id = int(admin_user["id"])

    bid = None
    if booking_id is not None and str(booking_id).strip() != "":
        try:
            bid = int(booking_id)
        except ValueError:
            bid = None

    counts = payout_refresh_eligibility(db, booking_id=bid)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="refresh_payout_eligibility",
        entity_type="booking",
        entity_id=bid,
        old_values=None,
        new_values=counts,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return counts


def get_admin_reports_summary(db: Session) -> Dict[str, Any]:
    """
    Route: api/v1/admin/reports_summary
    """
    try:
        # 1. Revenue summary
        rev_row = db.execute(
            text(
                "SELECT "
                "    COALESCE(SUM(CASE WHEN status = 'success' THEN amount ELSE 0 END), 0) AS total_revenue, "
                "    COALESCE(SUM(CASE WHEN status = 'success' AND DATE_FORMAT(created_at, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m') THEN amount ELSE 0 END), 0) AS this_month_revenue, "
                "    COALESCE(SUM(CASE WHEN status = 'success' AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1) THEN amount ELSE 0 END), 0) AS this_week_revenue "
                "FROM payments"
            )
        ).mappings().first()
        revenue = {k: round(float(v or 0), 2) for k, v in dict(rev_row or {}).items()}

        # 2. Platform commission summary
        comm_row = db.execute(
            text(
                "SELECT "
                "    COALESCE(SUM(platform_commission_amount), 0) AS total_platform_commission, "
                "    COALESCE(SUM(CASE WHEN DATE_FORMAT(completed_at, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m') THEN platform_commission_amount ELSE 0 END), 0) AS this_month_commission "
                "FROM bookings "
                "WHERE status = 'completed'"
            )
        ).mappings().first()
        commission = {k: round(float(v or 0), 2) for k, v in dict(comm_row or {}).items()}

        # 3. Booking breakdown
        bk_row = db.execute(
            text(
                "SELECT "
                "    COUNT(*) AS total, "
                "    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending, "
                "    SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) AS accepted, "
                "    SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress, "
                "    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed, "
                "    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled, "
                "    SUM(CASE WHEN status = 'declined' THEN 1 ELSE 0 END) AS declined "
                "FROM bookings"
            )
        ).mappings().first()
        booking_stats = {k: int(v or 0) for k, v in dict(bk_row or {}).items()}

        # 4. User breakdown
        usr_row = db.execute(
            text(
                "SELECT "
                "    COUNT(*) AS total, "
                "    SUM(CASE WHEN role = 'family' THEN 1 ELSE 0 END) AS family, "
                "    SUM(CASE WHEN role = 'caretaker' THEN 1 ELSE 0 END) AS caretaker, "
                "    SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) AS admin, "
                "    SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS inactive, "
                "    SUM(CASE WHEN DATE_FORMAT(created_at, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m') THEN 1 ELSE 0 END) AS new_this_month "
                "FROM users"
            )
        ).mappings().first()
        user_stats = {k: int(v or 0) for k, v in dict(usr_row or {}).items()}

        # 5. Payout summary
        payout_row = db.execute(
            text(
                "SELECT "
                "    COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS total_paid, "
                "    COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) AS total_pending, "
                "    COUNT(CASE WHEN status = 'paid' THEN 1 END) AS paid_count, "
                "    COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending_count "
                "FROM caretaker_payouts"
            )
        ).mappings().first()
        # In $payout_stats is in the float-rounded group
        payout_stats = {k: round(float(v or 0), 2) for k, v in dict(payout_row or {}).items()}

        # 6. SOS summary
        sos_row = db.execute(
            text(
                "SELECT "
                "    COUNT(*) AS total, "
                "    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_alerts, "
                "    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved "
                "FROM sos_alerts"
            )
        ).mappings().first()
        sos_stats = {k: int(v or 0) for k, v in dict(sos_row or {}).items()}

        # 7. Complaint summary
        comp_row = db.execute(
            text(
                "SELECT "
                "    COUNT(*) AS total, "
                "    SUM(CASE WHEN status IN ('open','in_review') THEN 1 ELSE 0 END) AS pending, "
                "    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved, "
                "    SUM(CASE WHEN status = 'declined' THEN 1 ELSE 0 END) AS declined "
                "FROM complaints"
            )
        ).mappings().first()
        complaint_stats = {k: int(v or 0) for k, v in dict(comp_row or {}).items()}

        return {
            "revenue": revenue,
            "commission": commission,
            "bookings": booking_stats,
            "users": user_stats,
            "payouts": payout_stats,
            "sos_alerts": sos_stats,
            "complaints": complaint_stats,
        }
    except Exception as e:
        logger.error(f"Reports summary error: {e}")
        raise APIException("Failed to generate reports summary", status_code=500)

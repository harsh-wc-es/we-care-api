"""
WeCare — Caretaker Earnings Service (Part 12A)

Migrated from helpers/caretaker_earnings and helpers/payout.
Provides:
- caretaker_money
- format_visit_label
- get_next_payout_date
- payout_refresh_eligibility
- get_caretaker_earnings_summary
- get_caretaker_recent_earnings
- get_caretaker_earnings_history
"""

import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException


def caretaker_money(value: Any) -> float:
    """Route: caretaker_money() — helpers/caretaker_earnings L6-9"""
    try:
        return round(float(value or 0), 2)
    except (ValueError, TypeError):
        return 0.0


def _parse_time_parts(val: Any) -> Optional[tuple[int, int]]:
    """Helper to parse time parts (hour, minute) from datetime, time, timedelta, or string."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.hour, val.minute
    if hasattr(val, "hour") and hasattr(val, "minute"):
        return val.hour, val.minute
    if hasattr(val, "total_seconds"):
        total_sec = int(val.total_seconds())
        return (total_sec // 3600) % 24, (total_sec % 3600) // 60

    val_str = str(val).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt.hour, dt.minute
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?", val_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def format_visit_label(start_time: Any, end_time: Any) -> Optional[str]:
    """Route: format_visit_label() — helpers/caretaker_earnings L11-21"""
    if not start_time or not end_time:
        return None

    st_parts = _parse_time_parts(start_time)
    et_parts = _parse_time_parts(end_time)
    if not st_parts or not et_parts:
        return f"{start_time} - {end_time}"

    def _fmt(hour: int, minute: int) -> str:
        # date("g:i A") -> e.g. "9:00 AM" (12-hour without leading zero, uppercase AM/PM)
        h12 = hour % 12 or 12
        ampm = "AM" if hour < 12 else "PM"
        return f"{h12}:{minute:02d} {ampm}"

    return f"{_fmt(*st_parts)} - {_fmt(*et_parts)}"


def get_next_payout_date(reference_date: Optional[datetime] = None) -> str:
    """
    Route: get_next_payout_date() — helpers/caretaker_earnings L23-33

    Next payout date logic:
    If today is Monday or Tuesday (ISO weekday <= 2):
        Tuesday this week
    Else:
        Tuesday next week
    """
    now = reference_date or datetime.now()
    weekday = now.isoweekday()  # 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat, 7=Sun

    if weekday <= 2:
        # Tuesday this week
        next_tue = now + timedelta(days=(2 - weekday))
    else:
        # Tuesday next week
        next_tue = now + timedelta(days=(9 - weekday))

    return next_tue.strftime("%Y-%m-%d")


def payout_refresh_eligibility(db: Session, booking_id: Optional[int] = None) -> Dict[str, int]:
    """
    Route: payout_refresh_eligibility() — helpers/payout L31-87

    Refreshes payout_status across completed bookings:
    - hold: 24h completion hold is active
    - disputed: complaint, open SOS, pending checklist, or refund exists
    - ready_for_payout: hold expired and no issue exists
    """
    where = "b.status = 'completed' AND b.payout_status <> 'paid'"
    params: Dict[str, Any] = {}

    if booking_id is not None:
        where += " AND b.id = :booking_id"
        params["booking_id"] = int(booking_id)

    issue_query = (
        "EXISTS (SELECT 1 FROM complaints c WHERE c.booking_id = b.id) AS has_complaint, "
        "EXISTS (SELECT 1 FROM sos_alerts s WHERE s.booking_id = b.id) AS has_sos_incident, "
        "EXISTS (SELECT 1 FROM booking_checklist_tasks t WHERE t.booking_id = b.id AND t.status <> 'completed') AS has_pending_checklist, "
        "EXISTS (SELECT 1 FROM payments p WHERE p.booking_id = b.id AND p.status = 'refunded') AS has_refund, "
        "(b.payment_status = 'refunded') AS booking_refunded"
    )

    rows = db.execute(
        text(
            f"SELECT b.id, b.payout_hold_until, {issue_query} "
            f"FROM bookings b "
            f"WHERE {where}"
        ),
        params,
    ).fetchall()

    counts = {
        "ready_for_payout": 0,
        "hold": 0,
        "disputed": 0,
    }

    now = datetime.now()

    for r in rows:
        mapping = dict(r._mapping)
        has_issue = bool(
            int(mapping.get("has_complaint") or 0) == 1
            or int(mapping.get("has_sos_incident") or 0) == 1
            or int(mapping.get("has_pending_checklist") or 0) == 1
            or int(mapping.get("has_refund") or 0) == 1
            or int(mapping.get("booking_refunded") or 0) == 1
        )

        hold_until = mapping.get("payout_hold_until")
        if isinstance(hold_until, str):
            try:
                hold_until = datetime.fromisoformat(hold_until)
            except Exception:
                hold_until = None

        if has_issue:
            new_status = "disputed"
        elif not hold_until or (isinstance(hold_until, datetime) and hold_until > now):
            new_status = "hold"
        else:
            new_status = "ready_for_payout"

        db.execute(
            text("UPDATE bookings SET payout_status = :status WHERE id = :id AND payout_status <> 'paid'"),
            {"status": new_status, "id": mapping["id"]},
        )
        if new_status in counts:
            counts[new_status] += 1

    # Invalidate non-completed bookings
    db.execute(
        text(
            "UPDATE bookings "
            "SET payout_status = 'not_applicable' "
            "WHERE status <> 'completed' "
            "  AND payout_status <> 'paid' "
            "  AND payout_status <> 'not_applicable'"
        )
    )
    db.commit()

    return counts


def caretaker_earning_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Route: caretaker_earning_row() — helpers/caretaker_earnings L35-49"""
    completed_at = row.get("completed_at")
    payout_paid_at = row.get("payout_paid_at")

    return {
        "booking_id": int(row["booking_id"]),
        "patient_name": row.get("patient_name") or "",
        "booking_date": str(row["booking_date"]) if row.get("booking_date") else None,
        "start_time": str(row["start_time"]) if row.get("start_time") else None,
        "end_time": str(row["end_time"]) if row.get("end_time") else None,
        "visit_label": format_visit_label(row.get("start_time"), row.get("end_time")),
        "earning_amount": caretaker_money(row.get("earning_amount")),
        "payout_status": row.get("payout_status") or "",
        "completed_at": completed_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(completed_at, "strftime") else (str(completed_at) if completed_at else None),
        "payout_paid_at": payout_paid_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(payout_paid_at, "strftime") else (str(payout_paid_at) if payout_paid_at else None),
    }


def get_caretaker_earnings_summary(db: Session, caretaker_user_id: int) -> Dict[str, Any]:
    """Route: get_caretaker_earnings_summary() — helpers/caretaker_earnings L51-82"""
    payout_refresh_eligibility(db)

    row = db.execute(
        text(
            "SELECT "
            "  SUM(CASE WHEN b.status = 'completed' AND b.payout_status IN ('hold','ready_for_payout','paid','disputed') THEN b.caretaker_earning_amount ELSE 0 END) AS total_earnings, "
            "  SUM(CASE WHEN b.status = 'completed' AND COALESCE(b.completed_at, b.updated_at, b.created_at) >= DATE_SUB(NOW(), INTERVAL 7 DAY) THEN b.caretaker_earning_amount ELSE 0 END) AS this_week_earnings, "
            "  SUM(CASE WHEN b.status = 'completed' AND DATE_FORMAT(COALESCE(b.completed_at, b.updated_at, b.created_at), '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m') THEN b.caretaker_earning_amount ELSE 0 END) AS this_month_earnings, "
            "  SUM(CASE WHEN b.status = 'completed' AND b.payout_status = 'ready_for_payout' THEN b.caretaker_earning_amount ELSE 0 END) AS ready_for_payout, "
            "  SUM(CASE WHEN b.status = 'completed' AND b.payout_status = 'hold' THEN b.caretaker_earning_amount ELSE 0 END) AS hold_earnings, "
            "  SUM(CASE WHEN b.status = 'completed' AND b.payout_status = 'paid' THEN b.caretaker_earning_amount ELSE 0 END) AS paid_earnings, "
            "  SUM(CASE WHEN b.status = 'completed' AND b.payout_status = 'disputed' THEN b.caretaker_earning_amount ELSE 0 END) AS disputed_earnings "
            "FROM bookings b "
            "WHERE b.caretaker_user_id = :uid"
        ),
        {"uid": int(caretaker_user_id)},
    ).fetchone()

    mapping = dict(row._mapping) if row else {}

    return {
        "currency": "INR",
        "total_earnings": caretaker_money(mapping.get("total_earnings")),
        "this_week_earnings": caretaker_money(mapping.get("this_week_earnings")),
        "this_month_earnings": caretaker_money(mapping.get("this_month_earnings")),
        "ready_for_payout": caretaker_money(mapping.get("ready_for_payout")),
        "hold_earnings": caretaker_money(mapping.get("hold_earnings")),
        "paid_earnings": caretaker_money(mapping.get("paid_earnings")),
        "disputed_earnings": caretaker_money(mapping.get("disputed_earnings")),
        "next_payout_date": get_next_payout_date(),
        "payout_note": "Weekly payouts are processed by admin.",
    }


def get_caretaker_recent_earnings(db: Session, caretaker_user_id: int, limit: int = 3) -> List[Dict[str, Any]]:
    """Route: get_caretaker_recent_earnings() — helpers/caretaker_earnings L84-110"""
    clamped_limit = min(10, max(1, int(limit)))

    rows = db.execute(
        text(
            "SELECT "
            "  b.id AS booking_id, "
            "  p.patient_name, "
            "  b.booking_date, "
            "  b.start_time, "
            "  b.end_time, "
            "  b.caretaker_earning_amount AS earning_amount, "
            "  b.payout_status, "
            "  b.completed_at, "
            "  b.payout_paid_at "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE b.caretaker_user_id = :uid "
            "  AND b.status = 'completed' "
            "  AND b.payout_status IN ('hold','ready_for_payout','paid','disputed') "
            "ORDER BY COALESCE(b.completed_at, b.updated_at, b.created_at) DESC, b.id DESC "
            "LIMIT :limit"
        ),
        {"uid": int(caretaker_user_id), "limit": clamped_limit},
    ).fetchall()

    return [caretaker_earning_row(dict(r._mapping)) for r in rows]


def get_caretaker_earnings_history(
    db: Session,
    caretaker_user_id: int,
    page_raw: Any = 1,
    limit_raw: Any = 20,
    status: Optional[str] = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: get_caretaker_earnings_history() — helpers/caretaker_earnings L112-196
    """
    # CRITICAL LEGACY QUIRK: payout_refresh_eligibility() runs BEFORE validation
    payout_refresh_eligibility(db)

    # Coerce pagination integers
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

    page = max(1, _coerce_int(page_raw, 1))
    limit = min(100, max(1, _coerce_int(limit_raw, 20)))
    offset = (page - 1) * limit

    status_clean = str(status or "all").strip().lower()
    start_date_clean = str(start_date or "").strip()
    end_date_clean = str(end_date or "").strip()

    if status_clean not in ["hold", "ready_for_payout", "paid", "disputed", "all"]:
        raise APIException(
            message="Invalid status",
            errors={"status": ["Allowed values: hold, ready_for_payout, paid, disputed, all"]},
            status_code=400,
        )

    for field, val in [("start_date", start_date_clean), ("end_date", end_date_clean)]:
        if val != "" and not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
            raise APIException(
                message="Invalid date filter",
                errors={field: ["Use YYYY-MM-DD format"]},
                status_code=400,
            )

    where = (
        "b.caretaker_user_id = :uid "
        "AND b.status = 'completed' "
        "AND b.payout_status IN ('hold','ready_for_payout','paid','disputed')"
    )
    params: Dict[str, Any] = {"uid": int(caretaker_user_id)}

    if status_clean != "all":
        where += " AND b.payout_status = :pstatus"
        params["pstatus"] = status_clean

    if start_date_clean != "":
        where += " AND b.booking_date >= :start_date"
        params["start_date"] = start_date_clean

    if end_date_clean != "":
        where += " AND b.booking_date <= :end_date"
        params["end_date"] = end_date_clean

    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM bookings b WHERE {where}"),
        params,
    ).fetchone()
    total = int(count_row[0]) if count_row else 0

    rows = db.execute(
        text(
            f"SELECT "
            f"  b.id AS booking_id, "
            f"  p.patient_name, "
            f"  b.booking_date, "
            f"  b.start_time, "
            f"  b.end_time, "
            f"  b.caretaker_earning_amount AS earning_amount, "
            f"  b.payout_status, "
            f"  b.completed_at, "
            f"  b.payout_paid_at "
            f"FROM bookings b "
            f"LEFT JOIN patient_details p ON p.id = b.patient_id "
            f"WHERE {where} "
            f"ORDER BY COALESCE(b.completed_at, b.updated_at, b.created_at) DESC, b.id DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    return {
        "items": [caretaker_earning_row(dict(r._mapping)) for r in rows],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0,
        },
    }

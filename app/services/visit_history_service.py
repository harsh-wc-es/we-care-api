"""
WeCare — Caretaker Visit History Service (Part 12A)

Migrated from helpers/visit_history and api/v1/caretaker/visit_history.
Provides:
- visit_history_status_color
- visit_history_group_label
- visit_history_event_datetime
- get_caretaker_visit_history
"""

import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.caretaker_earnings_service import format_visit_label


def visit_history_status_color(status: str) -> str:
    """Route: visit_history_status_color() — helpers/visit_history L22-38"""
    status = str(status or "").strip().lower()
    if status == "completed":
        return "green"
    if status in ["cancelled", "declined"]:
        return "red"
    if status in ["accepted", "in_progress"]:
        return "orange"
    return "gray"


def visit_history_group_label(datetime_val: Any) -> str:
    """
    Route: visit_history_group_label() — helpers/visit_history L40-67

    Grouping rules:
    - Today: event date == today
    - Yesterday: event date == today - 1 day
    - This Week: ISO week (oW) matches current ISO week
    - Earlier: everything else or missing date
    """
    if not datetime_val:
        return "Earlier"

    dt: Optional[datetime] = None
    if isinstance(datetime_val, datetime):
        dt = datetime_val
    else:
        try:
            dt_str = str(datetime_val).strip()
            if len(dt_str) >= 19:
                dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
            elif len(dt_str) == 10:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
            else:
                dt = datetime.fromisoformat(dt_str)
        except Exception:
            return "Earlier"

    if dt is None:
        return "Earlier"

    now = datetime.now()
    today_date = now.date()
    event_date = dt.date()

    if event_date == today_date:
        return "Today"

    if event_date == (today_date - timedelta(days=1)):
        return "Yesterday"

    # date("oW", $timestamp) === date("oW") -> ISO week comparison
    if dt.isocalendar()[:2] == now.isocalendar()[:2]:
        return "This Week"

    return "Earlier"


def visit_history_event_datetime(row: Dict[str, Any]) -> Optional[Any]:
    """Route: visit_history_event_datetime() — helpers/visit_history L205-221"""
    status = str(row.get("status") or "").strip().lower()

    if status == "completed":
        return row.get("completed_at") or row.get("check_out_time") or row.get("updated_at")

    if status == "cancelled":
        return row.get("cancelled_at") or row.get("updated_at")

    if status == "declined":
        return row.get("responded_at") or row.get("updated_at")

    return row.get("updated_at") or row.get("created_at")


def get_caretaker_visit_history(
    db: Session,
    caretaker_user_id: int,
    page_raw: Any = 1,
    limit_raw: Any = 20,
    status_param: Optional[str] = "",
    start_date: Optional[str] = "",
    end_date: Optional[str] = "",
    patient_name: Optional[str] = "",
) -> Dict[str, Any]:
    """
    Route: api/v1/caretaker/visit_history L13-154
    """
    # Coerce pagination integers (integer coercion parity)
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
    limit = max(1, min(100, _coerce_int(limit_raw, 20)))
    offset = (page - 1) * limit

    # Status parsing & validation
    raw_status = str(status_param or "").strip().lower()
    allowed_statuses = ["completed", "cancelled", "declined"]

    if raw_status in ["", "default"]:
        statuses = ["completed", "cancelled"]
    elif raw_status == "all":
        statuses = allowed_statuses
    else:
        parts = [p.strip() for p in raw_status.split(",") if p.strip()]
        statuses = parts
        for s in statuses:
            if s not in allowed_statuses:
                raise APIException(
                    message="Validation failed",
                    errors={"status": ["Status must be completed, cancelled, declined, or all"]},
                    status_code=400,
                )

    if not statuses:
        raise APIException(
            message="Validation failed",
            errors={"status": ["At least one valid status is required"]},
            status_code=400,
        )

    # Date validation
    start_date_clean = str(start_date or "").strip()
    end_date_clean = str(end_date or "").strip()
    patient_name_clean = str(patient_name or "").strip()

    for field, val in [("start_date", start_date_clean), ("end_date", end_date_clean)]:
        if val != "" and not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
            raise APIException(
                message="Validation failed",
                errors={field: ["Date must be in YYYY-MM-DD format"]},
                status_code=400,
            )

    # Build WHERE clause
    where_conditions = ["b.caretaker_user_id = :uid"]
    params: Dict[str, Any] = {"uid": int(caretaker_user_id)}

    # Status IN placeholders
    status_clauses = []
    for idx, s in enumerate(statuses):
        param_name = f"st_{idx}"
        status_clauses.append(f":{param_name}")
        params[param_name] = s

    where_conditions.append(f"b.status IN ({', '.join(status_clauses)})")

    if start_date_clean != "":
        where_conditions.append("b.booking_date >= :start_date")
        params["start_date"] = start_date_clean

    if end_date_clean != "":
        where_conditions.append("b.booking_date <= :end_date")
        params["end_date"] = end_date_clean

    if patient_name_clean != "":
        where_conditions.append("p.patient_name LIKE :patient_name")
        params["patient_name"] = f"%{patient_name_clean}%"

    where_sql = " AND ".join(where_conditions)

    count_row = db.execute(
        text(
            f"SELECT COUNT(*) "
            f"FROM bookings b "
            f"LEFT JOIN patient_details p ON p.id = b.patient_id "
            f"WHERE {where_sql}"
        ),
        params,
    ).fetchone()
    total = int(count_row[0]) if count_row else 0

    rows = db.execute(
        text(
            f"SELECT b.id AS booking_id, b.status, b.booking_date, b.start_time, b.end_time, "
            f"       b.completed_at, b.cancelled_at, b.responded_at, b.created_at, b.updated_at, "
            f"       p.patient_name, "
            f"       vt.id AS visit_id, vt.check_out_time "
            f"FROM bookings b "
            f"LEFT JOIN patient_details p ON p.id = b.patient_id "
            f"LEFT JOIN visit_tracking vt "
            f"  ON vt.id = ( "
            f"    SELECT vt2.id "
            f"    FROM visit_tracking vt2 "
            f"    WHERE vt2.booking_id = b.id "
            f"      AND vt2.caretaker_user_id = b.caretaker_user_id "
            f"    ORDER BY vt2.id DESC "
            f"    LIMIT 1 "
            f"  ) "
            f"WHERE {where_sql} "
            f"ORDER BY "
            f"  CASE "
            f"    WHEN b.status = 'completed' THEN COALESCE(b.completed_at, vt.check_out_time, b.updated_at) "
            f"    WHEN b.status = 'cancelled' THEN COALESCE(b.cancelled_at, b.updated_at) "
            f"    WHEN b.status = 'declined' THEN COALESCE(b.responded_at, b.updated_at) "
            f"    ELSE b.updated_at "
            f"  END DESC, "
            f"  b.id DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    grouped: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        row = dict(r._mapping)
        status = str(row.get("status") or "").strip().lower()
        event_at = visit_history_event_datetime(row)
        label = visit_history_group_label(event_at)

        if label not in grouped:
            grouped[label] = {
                "label": label,
                "items": [],
            }

        def _format_event_time(val: Any) -> Optional[str]:
            if not val:
                return None
            if hasattr(val, "strftime"):
                return val.strftime("%Y-%m-%d %H:%M:%S")
            return str(val)

        formatted_event = _format_event_time(event_at)

        item = {
            "booking_id": int(row["booking_id"]),
            "visit_id": int(row["visit_id"]) if row.get("visit_id") is not None else None,
            "patient_name": str(row.get("patient_name") or ""),
            "status": status,
            "status_color": visit_history_status_color(status),
            "display_time": format_visit_label(row.get("start_time"), row.get("end_time")),
            "completed_at": formatted_event if status == "completed" else None,
            "cancelled_at": formatted_event if status == "cancelled" else None,
            "declined_at": formatted_event if status == "declined" else None,
        }

        grouped[label]["items"].append(item)

    return {
        "groups": list(grouped.values()),
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0,
        },
    }

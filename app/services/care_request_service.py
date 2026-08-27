"""
WeCare — Care Request Service

Mirrors helpers/care_requests.
Formatters and helpers for care requests and bookings.
"""

from datetime import date, datetime, time
from typing import Any, Dict, Optional


def care_request_display_time(start_time: Any, end_time: Any) -> str:
    """
    Route: care_request_display_time() — helpers/care_requests L3-10
    e.g., '09:00:00', '13:00:00' -> '9:00 AM - 1:00 PM'
    """
    if not start_time or not end_time:
        return ""

    try:
        if isinstance(start_time, time):
            s_dt = datetime.combine(date.today(), start_time)
        elif isinstance(start_time, str):
            # Parse time string
            parts = str(start_time).strip().split(":")
            s_dt = datetime.combine(
                date.today(),
                time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0),
            )
        elif isinstance(start_time, datetime):
            s_dt = start_time
        else:
            return ""

        if isinstance(end_time, time):
            e_dt = datetime.combine(date.today(), end_time)
        elif isinstance(end_time, str):
            parts = str(end_time).strip().split(":")
            e_dt = datetime.combine(
                date.today(),
                time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0),
            )
        elif isinstance(end_time, datetime):
            e_dt = end_time
        else:
            return ""

        # date("g:i A") -> e.g. 9:00 AM, 1:00 PM (no leading zero on hour)
        s_str = s_dt.strftime("%I:%M %p").lstrip("0")
        e_str = e_dt.strftime("%I:%M %p").lstrip("0")
        return f"{s_str} - {e_str}"
    except Exception:
        return ""


def care_request_location_short(address: Any) -> str:
    """
    Route: care_request_location_short() — helpers/care_requests L12-21
    Returns the first comma-separated segment of the address.
    """
    if address is None:
        return ""
    addr_str = str(address).strip()
    if not addr_str:
        return ""

    parts = [p.strip() for p in addr_str.split(",") if p.strip()]
    return parts[0] if parts else addr_str


def care_request_text(value: Any) -> str:
    """
    Route: care_request_text() — helpers/care_requests L23-26
    """
    return "" if value is None else str(value)


def care_request_date(value: Any) -> str:
    """
    Route: care_request_date() — helpers/care_requests L28-31
    Returns 'YYYY-MM-DD' or ''
    """
    if not value:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            return ""
        try:
            # If string contains time or ISO format
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return val_str[:10]
    return ""


def care_request_time(value: Any) -> str:
    """
    Route: care_request_time() — helpers/care_requests L33-36
    Returns 'HH:MM:SS' or ''
    """
    if not value:
        return ""
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    if isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            return ""
        if len(val_str) == 8 and val_str.count(":") == 2:
            return val_str
        try:
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return val_str
    return ""


def care_request_datetime(value: Any) -> str:
    """
    Route: care_request_datetime() — helpers/care_requests L38-46
    Returns ISO 8601 (DATE_ATOM, e.g. 2026-08-24T18:00:00+00:00) or ''
    """
    if not value:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        return value.isoformat()
    if isinstance(value, date):
        return datetime.combine(value, time.min).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            return ""
        try:
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            return dt.isoformat()
        except Exception:
            return val_str
    return ""


def care_request_priority(row: Dict[str, Any]) -> str:
    """
    Route: care_request_priority() — helpers/care_requests L48-52
    """
    priority = str(row.get("request_priority") or "normal").lower()
    return priority if priority in ("normal", "high", "urgent") else "normal"


def care_request_list_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route: care_request_list_item() — helpers/care_requests L54-78
    """
    priority = care_request_priority(row)
    start = care_request_time(row.get("start_time"))
    end = care_request_time(row.get("end_time"))
    patient_name = care_request_text(row.get("patient_name") or "")

    return {
        "booking_id": int(row["booking_id"]),
        "request_id": int(row["booking_id"]),
        "patient_name": patient_name,
        "elder_name": patient_name,
        "location_short": care_request_location_short(row.get("address")),
        "visit_date": care_request_date(row.get("booking_date")),
        "start_time": start,
        "end_time": end,
        "display_time": care_request_display_time(start, end),
        "service_type": care_request_text(row.get("service_type")),
        "care_type": care_request_text(row.get("care_type")),
        "priority": priority,
        "is_urgent": priority == "urgent",
        "status": str(care_request_text(row.get("status"))).lower(),
        "created_at": care_request_datetime(row.get("created_at")),
    }


def care_request_decline_reasons() -> Dict[str, str]:
    """
    Route: care_request_decline_reasons() — helpers/care_requests L80-89
    """
    return {
        "not_available": "Not available",
        "location_too_far": "Location too far",
        "not_comfortable_with_care": "Not comfortable with care",
        "personal_reasons": "Personal reasons",
        "other": "Other",
    }


def care_request_parse_coordinates(row: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Route: care_request_parse_coordinates() — helpers/care_requests L91-97
    """
    lat = row.get("location_latitude")
    lng = row.get("location_longitude")
    return {
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lng) if lng is not None else None,
    }

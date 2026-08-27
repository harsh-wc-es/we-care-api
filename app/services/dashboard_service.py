"""
WeCare — Dashboard Service (Part 11)

Migrates api/v1/dashboard/*.
Handles Admin, Caretaker, and Family dashboard aggregation metrics and queries.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.availability_service import (
    caretaker_availability_payload,
    touch_caretaker_presence,
)
from app.services.care_request_service import (
    care_request_date,
    care_request_display_time,
    care_request_location_short,
    care_request_parse_coordinates,
    care_request_text,
    care_request_time,
)

logger = logging.getLogger(__name__)


# ============================================================
# Admin Dashboard
# ============================================================


def get_admin_dashboard(db: Session, admin_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route: api/v1/dashboard/admin_dashboard
    """
    try:
        # ── Core counts ──
        total_users = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        total_family = db.execute(text("SELECT COUNT(*) FROM users WHERE role='family'")).scalar() or 0
        total_caretakers = db.execute(text("SELECT COUNT(*) FROM users WHERE role='caretaker'")).scalar() or 0
        total_bookings = db.execute(text("SELECT COUNT(*) FROM bookings")).scalar() or 0

        # ── Primary KPIs (operational urgency) ──
        active_sos = db.execute(text("SELECT COUNT(*) FROM sos_alerts WHERE status='open'")).scalar() or 0
        active_visits = db.execute(text("SELECT COUNT(*) FROM bookings WHERE status='in_progress'")).scalar() or 0
        pending_verification = (
            db.execute(text("SELECT COUNT(*) FROM caretaker_profiles WHERE verification_status='pending'")).scalar()
            or 0
        )
        payout_holds = db.execute(text("SELECT COUNT(*) FROM bookings WHERE payout_status='hold'")).scalar() or 0
        pending_bookings = db.execute(text("SELECT COUNT(*) FROM bookings WHERE status='pending'")).scalar() or 0
        completed_bookings = db.execute(text("SELECT COUNT(*) FROM bookings WHERE status='completed'")).scalar() or 0

        # ── Secondary KPIs (operational awareness) ──
        complaints_pending = (
            db.execute(text("SELECT COUNT(*) FROM complaints WHERE status IN ('open','in_review')")).scalar() or 0
        )

        # Replacements — L30-36 try/catch fallback
        replacements_pending = 0
        try:
            replacements_pending = (
                db.execute(text("SELECT COUNT(*) FROM replacement_tickets WHERE status='open'")).scalar() or 0
            )
        except Exception:
            replacements_pending = 0

        # ── Recent activity (last 10 admin audit logs) — L39-51 try/catch fallback ──
        recent_activity: List[Dict[str, Any]] = []
        try:
            rows = db.execute(
                text(
                    "SELECT action, entity_type, entity_id, created_at "
                    "FROM admin_audit_logs "
                    "ORDER BY created_at DESC "
                    "LIMIT 10"
                )
            ).fetchall()
            for r in rows:
                action_str = str(r.action or "")
                entity_type_str = str(r.entity_type or "")
                entity_id_val = r.entity_id
                created_str = (
                    r.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if hasattr(r.created_at, "strftime")
                    else str(r.created_at or "")
                )

                formatted_action = action_str.replace("_", " ").capitalize()
                text_label = f"{formatted_action} {entity_type_str} #{entity_id_val}"

                recent_activity.append({
                    "action": action_str,
                    "entity_type": entity_type_str,
                    "entity_id": entity_id_val,
                    "created_at": created_str,
                    "text": text_label,
                    "type": entity_type_str,
                    "time": created_str,
                })
        except Exception:
            recent_activity = []

        # ── Active bookings for live operations table — L54-69 try/catch fallback ──
        live_operations: List[Dict[str, Any]] = []
        try:
            rows = db.execute(
                text(
                    "SELECT b.id, b.status AS booking_status, b.payout_status, b.start_time, "
                    "       p.patient_name, u.username AS caretaker_name "
                    "FROM bookings b "
                    "LEFT JOIN patient_details p ON b.patient_id = p.id "
                    "LEFT JOIN users u ON b.caretaker_user_id = u.id "
                    "WHERE b.status = 'in_progress' "
                    "ORDER BY b.start_time DESC "
                    "LIMIT 20"
                )
            ).fetchall()
            for r in rows:
                st_val = r.start_time
                start_time_str = str(st_val) if st_val is not None else None
                live_operations.append({
                    "id": int(r.id),
                    "booking_status": str(r.booking_status or ""),
                    "payout_status": str(r.payout_status or "") if r.payout_status is not None else None,
                    "start_time": start_time_str,
                    "patient_name": str(r.patient_name or "") if r.patient_name is not None else None,
                    "caretaker_name": str(r.caretaker_name or "") if r.caretaker_name is not None else None,
                })
        except Exception:
            live_operations = []

        return {
            "stats": {
                "active_sos": int(active_sos),
                "active_visits": int(active_visits),
                "pending_verification": int(pending_verification),
                "payout_holds": int(payout_holds),
                "complaints_pending": int(complaints_pending),
                "replacements_pending": int(replacements_pending),
                "pending_bookings": int(pending_bookings),
                "completed_bookings": int(completed_bookings),
            },
            "counts": {
                "total_users": int(total_users),
                "total_family_users": int(total_family),
                "total_caretakers": int(total_caretakers),
                "total_bookings": int(total_bookings),
            },
            "live_operations": live_operations,
            "recent_activity": recent_activity,
        }

    except Exception as e:
        logger.error(f"Admin dashboard query error: {e}")
        raise APIException(message="Failed to load dashboard data", status_code=500)


# ============================================================
# Caretaker Dashboard
# ============================================================


def _format_dashboard_visit(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Route: $formatDashboardVisit closure — api/v1/dashboard/caretaker_dashboard L80-110
    """
    if not row:
        return None

    start = care_request_time(row.get("start_time"))
    end = care_request_time(row.get("end_time"))
    coords = care_request_parse_coordinates(row)
    status_str = care_request_text(row.get("status") or "")

    return {
        "booking_id": int(row["booking_id"]),
        "visit_id": int(row["visit_id"]) if row.get("visit_id") is not None else None,
        "patient_name": care_request_text(row.get("patient_name") or ""),
        "service_type": care_request_text(row.get("service_type") or ""),
        "status": status_str,
        "visit_date": care_request_date(row.get("booking_date")),
        "start_time": start,
        "end_time": end,
        "display_time": care_request_display_time(start, end),
        "address": care_request_text(row.get("address") or ""),
        "location_short": care_request_location_short(row.get("address") or ""),
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "can_navigate": coords["latitude"] is not None and coords["longitude"] is not None,
        "can_call": True,
        "can_start_visit": status_str == "accepted",
        "requires_otp": status_str == "accepted",
        "sos_available": status_str in ("accepted", "in_progress"),
        "detail_endpoint": f"/api/v1/visit/view_visit?booking_id={int(row['booking_id'])}",
    }


def get_caretaker_dashboard(db: Session, caretaker_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route: api/v1/dashboard/caretaker_dashboard
    """
    user_id = int(caretaker_user["id"])

    # ── Realtime presence update (mandatory GET side effect) ──
    touch_caretaker_presence(db, user_id)

    # Profile details
    profile_row = db.execute(
        text(
            "SELECT full_name, verification_status, rating, total_reviews, is_available, availability_updated_at "
            "FROM caretaker_profiles "
            "WHERE user_id = :uid"
        ),
        {"uid": user_id},
    ).fetchone()
    profile = dict(profile_row._mapping) if profile_row else {}

    # Booking counts
    pending_requests = (
        db.execute(
            text("SELECT COUNT(*) FROM bookings WHERE caretaker_user_id = :uid AND status = 'pending'"),
            {"uid": user_id},
        ).scalar()
        or 0
    )
    accepted_bookings = (
        db.execute(
            text("SELECT COUNT(*) FROM bookings WHERE caretaker_user_id = :uid AND status = 'accepted'"),
            {"uid": user_id},
        ).scalar()
        or 0
    )
    completed_bookings = (
        db.execute(
            text("SELECT COUNT(*) FROM bookings WHERE caretaker_user_id = :uid AND status = 'completed'"),
            {"uid": user_id},
        ).scalar()
        or 0
    )

    # Earnings breakdown
    earnings_row = db.execute(
        text(
            "SELECT "
            "    SUM(CASE WHEN payout_status IN ('ready_for_payout', 'paid') THEN caretaker_earning_amount ELSE 0 END) AS total_earnings, "
            "    SUM(CASE WHEN payout_status = 'ready_for_payout' THEN caretaker_earning_amount ELSE 0 END) AS pending_earnings, "
            "    SUM(CASE WHEN payout_status = 'paid' THEN caretaker_earning_amount ELSE 0 END) AS paid_earnings, "
            "    SUM(CASE WHEN payout_status = 'hold' THEN caretaker_earning_amount ELSE 0 END) AS hold_earnings "
            "FROM bookings "
            "WHERE caretaker_user_id = :uid AND status = 'completed'"
        ),
        {"uid": user_id},
    ).fetchone()
    earnings = dict(earnings_row._mapping) if earnings_row else {}

    # Availability payload
    avail = caretaker_availability_payload(db, user_id) or {}

    # Today's visits count
    todays_visits = (
        db.execute(
            text(
                "SELECT COUNT(*) FROM bookings "
                "WHERE caretaker_user_id = :uid "
                "  AND booking_date = CURDATE() "
                "  AND status IN ('accepted','in_progress','completed')"
            ),
            {"uid": user_id},
        ).scalar()
        or 0
    )

    visit_select = (
        "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
        "       b.address, b.status, b.location_latitude, b.location_longitude, "
        "       p.patient_name, vt.id AS visit_id, vt.check_in_time "
        "FROM bookings b "
        "LEFT JOIN patient_details p ON p.id = b.patient_id "
        "LEFT JOIN visit_tracking vt "
        "  ON vt.booking_id = b.id "
        " AND vt.caretaker_user_id = b.caretaker_user_id "
    )

    # Active in-progress visit
    active_visit_row = db.execute(
        text(
            visit_select
            + "WHERE b.caretaker_user_id = :uid "
            "  AND b.status = 'in_progress' "
            "  AND vt.check_in_time IS NOT NULL "
            "  AND vt.check_out_time IS NULL "
            "ORDER BY vt.check_in_time DESC, b.id DESC "
            "LIMIT 1"
        ),
        {"uid": user_id},
    ).fetchone()

    active_visit = _format_dashboard_visit(dict(active_visit_row._mapping) if active_visit_row else None)

    # Upcoming visits (up to 5)
    upcoming_rows = db.execute(
        text(
            visit_select
            + "WHERE b.caretaker_user_id = :uid "
            "  AND b.status = 'accepted' "
            "  AND b.booking_date >= CURDATE() "
            "ORDER BY b.booking_date ASC, b.start_time ASC, b.id ASC "
            "LIMIT 5"
        ),
        {"uid": user_id},
    ).fetchall()

    upcoming_visits = [_format_dashboard_visit(dict(r._mapping)) for r in upcoming_rows]

    # Availability updated timestamp string
    up_at = profile.get("availability_updated_at")
    availability_updated_str = (
        up_at.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(up_at, "strftime")
        else (str(up_at) if up_at is not None else None)
    )

    caretaker_name = care_request_text(profile.get("full_name") or caretaker_user.get("username") or "")

    return {
        "verification_status": profile.get("verification_status") or "pending",
        "is_available": bool(int(profile.get("is_available") or 0) == 1),
        "availability_updated_at": availability_updated_str,
        "availability_reason": avail.get("availability_reason"),
        "has_active_visit": bool(avail.get("has_active_visit") or False),
        "availability_locked_by_admin": bool(avail.get("availability_locked_by_admin") or False),
        "rating": float(profile.get("rating") or 0),
        "total_reviews": int(profile.get("total_reviews") or 0),
        "pending_requests": int(pending_requests),
        "accepted_bookings": int(accepted_bookings),
        "completed_bookings": int(completed_bookings),
        "total_earnings": float(earnings.get("total_earnings") or 0.0),
        "pending_earnings": float(earnings.get("pending_earnings") or 0.0),
        "paid_earnings": float(earnings.get("paid_earnings") or 0.0),
        "hold_earnings": float(earnings.get("hold_earnings") or 0.0),
        "caretaker": {
            "id": user_id,
            "name": caretaker_name,
            "availability_status": avail.get("availability_reason"),
            "is_available": bool(avail.get("is_available") or False),
            "availability_locked_by_admin": bool(avail.get("availability_locked_by_admin") or False),
            "availability_reason": avail.get("availability_reason"),
        },
        "summary": {
            "todays_visits": int(todays_visits),
            "new_requests": int(pending_requests),
        },
        "active_visit": active_visit,
        "upcoming_visits": upcoming_visits,
        "new_requests": [],
        "capabilities": {
            "sos_available": active_visit is not None,
            "can_toggle_availability": not bool(avail.get("availability_locked_by_admin"))
            and not bool(avail.get("has_active_visit")),
        },
    }


# ============================================================
# Family Dashboard
# ============================================================


def get_family_dashboard(db: Session, family_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route: api/v1/dashboard/family_dashboard
    """
    user_id = int(family_user["id"])

    total_patients = (
        db.execute(
            text("SELECT COUNT(*) FROM patient_details WHERE family_user_id = :uid"),
            {"uid": user_id},
        ).scalar()
        or 0
    )
    total_bookings = (
        db.execute(
            text("SELECT COUNT(*) FROM bookings WHERE family_user_id = :uid"),
            {"uid": user_id},
        ).scalar()
        or 0
    )
    pending_bookings = (
        db.execute(
            text("SELECT COUNT(*) FROM bookings WHERE family_user_id = :uid AND status = 'pending'"),
            {"uid": user_id},
        ).scalar()
        or 0
    )
    completed_bookings = (
        db.execute(
            text("SELECT COUNT(*) FROM bookings WHERE family_user_id = :uid AND status = 'completed'"),
            {"uid": user_id},
        ).scalar()
        or 0
    )
    open_sos = (
        db.execute(
            text("SELECT COUNT(*) FROM sos_alerts WHERE user_id = :uid AND status = 'open'"),
            {"uid": user_id},
        ).scalar()
        or 0
    )

    return {
        "total_patients": int(total_patients),
        "total_bookings": int(total_bookings),
        "pending_bookings": int(pending_bookings),
        "completed_bookings": int(completed_bookings),
        "open_sos_alerts": int(open_sos),
    }

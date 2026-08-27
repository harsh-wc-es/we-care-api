"""
WeCare — Review and Feedback Service

Complete implementation of the Review & Feedback domain business logic mirroring Route: - api/v1/review/add_review
- api/v1/review/caretaker_reviews
- api/v1/caretaker/submit_feedback
- api/v1/admin/caretaker_feedback
- api/v1/admin/update_feedback_status
"""

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.audit_service import audit_log


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


def _strip_tags(text_val: Optional[str]) -> str:
    """Strips HTML tags matching strip_tags."""
    if not text_val:
        return ""
    clean = re.sub(r"<[^>]*>", "", str(text_val))
    return clean.strip()


def _parse_bool(value: Any) -> Optional[bool]:
    """Parses boolean value matching feedback_bool()."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes"):
            return True
        if normalized in ("0", "false", "no"):
            return False
    return None


def _format_dt(val: Any) -> Optional[str]:
    """Formats datetime values to standard MySQL representation."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def _admin_feedback_iso(val: Any) -> Optional[str]:
    """Formats datetime values to ISO 8601 representation (DATE_ATOM)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    try:
        dt = datetime.strptime(str(val), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except Exception:
        return str(val)


# ── Review Endpoints ─────────────────────────────────────────────────────────

def add_booking_review(
    db: Session,
    family_user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/review/add_review
    Submits a review for a completed booking by a family user and recalculates caretaker rating.
    """
    user_id = _get_user_id(family_user)

    booking_id = data.get("booking_id")
    raw_rating = data.get("rating")
    comment = data.get("comment")

    if booking_id is None or raw_rating is None or str(booking_id).strip() == "" or str(raw_rating).strip() == "":
        raise APIException("Booking id and rating are required", status_code=400)

    try:
        booking_id_int = int(booking_id)
        rating_int = int(raw_rating)
    except (ValueError, TypeError):
        raise APIException("Booking id and rating are required", status_code=400)

    if rating_int < 1 or rating_int > 5:
        raise APIException("Rating must be between 1 and 5", status_code=400)

    # Check completed booking ownership
    b_row = db.execute(
        text(
            "SELECT id, family_user_id, caretaker_user_id, status "
            "FROM bookings "
            "WHERE id = :bid AND family_user_id = :uid AND status = 'completed'"
        ),
        {"bid": booking_id_int, "uid": user_id},
    ).fetchone()

    if not b_row:
        raise APIException("Completed booking not found", status_code=404)

    caretaker_user_id = int(b_row.caretaker_user_id)

    # Check duplicate review
    rev_row = db.execute(
        text("SELECT id FROM reviews WHERE booking_id = :bid"),
        {"bid": booking_id_int},
    ).fetchone()

    if rev_row:
        raise APIException("Review already submitted for this booking", status_code=400)

    try:
        db.execute(
            text(
                "INSERT INTO reviews "
                "(booking_id, family_user_id, caretaker_user_id, rating, comment) "
                "VALUES (:bid, :fid, :cid, :rating, :comment)"
            ),
            {
                "bid": booking_id_int,
                "fid": user_id,
                "cid": caretaker_user_id,
                "rating": rating_int,
                "comment": comment,
            },
        )
        review_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())

        # Recalculate caretaker profile total_reviews and rating
        db.execute(
            text(
                "UPDATE caretaker_profiles cp "
                "SET "
                "    total_reviews = ( "
                "        SELECT COUNT(*) FROM reviews r WHERE r.caretaker_user_id = cp.user_id "
                "    ), "
                "    rating = ( "
                "        SELECT AVG(rating) FROM reviews r WHERE r.caretaker_user_id = cp.user_id "
                "    ) "
                "WHERE cp.user_id = :cid"
            ),
            {"cid": caretaker_user_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException("Review submission failed", status_code=500)

    return {"review_id": review_id}


def get_caretaker_reviews(
    db: Session,
    user: Any,
    caretaker_user_id: Optional[Union[int, str]] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/review/caretaker_reviews
    Retrieves reviews for a specified caretaker (or current user if caretaker).
    """
    user_id = _get_user_id(user)
    user_role = _get_user_role(user)

    if user_role == "caretaker":
        target_cid = user_id
    else:
        if caretaker_user_id is None or str(caretaker_user_id).strip() == "":
            raise APIException("Caretaker user id is required", status_code=400)
        try:
            target_cid = int(caretaker_user_id)
        except (ValueError, TypeError):
            raise APIException("Caretaker user id is required", status_code=400)

    page = max(1, int(page))
    limit = min(100, max(1, int(limit)))
    offset = (page - 1) * limit

    count_row = db.execute(
        text("SELECT COUNT(*) AS total FROM reviews WHERE caretaker_user_id = :cid"),
        {"cid": target_cid},
    ).fetchone()
    total = int(count_row.total) if count_row else 0

    rows = db.execute(
        text(
            "SELECT r.id, r.booking_id, r.family_user_id, r.caretaker_user_id, "
            "       r.rating, r.comment, r.created_at, u.username AS family_username "
            "FROM reviews r "
            "LEFT JOIN users u ON u.id = r.family_user_id "
            "WHERE r.caretaker_user_id = :cid "
            "ORDER BY r.id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"cid": target_cid, "limit": limit, "offset": offset},
    ).fetchall()

    items = []
    for r in rows:
        items.append({
            "id": int(r.id),
            "booking_id": int(r.booking_id),
            "family_user_id": int(r.family_user_id),
            "caretaker_user_id": int(r.caretaker_user_id),
            "rating": int(r.rating),
            "comment": r.comment,
            "created_at": _format_dt(r.created_at),
            "family_username": r.family_username,
        })

    total_pages = math.ceil(total / limit) if limit > 0 else 1

    return {
        "items": items,
        "reviews": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
        },
    }


# ── Caretaker Feedback Endpoints ─────────────────────────────────────────────

def submit_caretaker_feedback(
    db: Session,
    caretaker_user: Any,
    data: Dict[str, Any],
) -> None:
    """
    Route: api/v1/caretaker/submit_feedback
    Allows approved caretakers to submit internal feedback/suggestions.
    """
    user_id = _get_user_id(caretaker_user)

    # Check caretaker verification status
    cp_row = db.execute(
        text("SELECT verification_status FROM caretaker_profiles WHERE user_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).fetchone()

    if not cp_row or str(cp_row.verification_status.value if hasattr(cp_row.verification_status, "value") else cp_row.verification_status) != "approved":
        raise APIException(
            "Only approved caretakers can submit feedback",
            status_code=403,
            errors={"caretaker": ["Caretaker profile must be approved"]},
        )

    raw_rating = data.get("rating")
    feedback = _strip_tags(data.get("feedback"))
    suggestion = _strip_tags(data.get("suggestion"))
    is_anonymous_raw = data.get("is_anonymous", False)
    is_anonymous = _parse_bool(is_anonymous_raw)

    errors: Dict[str, List[str]] = {}

    rating_int: Optional[int] = None
    if raw_rating is None:
        errors["rating"] = ["Rating must be an integer between 1 and 5"]
    else:
        try:
            rating_int = int(raw_rating)
            if rating_int < 1 or rating_int > 5:
                errors["rating"] = ["Rating must be an integer between 1 and 5"]
        except (ValueError, TypeError):
            errors["rating"] = ["Rating must be an integer between 1 and 5"]

    if feedback == "" and suggestion == "":
        errors["feedback"] = ["Feedback or suggestion is required"]

    if len(feedback) > 2000:
        errors["feedback"] = ["Feedback must not exceed 2000 characters"]

    if len(suggestion) > 2000:
        errors["suggestion"] = ["Suggestion must not exceed 2000 characters"]

    if is_anonymous is None:
        errors["is_anonymous"] = ["is_anonymous must be a boolean"]

    if errors:
        raise APIException("Validation failed", status_code=400, errors=errors)

    try:
        db.execute(
            text(
                "INSERT INTO caretaker_feedback "
                "    (caretaker_user_id, rating, feedback, suggestion, is_anonymous) "
                "VALUES (:uid, :rating, :fb, :sug, :anon)"
            ),
            {
                "uid": user_id,
                "rating": rating_int,
                "fb": feedback if feedback != "" else None,
                "sug": suggestion if suggestion != "" else None,
                "anon": 1 if is_anonymous else 0,
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException("Failed to submit feedback", status_code=500)


# ── Admin Feedback Moderation Endpoints ──────────────────────────────────────

def get_admin_caretaker_feedback_list(
    db: Session,
    admin_user: Any,
    filters: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/caretaker_feedback
    Admin endpoint to view and filter caretaker feedback with statistics.
    """
    page = max(1, int(filters.get("page", 1)))
    limit_raw = filters.get("per_page") or filters.get("limit") or 50
    limit = min(100, max(1, int(limit_raw)))
    offset = (page - 1) * limit

    rating_str = str(filters.get("rating", "")).strip() if filters.get("rating") is not None else ""
    status_str = str(filters.get("status", "")).strip() if filters.get("status") is not None else ""
    anonymous_str = str(filters.get("is_anonymous", "")).strip() if filters.get("is_anonymous") is not None else ""
    date_from = str(filters.get("date_from", "")).strip() if filters.get("date_from") is not None else ""
    date_to = str(filters.get("date_to", "")).strip() if filters.get("date_to") is not None else ""
    sort_by = str(filters.get("sort_by", "created_at")).strip()
    sort_order = str(filters.get("sort_order", "desc")).strip().lower()

    where: List[str] = []
    params: Dict[str, Any] = {}
    errors: Dict[str, List[str]] = {}

    if rating_str != "":
        try:
            rating_int = int(rating_str)
            if rating_int < 1 or rating_int > 5:
                errors["rating"] = ["Rating must be between 1 and 5"]
            else:
                where.append("cf.rating = :rating_filter")
                params["rating_filter"] = rating_int
        except (ValueError, TypeError):
            errors["rating"] = ["Rating must be between 1 and 5"]

    if status_str != "":
        if status_str not in ("pending", "reviewed", "archived"):
            errors["status"] = ["Invalid feedback status"]
        else:
            where.append("cf.status = :status_filter")
            params["status_filter"] = status_str

    if anonymous_str != "":
        anon_norm = anonymous_str.lower()
        if anon_norm not in ("1", "0", "true", "false"):
            errors["is_anonymous"] = ["is_anonymous must be true or false"]
        else:
            where.append("cf.is_anonymous = :anon_filter")
            params["anon_filter"] = 1 if anon_norm in ("1", "true") else 0

    if date_from != "":
        try:
            datetime.strptime(date_from, "%Y-%m-%d")
            where.append("cf.created_at >= :date_from_filter")
            params["date_from_filter"] = f"{date_from} 00:00:00"
        except ValueError:
            errors["date_from"] = ["date_from must be YYYY-MM-DD"]

    if date_to != "":
        try:
            datetime.strptime(date_to, "%Y-%m-%d")
            where.append("cf.created_at <= :date_to_filter")
            params["date_to_filter"] = f"{date_to} 23:59:59"
        except ValueError:
            errors["date_to"] = ["date_to must be YYYY-MM-DD"]

    sort_map = {
        "created_at": "cf.created_at",
        "rating": "cf.rating",
        "status": "cf.status",
    }
    if sort_by not in sort_map:
        errors["sort_by"] = ["sort_by must be one of created_at, rating, status"]

    if sort_order not in ("asc", "desc"):
        errors["sort_order"] = ["sort_order must be asc or desc"]

    if errors:
        raise APIException("Validation failed", status_code=400, errors=errors)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = f"{sort_map[sort_by]} {sort_order.upper()}, cf.id DESC"

    count_query = f"SELECT COUNT(*) AS total FROM caretaker_feedback cf {where_sql}"
    count_row = db.execute(text(count_query), params).fetchone()
    total = int(count_row.total) if count_row else 0

    stats_query = f"""
        SELECT
            COUNT(*) AS total_feedback,
            COALESCE(ROUND(AVG(rating), 2), 0) AS average_rating,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN status = 'reviewed' THEN 1 ELSE 0 END) AS reviewed_count,
            SUM(CASE WHEN status = 'archived' THEN 1 ELSE 0 END) AS archived_count,
            SUM(CASE WHEN is_anonymous = 1 THEN 1 ELSE 0 END) AS anonymous_count
        FROM caretaker_feedback cf
        {where_sql}
    """
    stats_row = db.execute(text(stats_query), params).fetchone()

    rating_stats_query = f"""
        SELECT rating, COUNT(*) AS count
        FROM caretaker_feedback cf
        {where_sql}
        GROUP BY rating
        ORDER BY rating ASC
    """
    rating_rows = db.execute(text(rating_stats_query), params).fetchall()
    rating_counts: Dict[str, int] = {}
    for r in rating_rows:
        rating_counts[str(r.rating)] = int(r.count)

    items_params = dict(params)
    items_params["limit"] = limit
    items_params["offset"] = offset

    items_query = f"""
        SELECT cf.id, cf.caretaker_user_id, cf.rating, cf.feedback, cf.suggestion,
               cf.is_anonymous, cf.status, cf.admin_note, cf.created_at, cf.updated_at,
               cf.reviewed_at, u.username, u.email, u.phone_number, u.profile_picture,
               cp.full_name, cp.city
        FROM caretaker_feedback cf
        INNER JOIN users u ON u.id = cf.caretaker_user_id
        LEFT JOIN caretaker_profiles cp ON cp.user_id = cf.caretaker_user_id
        {where_sql}
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(items_query), items_params).fetchall()

    items = []
    for row in rows:
        is_anon = bool(int(row.is_anonymous) == 1)
        item: Dict[str, Any] = {
            "id": int(row.id),
            "rating": int(row.rating),
            "feedback": row.feedback or "",
            "suggestion": row.suggestion or "",
            "is_anonymous": is_anon,
            "status": str(row.status.value if hasattr(row.status, "value") else row.status),
            "admin_note": row.admin_note,
            "created_at": _admin_feedback_iso(row.created_at),
            "updated_at": _admin_feedback_iso(row.updated_at),
            "reviewed_at": _admin_feedback_iso(row.reviewed_at),
        }

        if not is_anon:
            item["caretaker"] = {
                "id": int(row.caretaker_user_id),
                "full_name": row.full_name,
                "username": row.username,
                "email": row.email,
                "phone_number": row.phone_number,
                "profile_picture": row.profile_picture,
                "city": row.city,
            }

        items.append(item)

    total_pages = math.ceil(total / limit) if limit > 0 else 1

    return {
        "items": items,
        "pagination": {
            "page": page,
            "per_page": limit,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
        },
        "statistics": {
            "total_feedback": int(stats_row.total_feedback or 0) if stats_row else 0,
            "average_rating": float(stats_row.average_rating or 0) if stats_row else 0.0,
            "pending_count": int(stats_row.pending_count or 0) if stats_row else 0,
            "reviewed_count": int(stats_row.reviewed_count or 0) if stats_row else 0,
            "archived_count": int(stats_row.archived_count or 0) if stats_row else 0,
            "anonymous_count": int(stats_row.anonymous_count or 0) if stats_row else 0,
            "rating_counts": rating_counts,
        },
    }


def update_feedback_status(
    db: Session,
    admin_user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/update_feedback_status
    Admin updates feedback status, sets admin note and reviewed_at, and logs audit trail.
    """
    admin_id = _get_user_id(admin_user)

    feedback_id_raw = data.get("feedback_id")
    status_str = str(data.get("status", "")).strip()
    admin_note = _strip_tags(data.get("admin_note"))

    errors: Dict[str, List[str]] = {}

    feedback_id_int: Optional[int] = None
    if feedback_id_raw is None:
        errors["feedback_id"] = ["Feedback id must be a valid integer"]
    else:
        try:
            feedback_id_int = int(feedback_id_raw)
            if feedback_id_int < 1:
                errors["feedback_id"] = ["Feedback id must be a valid integer"]
        except (ValueError, TypeError):
            errors["feedback_id"] = ["Feedback id must be a valid integer"]

    if status_str not in ("pending", "reviewed", "archived"):
        errors["status"] = ["Status must be pending, reviewed, or archived"]

    if len(admin_note) > 2000:
        errors["admin_note"] = ["Admin note must not exceed 2000 characters"]

    if errors:
        raise APIException("Validation failed", status_code=400, errors=errors)

    row = db.execute(
        text("SELECT id, caretaker_user_id, status, admin_note, reviewed_at FROM caretaker_feedback WHERE id = :fid"),
        {"fid": feedback_id_int},
    ).fetchone()

    if not row:
        raise APIException("Feedback not found", status_code=404)

    old_status = str(row.status.value if hasattr(row.status, "value") else row.status)
    old_note = row.admin_note

    # Update row
    note_to_save = admin_note if admin_note != "" else None
    db.execute(
        text(
            "UPDATE caretaker_feedback "
            "SET status = :status, "
            "    admin_note = :admin_note, "
            "    reviewed_at = CASE WHEN :status = 'reviewed' THEN COALESCE(reviewed_at, NOW()) ELSE reviewed_at END, "
            "    updated_at = NOW() "
            "WHERE id = :fid"
        ),
        {
            "status": status_str,
            "admin_note": note_to_save,
            "fid": feedback_id_int,
        },
    )

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_caretaker_feedback_status",
        entity_type="caretaker_feedback",
        entity_id=feedback_id_int,
        old_values={"status": old_status, "admin_note": old_note},
        new_values={"status": status_str, "admin_note": note_to_save},
    )

    db.commit()

    return {
        "feedback_id": feedback_id_int,
        "status": status_str,
        "admin_note": note_to_save,
    }

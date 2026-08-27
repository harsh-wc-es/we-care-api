"""
WeCare — Admin Caretaker Mapping & Inspection Service

Mirrors helpers/admin_caretaker.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.caretaker_document_service import (
    build_caretaker_document_slots,
    caretaker_document_rows_for_user,
)
from app.services.url_service import public_file_url


def admin_caretaker_bool(val: Any) -> bool:
    """Route: admin_caretaker_bool() — helpers/admin_caretaker L246-249"""
    if isinstance(val, bool):
        return val
    if val is None or val == "":
        return False
    if str(val).lower() in ["true", "1", "yes"]:
        return True
    if str(val).lower() in ["false", "0", "no"]:
        return False
    try:
        return int(val) == 1
    except (ValueError, TypeError):
        return False


def admin_caretaker_number(val: Any) -> Optional[float]:
    """Route: admin_caretaker_number() — helpers/admin_caretaker L251-254"""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def admin_caretaker_text(val: Any) -> Optional[str]:
    """Route: admin_caretaker_text() — helpers/admin_caretaker L256-264"""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def admin_caretaker_label(val: str) -> str:
    """Route: admin_caretaker_label() — helpers/admin_caretaker L266-269"""
    return str(val).replace("-", " ").replace("_", " ").title()


def build_admin_caretaker_response(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route: build_admin_caretaker_response() — helpers/admin_caretaker L11-142
    """
    r = dict(row)
    user_id = int(r.get("user_id") or r.get("id") or 0)
    profile_id = (
        int(r["caretaker_profile_id"])
        if r.get("caretaker_profile_id") is not None
        else (int(r["profile_id"]) if r.get("profile_id") is not None else None)
    )

    has_active_visit = admin_caretaker_bool(
        r.get("caretaker_has_active_visit") if r.get("caretaker_has_active_visit") is not None else r.get("has_active_visit")
    )
    is_available = admin_caretaker_bool(
        r.get("is_available") if r.get("is_available") is not None else r.get("caretaker_is_available")
    )
    manual_availability = admin_caretaker_bool(
        r.get("manual_availability_enabled") if r.get("manual_availability_enabled") is not None else r.get("caretaker_manual_preference")
    )
    admin_locked = admin_caretaker_bool(
        r.get("availability_locked_by_admin") if r.get("availability_locked_by_admin") is not None else r.get("caretaker_admin_locked")
    )
    availability_reason = r.get("availability_reason") or r.get("caretaker_availability_reason")
    availability_changed_by = r.get("availability_changed_by") or r.get("caretaker_availability_changed_by")

    availability_source = "caretaker_manual"
    if has_active_visit or availability_reason == "on_visit":
        availability_source = "system_active_visit"
    elif (
        admin_locked
        or availability_changed_by == "admin"
        or availability_reason in ["admin_forced_on", "admin_forced_off"]
    ):
        availability_source = "admin_override"
        admin_locked = True

    availability_status = "busy" if has_active_visit else ("available" if is_available else "unavailable")
    is_active_val = r.get("is_active") if r.get("is_active") is not None else r.get("user_is_active")
    if not has_active_visit and not is_available and is_active_val is not None and int(is_active_val) != 1:
        availability_status = "offline"

    review_count = int(r.get("review_rating_count") or 0)
    average_rating = None
    if review_count > 0 and r.get("review_average_rating") is not None:
        average_rating = round(float(r["review_average_rating"]), 2)
    elif int(r.get("total_reviews") or 0) > 0:
        review_count = int(r["total_reviews"])
        average_rating = round(float(r.get("rating") or 0), 2)

    tier_slug = admin_caretaker_text(r.get("pricing_tier_slug") or r.get("pricing_tier"))
    tier_label = admin_caretaker_text(r.get("pricing_tier_name"))
    if tier_label is None and tier_slug is not None:
        tier_label = admin_caretaker_label(tier_slug)
    if tier_label is None:
        tier_label = "Unassigned"

    experience_years = int(r["experience_years"]) if r.get("experience_years") is not None else None
    experience = (
        f"{experience_years} {'yr' if experience_years == 1 else 'yrs'}"
        if experience_years and experience_years > 0
        else None
    )

    r["id"] = user_id
    r["user_id"] = user_id
    r["profile_id"] = profile_id
    r["caretaker_profile_id"] = profile_id
    r["caretaker_id"] = f"CT-{str(user_id).zfill(4)}" if user_id > 0 else None
    r["full_name"] = admin_caretaker_text(r.get("full_name") or r.get("username"))
    r["phone"] = admin_caretaker_text(r.get("phone") or r.get("phone_number"))
    r["city"] = admin_caretaker_text(r.get("city"))
    r["gender"] = admin_caretaker_text(r.get("gender"))
    r["dob"] = r.get("dob") or r.get("date_of_birth")
    r["experience"] = experience
    r["specialization"] = admin_caretaker_text(r.get("specialization") or r.get("qualification"))
    r["skills"] = r.get("skills")
    r["languages"] = r.get("languages")
    r["verification_status"] = r.get("verification_status") or r.get("caretaker_verification_status")
    r["pricing_tier_id"] = int(r["pricing_tier_id"]) if r.get("pricing_tier_id") is not None else None
    r["pricing_tier"] = tier_slug
    r["pricing_tier_label"] = tier_label

    customer_rate = admin_caretaker_number(r.get("customer_hourly_rate"))
    caretaker_rate = admin_caretaker_number(r.get("caretaker_hourly_rate"))
    commission_percent = admin_caretaker_number(r.get("commission_percentage"))

    if (customer_rate is None or customer_rate <= 0) and r.get("tier_customer_hourly_rate") is not None:
        customer_rate = admin_caretaker_number(r["tier_customer_hourly_rate"])
    if (caretaker_rate is None or caretaker_rate < 0) and r.get("tier_caretaker_hourly_rate") is not None:
        caretaker_rate = admin_caretaker_number(r["tier_caretaker_hourly_rate"])
    if (commission_percent is None or commission_percent < 0) and r.get("tier_commission_percentage") is not None:
        commission_percent = admin_caretaker_number(r["tier_commission_percentage"])
    if (commission_percent is None or commission_percent <= 0) and customer_rate and customer_rate > 0 and caretaker_rate is not None:
        commission_percent = round(((customer_rate - caretaker_rate) / customer_rate) * 100, 2)

    earning_split_label = None
    if commission_percent is not None:
        earning_split_label = f"{round(100 - commission_percent, 2)}% caregiver / {round(commission_percent, 2)}% platform"

    r["customer_hourly_rate"] = customer_rate
    r["caretaker_hourly_rate"] = caretaker_rate
    r["commission_percentage"] = commission_percent
    r["platform_commission_percentage"] = commission_percent
    r["tier_id"] = r["pricing_tier_id"]
    r["tier_name"] = tier_label
    r["tier_code"] = tier_slug
    r["customer_rate_per_hour"] = customer_rate
    r["caregiver_rate_per_hour"] = caretaker_rate
    r["commission_percent"] = commission_percent
    r["earning_split_label"] = earning_split_label or "Not set"
    r["average_rating"] = average_rating
    r["rating_count"] = review_count
    r["availability_status"] = availability_status
    r["availability_source"] = availability_source
    r["admin_locked"] = 1 if admin_locked else 0
    r["manual_preference"] = "on" if manual_availability else "off"
    r["active_visit"] = 1 if has_active_visit else 0
    r["is_available"] = 1 if is_available else 0
    r["profile_photo"] = r.get("profile_photo") or r.get("profile_picture")
    r["profile_picture_url"] = public_file_url(r.get("profile_picture"))
    r["profile_photo_url"] = public_file_url(r.get("profile_photo"))

    # Legacy aliases
    r["tier"] = r.get("tier") or tier_label
    r["rating"] = r.get("rating") if r.get("rating") is not None else average_rating
    r["caretaker_is_available"] = is_available
    r["caretaker_admin_locked"] = admin_locked
    r["caretaker_manual_preference"] = manual_availability
    r["caretaker_has_active_visit"] = has_active_visit

    return r


def build_admin_caretaker_documents(db: Session, caretaker_user_id: int) -> Dict[str, Any]:
    """
    Route: build_admin_caretaker_documents() — helpers/admin_caretaker L144-151
    """
    items = caretaker_document_rows_for_user(db, caretaker_user_id)
    return {
        "items": items,
        "map": build_caretaker_document_slots(items),
    }


def build_admin_caretaker_reviews(db: Session, caretaker_user_id: int) -> Dict[str, Any]:
    """
    Route: build_admin_caretaker_reviews() — helpers/admin_caretaker L153-244
    """
    rows = db.execute(
        text(
            "SELECT r.id, "
            "       r.booking_id, "
            "       CONCAT('#', r.booking_id) AS booking_reference, "
            "       r.family_user_id, "
            "       fu.username AS family_name, "
            "       fu.email AS family_email, "
            "       fu.phone_number AS family_phone, "
            "       b.patient_id, "
            "       pd.patient_name, "
            "       r.caretaker_user_id, "
            "       r.rating, "
            "       r.comment, "
            "       r.comment AS review, "
            "       r.comment AS feedback, "
            "       r.created_at, "
            "       r.created_at AS submitted_at, "
            "       r.created_at AS reviewed_at "
            "FROM reviews r "
            "LEFT JOIN users fu ON fu.id = r.family_user_id "
            "LEFT JOIN bookings b ON b.id = r.booking_id "
            "LEFT JOIN patient_details pd ON pd.id = b.patient_id "
            "WHERE r.caretaker_user_id = :cid "
            "ORDER BY r.created_at DESC, r.id DESC"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchall()

    reviews: List[Dict[str, Any]] = []
    stats = {
        "average_rating": 0,
        "avg_rating": 0,
        "total_reviews": 0,
        "review_count": 0,
        "reviews_count": 0,
        "rating_count": 0,
        "five_star": 0,
        "four_star": 0,
        "three_star": 0,
        "two_star": 0,
        "one_star": 0,
    }

    rating_total = 0
    for row in rows:
        m = row._mapping
        rating = int(m.get("rating") or 0)
        cr_at = m.get("created_at")
        cr_str = cr_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(cr_at, "strftime") else (str(cr_at) if cr_at else None)

        rev = {
            "id": int(m["id"]),
            "booking_id": int(m.get("booking_id") or 0),
            "booking_reference": m.get("booking_reference"),
            "family_user_id": int(m.get("family_user_id") or 0),
            "family_name": admin_caretaker_text(m.get("family_name")),
            "family_email": admin_caretaker_text(m.get("family_email")),
            "family_phone": admin_caretaker_text(m.get("family_phone")),
            "patient_name": admin_caretaker_text(m.get("patient_name")),
            "caretaker_user_id": int(m.get("caretaker_user_id") or 0),
            "rating": rating,
            "comment": admin_caretaker_text(m.get("comment")),
            "review": admin_caretaker_text(m.get("comment")),
            "feedback": admin_caretaker_text(m.get("comment")),
            "created_at": cr_str,
            "submitted_at": cr_str,
            "reviewed_at": cr_str,
        }
        reviews.append(rev)

        if 1 <= rating <= 5:
            rating_total += rating
            if rating == 5:
                stats["five_star"] += 1
            elif rating == 4:
                stats["four_star"] += 1
            elif rating == 3:
                stats["three_star"] += 1
            elif rating == 2:
                stats["two_star"] += 1
            elif rating == 1:
                stats["one_star"] += 1

    total = len(reviews)
    average = round(rating_total / total, 2) if total > 0 else 0
    stats["average_rating"] = average
    stats["avg_rating"] = average
    stats["total_reviews"] = total
    stats["review_count"] = total
    stats["reviews_count"] = total
    stats["rating_count"] = total

    return {
        "items": reviews,
        "reviews": reviews,
        "stats": stats,
    }

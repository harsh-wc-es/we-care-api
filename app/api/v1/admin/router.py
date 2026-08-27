"""
WeCare — Admin Routes

Complete implementation of all 23 admin endpoints mirroring api/v1/admin/.
"""

import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.schemas.admin import (
    AdminProfileUpdateRequest,
    ApproveCaretakerRequest,
    ApproveDocumentRequest,
    BanCaretakerRequest,
    RejectCaretakerRequest,
    RejectSelectedDocumentsRequest,
    SetAvailabilityOverrideRequest,
    SingleRejectDocumentRequest,
    UpdateUserStatusRequest,
)
from app.schemas.pricing import (
    CreatePricingTierRequest,
    DeletePricingTierRequest,
    UpdateCaregiverTierPricingRequest,
    UpdateCaretakerPricingRequest,
    UpdatePricingTierRequest,
)
from app.services.admin_caretaker_service import (
    admin_caretaker_text,
    build_admin_caretaker_documents,
    build_admin_caretaker_response,
    build_admin_caretaker_reviews,
)
from app.services.audit_service import audit_log
from app.services.availability_service import (
    admin_set_caretaker_availability,
    caretaker_availability_payload,
    caretaker_has_active_visit,
)
from app.services.caretaker_document_service import (
    build_caretaker_document_summary,
    caretaker_document_status_for_storage,
    caretaker_is_banned_payload,
    caretaker_profile_status_for_storage,
    normalize_caretaker_document_type,
    update_caretaker_verification_status_from_documents,
)
from app.services.notification_service import (
    notify_caretaker_approved,
    notify_caretaker_rejected,
)
from app.services.patient_service import patient_to_dict
from app.services.pricing_tier_service import (
    apply_pricing_tier_to_caretaker,
    calculate_commission,
    get_pricing_tier,
    pricing_tier_slug,
    validate_pricing_rates,
)
from app.services.sos_service import get_admin_sos_detail


router = APIRouter()


# ── 1. Admin Profile ───────────────────────────────────────────────────

@router.get("/me")
def get_admin_me_route(
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/me"""
    created_at = current_admin.get("created_at")
    updated_at = current_admin.get("updated_at")
    return success_response(
        data={
            "id": int(current_admin["id"]),
            "name": current_admin.get("username"),
            "username": current_admin.get("username"),
            "email": current_admin.get("email"),
            "phone_number": current_admin.get("phone_number"),
            "role": str(current_admin.get("role") or "admin"),
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else (str(created_at) if created_at else None),
            "updated_at": updated_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(updated_at, "strftime") else (str(updated_at) if updated_at else None),
        },
        message="Admin profile fetched successfully",
    )


@router.post("/update_profile")
def update_admin_profile_route(
    body: AdminProfileUpdateRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/update_profile (422 status on validation error)"""
    admin_id = int(current_admin["id"])
    name = (body.name or body.username or "").strip()
    email = (body.email or "").strip()
    phone_number = (body.phone_number or body.phone or "").strip()

    errors: Dict[str, List[str]] = {}
    if not name:
        errors["name"] = ["Name is required"]
    elif len(name) < 2 or len(name) > 100:
        errors["name"] = ["Name must be between 2 and 100 characters"]

    if not email:
        errors["email"] = ["Email is required"]
    elif not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        errors["email"] = ["Email must be a valid email address"]

    if phone_number and not re.match(r"^\d{7,15}$", phone_number):
        errors["phone_number"] = ["Phone number must be 7 to 15 digits"]

    if errors:
        raise APIException(message="Validation failed", status_code=422, errors=errors)

    # Check email in use
    existing_e = db.execute(
        text("SELECT id FROM users WHERE email = :e AND id <> :id LIMIT 1"),
        {"e": email, "id": admin_id},
    ).fetchone()
    if existing_e:
        raise APIException(message="Email is already in use", status_code=422, errors={"email": ["Email is already in use"]})

    if phone_number:
        existing_p = db.execute(
            text("SELECT id FROM users WHERE phone_number = :p AND id <> :id LIMIT 1"),
            {"p": phone_number, "id": admin_id},
        ).fetchone()
        if existing_p:
            raise APIException(message="Phone number is already in use", status_code=422, errors={"phone_number": ["Phone number is already in use"]})

    db.execute(
        text("UPDATE users SET username = :name, email = :email, phone_number = :phone, updated_at = NOW() WHERE id = :id"),
        {"name": name, "email": email, "phone": phone_number or None, "id": admin_id},
    )
    db.commit()

    updated_row = db.execute(
        text("SELECT id, email, username, phone_number, role, created_at, updated_at FROM users WHERE id = :id"),
        {"id": admin_id},
    ).mappings().first()

    u = dict(updated_row)
    cr_at = u.get("created_at")
    up_at = u.get("updated_at")

    return success_response(
        data={
            "id": admin_id,
            "name": u.get("username"),
            "username": u.get("username"),
            "email": u.get("email"),
            "phone_number": u.get("phone_number"),
            "role": str(u.get("role") or "admin"),
            "created_at": cr_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(cr_at, "strftime") else (str(cr_at) if cr_at else None),
            "updated_at": up_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(up_at, "strftime") else (str(up_at) if up_at else None),
        },
        message="Admin profile updated successfully",
    )


# ── 2. Users Management ────────────────────────────────────────────────

@router.get("/users")
def list_users_route(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[str] = Query(""),
    status: Optional[str] = Query(""),
    availability: Optional[str] = Query(""),
    available: Optional[str] = Query(""),
    verification_status: Optional[str] = Query(""),
    search: Optional[str] = Query(""),
    online_only: Optional[str] = Query(""),
    active_visit: Optional[str] = Query(""),
    admin_locked: Optional[str] = Query(""),
    availability_reason: Optional[str] = Query(""),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/users"""
    where: List[str] = []
    params: Dict[str, Any] = {}

    if role:
        if role not in ["family", "caretaker", "admin"]:
            raise APIException(message="Invalid role", status_code=400)
        where.append("u.role = :role")
        params["role"] = role

    avail_val = availability or available or ""
    verif_val = verification_status or ""

    if status:
        if status in ["available", "unavailable"]:
            avail_val = status
        elif status in ["approved", "pending", "rejected"]:
            verif_val = status
        elif status not in ["active", "inactive"]:
            raise APIException(message="Invalid status", status_code=400)
        else:
            where.append("u.is_active = :status_val")
            params["status_val"] = 1 if status == "active" else 0

    if avail_val:
        if str(avail_val).lower() in ["1", "true"]:
            avail_val = "available"
        if str(avail_val).lower() in ["0", "false"]:
            avail_val = "unavailable"
        if avail_val not in ["available", "unavailable"]:
            raise APIException(message="Invalid availability filter", status_code=400)
        where.append("cp.is_available = :avail_filter")
        where.append("u.role = 'caretaker'")
        params["avail_filter"] = 1 if avail_val == "available" else 0

    if verif_val:
        if verif_val not in ["approved", "pending", "rejected"]:
            raise APIException(message="Invalid verification status", status_code=400)
        where.append("cp.verification_status = :verif_filter")
        where.append("u.role = 'caretaker'")
        params["verif_filter"] = verif_val

    search_term = str(search or "").strip()
    if search_term:
        where.append("(u.email LIKE :search OR u.username LIKE :search OR u.phone_number LIKE :search)")
        params["search"] = f"%{search_term}%"

    if str(online_only).lower() == "true":
        where.append("cp.last_active_at >= DATE_SUB(NOW(), INTERVAL 15 MINUTE)")
        where.append("u.role = 'caretaker'")

    if str(active_visit).lower() == "true":
        where.append(
            "EXISTS (SELECT 1 FROM visit_tracking vt INNER JOIN bookings b ON b.id = vt.booking_id "
            "WHERE vt.caretaker_user_id = u.id AND vt.check_out_time IS NULL AND b.status = 'in_progress')"
        )
        where.append("u.role = 'caretaker'")

    if str(admin_locked).lower() == "true":
        where.append("cp.availability_locked_by_admin = 1")
        where.append("u.role = 'caretaker'")

    valid_reasons = ['manual_off', 'manual_on', 'on_visit', 'inactive', 'pending_review', 'rejected', 'admin_forced_off', 'admin_forced_on']
    if availability_reason and availability_reason in valid_reasons:
        where.append("cp.availability_reason = :avail_reason")
        where.append("u.role = 'caretaker'")
        params["avail_reason"] = availability_reason

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    offset = (page - 1) * limit

    count_res = db.execute(
        text(
            f"SELECT COUNT(*) FROM users u "
            f"LEFT JOIN caretaker_profiles cp ON cp.user_id = u.id "
            f"{where_sql}"
        ),
        params,
    ).scalar()
    total = int(count_res or 0)

    rows = db.execute(
        text(
            f"SELECT u.id, u.id AS user_id, u.email, u.username, u.phone_number, u.role, u.is_verified, u.is_active, u.profile_picture, u.created_at, u.updated_at, "
            f"       cp.id AS caretaker_profile_id, cp.full_name, cp.gender, cp.date_of_birth, cp.experience_years, "
            f"       cp.qualification, cp.city, cp.state, cp.pincode, "
            f"       cp.pricing_tier_id, cp.pricing_tier, cp.customer_hourly_rate, "
            f"       cp.caretaker_hourly_rate, cp.commission_percentage, "
            f"       cp.rating, cp.total_reviews, "
            f"       pt.name AS pricing_tier_name, pt.slug AS pricing_tier_slug, "
            f"       pt.customer_hourly_rate AS tier_customer_hourly_rate, "
            f"       pt.caretaker_hourly_rate AS tier_caretaker_hourly_rate, "
            f"       pt.commission_percentage AS tier_commission_percentage, "
            f"       review_stats.average_rating AS review_average_rating, "
            f"       review_stats.rating_count AS review_rating_count, "
            f"       cp.verification_status AS caretaker_verification_status, "
            f"       cp.is_available AS caretaker_is_available, "
            f"       cp.availability_updated_at AS caretaker_availability_updated_at, "
            f"       cp.last_active_at AS caretaker_last_active_at, "
            f"       cp.availability_reason AS caretaker_availability_reason, "
            f"       cp.availability_locked_by_admin AS caretaker_admin_locked, "
            f"       cp.manual_availability_enabled AS caretaker_manual_preference, "
            f"       cp.availability_changed_by AS caretaker_availability_changed_by, "
            f"       EXISTS ( "
            f"           SELECT 1 FROM visit_tracking vt INNER JOIN bookings b ON b.id = vt.booking_id "
            f"           WHERE vt.caretaker_user_id = u.id AND vt.check_in_time IS NOT NULL AND vt.check_out_time IS NULL AND b.status = 'in_progress' "
            f"       ) AS caretaker_has_active_visit "
            f"FROM users u "
            f"LEFT JOIN caretaker_profiles cp ON cp.user_id = u.id "
            f"LEFT JOIN pricing_tiers pt ON pt.id = cp.pricing_tier_id "
            f"LEFT JOIN ( "
            f"    SELECT caretaker_user_id, ROUND(AVG(rating), 2) AS average_rating, COUNT(*) AS rating_count "
            f"    FROM reviews GROUP BY caretaker_user_id "
            f") review_stats ON review_stats.caretaker_user_id = u.id "
            f"{where_sql} "
            f"ORDER BY u.id DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r._mapping)
        if item["role"] == "caretaker":
            item = build_admin_caretaker_response(item)
        else:
            item["caretaker_is_available"] = None
            item["caretaker_availability_reason"] = None
            item["caretaker_admin_locked"] = None
            item["caretaker_manual_preference"] = None
            item["caretaker_has_active_visit"] = None

        cr_at = item.get("created_at")
        up_at = item.get("updated_at")
        if cr_at and hasattr(cr_at, "strftime"):
            item["created_at"] = cr_at.strftime("%Y-%m-%d %H:%M:%S")
        if up_at and hasattr(up_at, "strftime"):
            item["updated_at"] = up_at.strftime("%Y-%m-%d %H:%M:%S")

        items.append(item)

    return success_response(
        data={
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0,
            "items": items,
        },
        message="Users retrieved",
    )


@router.post("/update_user_status")
def update_user_status_route(
    body: UpdateUserStatusRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/update_user_status"""
    admin_id = int(current_admin["id"])
    if body.is_active not in [0, 1]:
        raise APIException(message="User id and valid is_active are required", status_code=400)

    if body.user_id == admin_id and body.is_active == 0:
        raise APIException(message="Admin cannot deactivate own account", status_code=400)

    row = db.execute(
        text("SELECT id, email, username, role, is_active FROM users WHERE id = :uid"),
        {"uid": body.user_id},
    ).fetchone()

    if not row:
        raise APIException(message="User not found", status_code=404)

    old = dict(row._mapping)

    try:
        db.execute(
            text("UPDATE users SET is_active = :is_active, updated_at = NOW() WHERE id = :uid"),
            {"is_active": body.is_active, "uid": body.user_id},
        )
        if body.is_active == 0:
            db.execute(
                text("UPDATE tokens SET is_blacklisted = 1 WHERE user_id = :uid"),
                {"uid": body.user_id},
            )
            if old.get("role") == "caretaker":
                db.execute(
                    text("UPDATE caretaker_profiles SET is_available = 0, availability_updated_at = NOW() WHERE user_id = :uid"),
                    {"uid": body.user_id},
                )
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException(message="User status update failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_user_status",
        entity_type="user",
        entity_id=body.user_id,
        old_values=old,
        new_values={
            "is_active": body.is_active,
            "forced_is_available": False if (old.get("role") == "caretaker" and body.is_active == 0) else None,
        },
    )

    return success_response(
        data={
            "user_id": body.user_id,
            "is_active": body.is_active == 1,
        },
        message="User status updated",
    )


# ── 3. Patient Details ─────────────────────────────────────────────────

@router.get("/patient_profile")
def get_admin_patient_profile_route(
    family_user_id: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/patient_profile"""
    if not family_user_id or not str(family_user_id).isdigit() or int(family_user_id) <= 0:
        raise APIException(
            message="Invalid family_user_id",
            status_code=400,
            errors={"family_user_id": ["family_user_id must be a positive integer"]},
        )

    f_uid = int(family_user_id)
    user_row = db.execute(
        text("SELECT id FROM users WHERE id = :uid AND role = 'family' LIMIT 1"),
        {"uid": f_uid},
    ).fetchone()

    if not user_row:
        raise APIException(message="Family user not found", status_code=404)

    patient_row = db.execute(
        text("SELECT * FROM patient_details WHERE family_user_id = :uid LIMIT 1"),
        {"uid": f_uid},
    ).fetchone()

    if not patient_row:
        return success_response(data=None, message="No patient profile found")

    return success_response(data=patient_to_dict(patient_row), message="Patient profile retrieved")


# ── 4. Caretaker Inspection & Verification ─────────────────────────────

@router.get("/view_caretaker")
def view_caretaker_route(
    user_id: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/view_caretaker"""
    if not user_id or not str(user_id).isdigit() or int(user_id) <= 0:
        raise APIException(message="Caretaker user_id is required", status_code=400)

    cid = int(user_id)
    row = db.execute(
        text(
            "SELECT cp.*, cp.id AS caretaker_profile_id, "
            "       u.id AS user_id, u.email, u.username, u.phone_number, u.is_verified, u.is_active, u.profile_picture, "
            "       pt.name AS pricing_tier_name, pt.slug AS pricing_tier_slug, "
            "       pt.customer_hourly_rate AS tier_customer_hourly_rate, "
            "       pt.caretaker_hourly_rate AS tier_caretaker_hourly_rate, "
            "       pt.commission_percentage AS tier_commission_percentage, "
            "       review_stats.average_rating AS review_average_rating, "
            "       review_stats.rating_count AS review_rating_count "
            "FROM users u "
            "INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "LEFT JOIN pricing_tiers pt ON pt.id = cp.pricing_tier_id "
            "LEFT JOIN ( "
            "    SELECT caretaker_user_id, ROUND(AVG(rating), 2) AS average_rating, COUNT(*) AS rating_count "
            "    FROM reviews GROUP BY caretaker_user_id "
            ") review_stats ON review_stats.caretaker_user_id = u.id "
            "WHERE u.id = :cid AND u.role = 'caretaker'"
        ),
        {"cid": cid},
    ).fetchone()

    if not row:
        raise APIException(message="Caretaker not found", status_code=404)

    caretaker = dict(row._mapping)

    if caretaker.get("pricing_tier_id"):
        t_row = db.execute(
            text("SELECT id, name, slug FROM pricing_tiers WHERE id = :tid"),
            {"tid": caretaker["pricing_tier_id"]},
        ).fetchone()
        caretaker["pricing_tier_detail"] = dict(t_row._mapping) if t_row else None
    else:
        caretaker["pricing_tier_detail"] = None

    docs = build_admin_caretaker_documents(db, cid)
    caretaker["documents"] = docs["items"]
    caretaker["document_map"] = docs["map"]
    caretaker["documents_by_type"] = docs["map"]

    doc_status = build_caretaker_document_summary(db, cid, {**caretaker, "user_is_active": caretaker.get("is_active", 1)})
    summary = doc_status["summary"]

    caretaker["document_summary"] = summary
    caretaker["verification_status"] = summary["effective_verification_status"]
    caretaker["caretaker_verification_status"] = caretaker["verification_status"]
    caretaker["otp_verified"] = int(caretaker.get("is_verified") or 0) == 1
    caretaker["account_status"] = "banned" if caretaker["verification_status"] == "banned" else ("active" if int(caretaker.get("is_active") or 1) == 1 else "suspended")
    caretaker["total_required_documents"] = summary["total_required_documents"]
    caretaker["uploaded_documents_count"] = summary["uploaded_documents_count"]
    caretaker["pending_documents_count"] = summary["pending_documents_count"]
    caretaker["approved_documents_count"] = summary["approved_documents_count"]
    caretaker["rejected_documents_count"] = summary["rejected_documents_count"]
    caretaker["can_approve"] = summary["can_approve"]
    caretaker["can_reject"] = summary["can_reject"]
    caretaker["can_ban"] = summary["can_ban"]
    caretaker["can_unban"] = summary["can_unban"]
    caretaker["is_banned"] = summary["effective_verification_status"] == "banned"
    caretaker["latest_reupload_at"] = summary["latest_reupload_at"]

    rev_payload = build_admin_caretaker_reviews(db, cid)
    caretaker["reviews"] = rev_payload["reviews"]
    caretaker["review_items"] = rev_payload["items"]
    caretaker["review_stats"] = rev_payload["stats"]
    caretaker["total_reviews"] = rev_payload["stats"]["total_reviews"]
    caretaker["review_count"] = rev_payload["stats"]["review_count"]
    caretaker["reviews_count"] = rev_payload["stats"]["reviews_count"]
    caretaker["rating_count"] = rev_payload["stats"]["rating_count"]
    caretaker["average_rating"] = rev_payload["stats"]["average_rating"]
    caretaker["avg_rating"] = rev_payload["stats"]["avg_rating"]
    caretaker["caretaker_rating"] = rev_payload["stats"]["average_rating"]

    caretaker["has_active_visit"] = caretaker_has_active_visit(db, cid)
    caretaker["availability_detail"] = caretaker_availability_payload(db, cid)
    caretaker = build_admin_caretaker_response(caretaker)

    return success_response(data=caretaker, message="Caretaker details retrieved")


@router.get("/pending_caretakers")
def list_pending_caretakers_route(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(""),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/pending_caretakers"""
    search_term = str(search or "").strip()
    where_sql = "WHERE u.role = 'caretaker' AND cp.verification_status = 'pending'"
    params: Dict[str, Any] = {}

    if search_term:
        where_sql += " AND (u.username LIKE :search OR u.email LIKE :search OR cp.full_name LIKE :search)"
        params["search"] = f"%{search_term}%"

    offset = (page - 1) * limit
    count_res = db.execute(
        text(f"SELECT COUNT(*) FROM users u INNER JOIN caretaker_profiles cp ON cp.user_id = u.id {where_sql}"),
        params,
    ).scalar()
    total = int(count_res or 0)

    rows = db.execute(
        text(
            f"SELECT u.id AS user_id, u.email, u.username, u.phone_number, "
            f"       cp.full_name, cp.experience_years, cp.qualification, cp.city, cp.verification_status "
            f"FROM users u "
            f"INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            f"{where_sql} "
            f"ORDER BY cp.id DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    items = [dict(r._mapping) for r in rows]

    return success_response(
        data={
            "items": items,
            "caretakers": items,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": math.ceil(total / limit) if limit > 0 else 0,
            },
        },
        message="Pending caretakers retrieved",
    )


@router.get("/caretaker_verification")
def list_caretaker_verification_route(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query("pending_review"),
    search: Optional[str] = Query(""),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/caretaker_verification"""
    status_filter = str(status or "pending_review").lower().strip()
    allowed = ["all", "pending_review", "pending", "approved", "rejected", "needs_resubmission", "banned"]
    if status_filter not in allowed:
        raise APIException(
            message="Invalid verification status filter",
            status_code=400,
            errors={"status": ["Use pending_review, approved, rejected, needs_resubmission, banned, or all"]},
        )

    where = ["u.role = 'caretaker'"]
    params: Dict[str, Any] = {}
    search_term = str(search or "").strip()
    if search_term:
        where.append("(u.username LIKE :search OR u.email LIKE :search OR u.phone_number LIKE :search OR cp.full_name LIKE :search)")
        params["search"] = f"%{search_term}%"

    where_sql = f"WHERE {' AND '.join(where)}"
    count_res = db.execute(
        text(f"SELECT COUNT(*) FROM users u INNER JOIN caretaker_profiles cp ON cp.user_id = u.id {where_sql}"),
        params,
    ).scalar()
    raw_total = int(count_res or 0)

    rows = db.execute(
        text(
            f"SELECT u.id AS user_id, u.email, u.username, u.phone_number, u.is_verified, "
            f"       u.is_active AS user_is_active, u.profile_picture, "
            f"       cp.id AS caretaker_profile_id, cp.full_name, cp.experience_years, "
            f"       cp.qualification, cp.city, cp.verification_status, cp.is_available, "
            f"       cp.rejection_reason, cp.created_at, cp.updated_at "
            f"FROM users u "
            f"INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            f"{where_sql} "
            f"ORDER BY cp.updated_at DESC, cp.id DESC"
        ),
        params,
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for r in rows:
        row_dict = dict(r._mapping)
        doc_payload = build_caretaker_document_summary(db, int(row_dict["user_id"]), row_dict)
        summary = doc_payload["summary"]
        eff_status = summary["effective_verification_status"]

        matches = (
            status_filter == "all"
            or (status_filter == "pending" and eff_status == "pending_review")
            or (status_filter == "rejected" and eff_status == "needs_resubmission")
            or (status_filter == eff_status)
        )

        if not matches:
            continue

        row_dict["verification_status"] = eff_status
        row_dict["caretaker_verification_status"] = eff_status
        row_dict["otp_verified"] = int(row_dict.get("is_verified") or 0) == 1
        row_dict["account_status"] = "banned" if eff_status == "banned" else ("active" if int(row_dict.get("user_is_active") or 1) == 1 else "suspended")
        row_dict["document_summary"] = summary
        row_dict["total_required_documents"] = summary["total_required_documents"]
        row_dict["uploaded_documents_count"] = summary["uploaded_documents_count"]
        row_dict["pending_documents_count"] = summary["pending_documents_count"]
        row_dict["approved_documents_count"] = summary["approved_documents_count"]
        row_dict["rejected_documents_count"] = summary["rejected_documents_count"]
        row_dict["can_approve"] = summary["can_approve"]
        row_dict["can_reject"] = summary["can_reject"]
        row_dict["can_ban"] = summary["can_ban"]
        row_dict["can_unban"] = summary["can_unban"]
        row_dict["is_banned"] = eff_status == "banned"
        row_dict["latest_reupload_at"] = summary["latest_reupload_at"]
        row_dict["caretaker_user_id"] = int(row_dict["user_id"])
        row_dict["caretaker_name"] = row_dict.get("full_name") or (row_dict.get("username") or row_dict.get("email"))
        row_dict["phone"] = row_dict.get("phone_number")
        items.append(build_admin_caretaker_response(row_dict))

    total = len(items)
    offset = (page - 1) * limit
    page_items = items[offset : offset + limit]

    return success_response(
        data={
            "items": page_items,
            "caretakers": page_items,
            "page": page,
            "limit": limit,
            "total": total,
            "raw_total": raw_total,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0,
            "status": status_filter,
        },
        message="Caretaker verification list retrieved",
    )


# ── 5. Caretaker Approval, Rejection & Ban ─────────────────────────────

@router.post("/approve_caretaker")
def approve_caretaker_legacy_route(
    body: ApproveCaretakerRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/approve_caretaker"""
    admin_id = int(current_admin["id"])
    uid = body.user_id or body.caretaker_user_id
    if not uid:
        raise APIException(message="Caretaker user_id is required", status_code=400, errors={"user_id": ["Caretaker user_id is required"]})

    tier_id = body.pricing_tier_id or body.tier_id
    if not tier_id:
        raise APIException(message="Required fields missing", status_code=400, errors={"pricing_tier_id": ["Pricing tier id is required"]})

    row = db.execute(
        text("SELECT cp.*, u.role, u.is_active FROM caretaker_profiles cp INNER JOIN users u ON u.id = cp.user_id WHERE cp.user_id = :uid AND u.role = 'caretaker'"),
        {"uid": uid},
    ).fetchone()

    if not row:
        raise APIException(message="Caretaker not found", status_code=404)

    caretaker = dict(row._mapping)
    if caretaker_is_banned_payload(caretaker):
        raise APIException(message="Banned caretakers cannot be approved.", status_code=400, errors={"caretaker_user_id": ["Unban this caretaker before approval."]})

    doc_summary = build_caretaker_document_summary(db, uid, caretaker)["summary"]
    if not doc_summary["all_required_approved"]:
        raise APIException(
            message="Cannot approve caretaker until all required documents are approved.",
            status_code=400,
            errors={
                "documents": ["All required documents must be uploaded and approved before caretaker approval."],
                "document_summary": doc_summary,
            },
        )

    try:
        pricing_res = apply_pricing_tier_to_caretaker(
            db=db,
            caretaker_user_id=uid,
            tier_id=tier_id,
            overrides={
                "pricing_override_enabled": body.pricing_override_enabled,
                "customer_hourly_rate": body.customer_hourly_rate,
                "caretaker_hourly_rate": body.caretaker_hourly_rate,
            },
        )
        if not pricing_res["success"]:
            raise APIException(message=pricing_res["message"], status_code=400, errors=pricing_res.get("errors"))

        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET verification_status = 'approved', rejection_reason = NULL, is_available = 0, "
                "    availability_updated_at = NOW(), payout_priority = :payout, updated_at = NOW() "
                "WHERE user_id = :uid"
            ),
            {"payout": body.payout_priority or 0, "uid": uid},
        )
        db.commit()
    except APIException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise APIException(message="Caretaker approval failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="approve_caretaker_with_tier",
        entity_type="caretaker_profile",
        entity_id=uid,
        old_values=caretaker,
        new_values={
            "status": "approved",
            "is_available": False,
            "pricing": pricing_res.get("pricing"),
            "payout_priority": body.payout_priority or 0,
        },
    )
    notify_caretaker_approved(db, uid)

    return success_response(
        data={
            "user_id": uid,
            "status": "approved",
            "is_available": False,
            "pricing": pricing_res.get("pricing"),
        },
        message="Caretaker approved successfully",
    )


@router.post("/caretakers/approve")
def approve_caretaker_queue_route(
    body: ApproveCaretakerRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/caretakers/approve"""
    admin_id = int(current_admin["id"])
    uid = body.caretaker_user_id or body.user_id
    if not uid:
        raise APIException(message="Caretaker user id is required", status_code=400, errors={"caretaker_user_id": ["Caretaker user id is required"]})

    row = db.execute(
        text("SELECT cp.*, u.role, u.is_active FROM caretaker_profiles cp INNER JOIN users u ON u.id = cp.user_id WHERE cp.user_id = :uid AND u.role = 'caretaker'"),
        {"uid": uid},
    ).fetchone()

    if not row:
        raise APIException(message="Caretaker not found", status_code=404)

    caretaker = dict(row._mapping)
    if caretaker_is_banned_payload(caretaker):
        raise APIException(message="Banned caretakers cannot be approved.", status_code=400, errors={"caretaker_user_id": ["Unban this caretaker before approval."]})

    doc_summary = build_caretaker_document_summary(db, uid, caretaker)["summary"]
    if not doc_summary["all_required_approved"]:
        raise APIException(
            message="Cannot approve caretaker until all required documents are approved.",
            status_code=400,
            errors={
                "documents": ["All required documents must be approved first."],
                "document_summary": doc_summary,
            },
        )

    tier_id = body.pricing_tier_id or body.tier_id or (int(caretaker["pricing_tier_id"]) if caretaker.get("pricing_tier_id") else 0)
    if not tier_id:
        raise APIException(message="Pricing tier id is required", status_code=400, errors={"pricing_tier_id": ["Select a pricing tier before approval."]})

    try:
        pricing_res = apply_pricing_tier_to_caretaker(
            db=db,
            caretaker_user_id=uid,
            tier_id=tier_id,
            overrides={
                "pricing_override_enabled": body.pricing_override_enabled,
                "customer_hourly_rate": body.customer_hourly_rate,
                "caretaker_hourly_rate": body.caretaker_hourly_rate,
            },
        )
        if not pricing_res["success"]:
            raise APIException(message=pricing_res["message"], status_code=400, errors=pricing_res.get("errors"))

        storage_status = caretaker_profile_status_for_storage("approved")
        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET verification_status = :status, rejection_reason = NULL, is_available = 0, "
                "    availability_updated_at = NOW(), updated_at = NOW() "
                "WHERE user_id = :uid"
            ),
            {"status": storage_status, "uid": uid},
        )
        db.commit()
    except APIException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise APIException(message="Caretaker approval failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="approve_caretaker_after_document_verification",
        entity_type="caretaker_profile",
        entity_id=uid,
        old_values=caretaker,
        new_values={"verification_status": "approved", "pricing_tier_id": tier_id},
    )
    notify_caretaker_approved(db, uid)

    return success_response(
        data={
            "caretaker_user_id": uid,
            "user_id": uid,
            "verification_status": "approved",
            "status": "approved",
            "pricing": pricing_res.get("pricing"),
        },
        message="Caretaker approved successfully",
    )


@router.post("/reject_caretaker")
def reject_caretaker_route(
    body: RejectCaretakerRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/reject_caretaker"""
    admin_id = int(current_admin["id"])
    uid = body.user_id
    if not uid:
        raise APIException(message="Caretaker user_id is required", status_code=400, errors={"user_id": ["Caretaker user_id is required"]})

    row = db.execute(
        text("SELECT cp.id, cp.user_id, cp.verification_status, cp.is_available, cp.rejection_reason FROM caretaker_profiles cp INNER JOIN users u ON u.id = cp.user_id WHERE cp.user_id = :uid AND u.role = 'caretaker'"),
        {"uid": uid},
    ).fetchone()

    if not row:
        raise APIException(message="Caretaker not found", status_code=404)

    caretaker = dict(row._mapping)
    rejection_reason = body.rejection_reason or ""

    try:
        storage_status = caretaker_profile_status_for_storage("needs_resubmission")
        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET verification_status = :st, rejection_reason = :rr, is_available = 0, "
                "    availability_updated_at = NOW(), updated_at = NOW() "
                "WHERE user_id = :uid"
            ),
            {"st": storage_status, "rr": rejection_reason, "uid": uid},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException(message="Caretaker rejection failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="reject_caretaker_force_unavailable",
        entity_type="caretaker_profile",
        entity_id=uid,
        old_values={
            "verification_status": caretaker.get("verification_status"),
            "is_available": int(caretaker.get("is_available") or 0) == 1,
        },
        new_values={
            "verification_status": "needs_resubmission",
            "is_available": False,
            "reason": rejection_reason,
        },
    )
    notify_caretaker_rejected(db, uid, rejection_reason)

    return success_response(
        data={
            "user_id": uid,
            "status": "needs_resubmission",
            "is_available": False,
            "reason": rejection_reason,
        },
        message="Caretaker rejected successfully",
    )


@router.post("/caretakers/ban")
def ban_caretaker_route(
    body: BanCaretakerRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/caretakers/ban"""
    admin_id = int(current_admin["id"])
    uid = body.caretaker_user_id or body.user_id
    reason = (body.reason or body.ban_reason or body.admin_note or "").strip()

    if not uid:
        raise APIException(message="Caretaker user id is required", status_code=400, errors={"caretaker_user_id": ["Caretaker user id is required"]})
    if not reason:
        raise APIException(message="Ban reason is required", status_code=400, errors={"reason": ["Ban reason is required"]})

    row = db.execute(
        text("SELECT cp.*, u.role, u.is_active FROM caretaker_profiles cp INNER JOIN users u ON u.id = cp.user_id WHERE cp.user_id = :uid AND u.role = 'caretaker'"),
        {"uid": uid},
    ).fetchone()

    if not row:
        raise APIException(message="Caretaker not found", status_code=404)

    caretaker = dict(row._mapping)

    try:
        storage_status = caretaker_profile_status_for_storage("banned")
        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET verification_status = :st, rejection_reason = :rr, is_available = 0, "
                "    manual_availability_enabled = 0, availability_reason = 'inactive', "
                "    availability_locked_by_admin = 1, availability_locked_note = :note, "
                "    availability_locked_at = NOW(), availability_locked_by_user_id = :admin_id, "
                "    availability_updated_at = NOW(), updated_at = NOW() "
                "WHERE user_id = :uid"
            ),
            {"st": storage_status, "rr": reason, "note": reason, "admin_id": admin_id, "uid": uid},
        )
        db.execute(
            text("UPDATE users SET is_active = 0, updated_at = NOW() WHERE id = :uid"),
            {"uid": uid},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException(message="Caretaker ban failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="ban_caretaker",
        entity_type="caretaker_profile",
        entity_id=uid,
        old_values=caretaker,
        new_values={"verification_status": "banned", "is_available": False, "reason": reason},
    )

    return success_response(
        data={
            "caretaker_user_id": uid,
            "user_id": uid,
            "verification_status": "banned",
            "status": "banned",
            "is_banned": True,
            "reason": reason,
        },
        message="Caretaker banned successfully",
    )


# ── 6. Document Moderation ─────────────────────────────────────────────

@router.post("/caretaker_documents/approve")
def approve_document_route(
    body: ApproveDocumentRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/caretaker_documents/approve"""
    admin_id = int(current_admin["id"])
    uid = body.caretaker_user_id or body.user_id
    doc_id = body.document_id or body.id

    errors: Dict[str, List[str]] = {}
    if not uid:
        errors["caretaker_user_id"] = ["Caretaker user id is required"]
    if not doc_id:
        errors["document_id"] = ["Document id is required"]
    if errors:
        raise APIException(message="Validation failed", status_code=400, errors=errors)

    row = db.execute(
        text("SELECT d.*, u.role FROM documents d INNER JOIN users u ON u.id = d.user_id WHERE d.id = :id AND d.user_id = :uid"),
        {"id": doc_id, "uid": uid},
    ).fetchone()

    if not row or row._mapping.get("role") != "caretaker" or normalize_caretaker_document_type(row._mapping.get("document_type")) is None:
        raise APIException(message="Caretaker document not found", status_code=404)

    doc = dict(row._mapping)
    canonical = normalize_caretaker_document_type(doc.get("document_type"))

    try:
        db.execute(
            text(
                "UPDATE documents "
                "SET document_type = :dt, status = 'approved', admin_note = NULL, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"dt": canonical, "id": doc_id},
        )
        status_payload = update_caretaker_verification_status_from_documents(db, uid)
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException(message="Document approval failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="approve_caretaker_document",
        entity_type="document",
        entity_id=doc_id,
        old_values=doc,
        new_values={"status": "approved", "caretaker_user_id": uid},
    )

    doc_summary = build_caretaker_document_summary(db, uid)
    return success_response(
        data={
            "caretaker_user_id": uid,
            "document_id": doc_id,
            "verification_status": status_payload.get("status") or doc_summary["summary"]["effective_verification_status"],
            "document_summary": doc_summary["summary"],
            "documents": list(doc_summary["slots"].values()),
        },
        message="Document approved successfully.",
    )


@router.post("/caretaker_documents/reject_selected")
def reject_selected_documents_route(
    body: RejectSelectedDocumentsRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/caretaker_documents/reject_selected
    Uses SELECT ... FOR UPDATE row locks.
    """
    admin_id = int(current_admin["id"])
    uid = body.caretaker_user_id or body.user_id
    docs = body.documents or []

    errors: Dict[str, List[str]] = {}
    if not uid:
        errors["caretaker_user_id"] = ["Caretaker user id is required"]
    if not docs:
        errors["documents"] = ["At least one document rejection is required"]

    normalized: List[Dict[str, Any]] = []
    for i, item in enumerate(docs):
        d_id = item.document_id or item.id
        reason = (item.reason or item.admin_note or item.rejection_reason or "").strip()
        if not d_id:
            errors[f"documents.{i}.document_id"] = ["Document id is required"]
        if not reason:
            errors[f"documents.{i}.reason"] = ["Rejection reason is required"]
        elif len(reason) > 500:
            errors[f"documents.{i}.reason"] = ["Rejection reason must not exceed 500 characters"]
        normalized.append({"document_id": d_id, "reason": reason})

    if errors:
        raise APIException(message="Validation failed", status_code=400, errors=errors)

    rejected_results = []
    try:
        for item in normalized:
            row = db.execute(
                text("SELECT d.*, u.role FROM documents d INNER JOIN users u ON u.id = d.user_id WHERE d.id = :id AND d.user_id = :uid LIMIT 1 FOR UPDATE"),
                {"id": item["document_id"], "uid": uid},
            ).fetchone()

            if not row or row._mapping.get("role") != "caretaker":
                raise APIException(message="Selected document rejection failed", status_code=404, errors={"documents": [f"Document not found: {item['document_id']}"]})

            canonical = normalize_caretaker_document_type(row._mapping.get("document_type"))
            if canonical is None:
                raise APIException(message="Selected document rejection failed", status_code=404, errors={"documents": [f"Document not found: {item['document_id']}"]})

            db.execute(
                text(
                    "UPDATE documents "
                    "SET document_type = :dt, status = 'rejected', admin_note = :reason, updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {"dt": canonical, "reason": item["reason"], "id": item["document_id"]},
            )
            rejected_results.append({
                "document_id": item["document_id"],
                "document_type": canonical,
                "reason": item["reason"],
            })

        status_payload = update_caretaker_verification_status_from_documents(db, uid, "needs_resubmission")
        db.commit()
    except APIException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise APIException(message="Selected document rejection failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="reject_selected_caretaker_documents",
        entity_type="caretaker_profile",
        entity_id=uid,
        new_values={"caretaker_user_id": uid, "documents": rejected_results},
    )

    doc_summary = build_caretaker_document_summary(db, uid)
    return success_response(
        data={
            "caretaker_user_id": uid,
            "verification_status": status_payload.get("status") or "needs_resubmission",
            "rejected_documents_count": doc_summary["summary"]["rejected_documents_count"],
            "document_summary": doc_summary["summary"],
            "documents": list(doc_summary["slots"].values()),
        },
        message="Selected documents rejected successfully.",
    )


@router.post("/reject_document")
def reject_single_document_route(
    body: SingleRejectDocumentRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/reject_document"""
    admin_id = int(current_admin["id"])
    doc_id = body.document_id or body.id
    reason = (body.reason or body.admin_note or body.rejection_reason or "").strip()

    errors: Dict[str, List[str]] = {}
    if not doc_id or int(doc_id) <= 0:
        errors["document_id"] = ["Document ID must be a positive integer"]
    if not reason:
        errors["reason"] = ["Rejection reason is required"]
    elif len(reason) > 500:
        errors["reason"] = ["Rejection reason must not exceed 500 characters"]

    if errors:
        raise APIException(message="Validation failed", status_code=400, errors=errors)

    row = db.execute(
        text("SELECT d.*, u.role FROM documents d INNER JOIN users u ON u.id = d.user_id WHERE d.id = :id"),
        {"id": doc_id},
    ).fetchone()

    if not row:
        raise APIException(message="Document not found", status_code=404)

    doc = dict(row._mapping)
    canonical = normalize_caretaker_document_type(doc.get("document_type"))
    if doc.get("role") != "caretaker" or canonical is None:
        raise APIException(
            message="Document is not a caretaker verification document",
            status_code=400,
            errors={"document_id": ["Only caretaker verification documents can be rejected"]},
        )

    try:
        db.execute(
            text(
                "UPDATE documents "
                "SET document_type = :dt, status = 'rejected', admin_note = :reason, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"dt": canonical, "reason": reason, "id": doc_id},
        )
        update_caretaker_verification_status_from_documents(db, int(doc["user_id"]), "needs_resubmission")
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException(message="Document rejection failed", status_code=500)

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="reject_caretaker_document",
        entity_type="document",
        entity_id=doc_id,
        old_values=doc,
        new_values={"document_type": canonical, "status": "rejected", "admin_note": reason},
    )

    return success_response(
        data={
            "document": {
                "id": doc_id,
                "document_type": canonical,
                "status": "rejected",
                "admin_note": reason,
            }
        },
        message="Document rejected successfully",
    )


# ── 7. Caretaker Availability Override ─────────────────────────────────

@router.post("/set_caretaker_availability")
def set_caretaker_availability_route(
    body: SetAvailabilityOverrideRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/set_caretaker_availability"""
    admin_id = int(current_admin["id"])
    if not body.caretaker_user_id:
        raise APIException(
            message="caretaker_user_id is required",
            status_code=400,
            errors={"caretaker_user_id": ["Caretaker user ID is required"]},
        )

    reason = (body.reason or ("admin_enabled" if body.is_available else "admin_disabled")).strip()
    note = (body.note or "").strip() or None

    result = admin_set_caretaker_availability(
        db=db,
        caretaker_user_id=body.caretaker_user_id,
        available=body.is_available,
        lock_availability=bool(body.lock_availability),
        note=note,
        reason=reason,
        admin_user_id=admin_id,
    )

    if not result["success"]:
        raise APIException(message=result["message"], status_code=400, errors=result.get("errors"))

    return success_response(data=result.get("data"), message=result["message"])


# ── 8. Caretaker Pricing Overrides ─────────────────────────────────────

@router.post("/update_caretaker_pricing")
def update_caretaker_pricing_route(
    body: UpdateCaretakerPricingRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/update_caretaker_pricing"""
    admin_id = int(current_admin["id"])
    errors: Dict[str, List[str]] = {}
    if not body.caretaker_user_id:
        errors["caretaker_user_id"] = ["Caretaker user id is required"]
    if not body.pricing_tier_id:
        errors["pricing_tier_id"] = ["Pricing tier id is required"]

    if body.pricing_override_enabled:
        if body.customer_hourly_rate is None:
            errors["customer_hourly_rate"] = ["Customer hourly rate is required when override is enabled"]
        if body.caretaker_hourly_rate is None:
            errors["caretaker_hourly_rate"] = ["Caretaker hourly rate is required when override is enabled"]

    if errors:
        raise APIException(message="Required fields missing", status_code=400, errors=errors)

    row = db.execute(
        text("SELECT * FROM caretaker_profiles WHERE user_id = :uid"),
        {"uid": body.caretaker_user_id},
    ).fetchone()

    if not row:
        raise APIException(message="Caretaker not found", status_code=404)

    old = dict(row._mapping)
    result = apply_pricing_tier_to_caretaker(
        db=db,
        caretaker_user_id=body.caretaker_user_id,
        tier_id=body.pricing_tier_id,
        overrides={
            "pricing_override_enabled": body.pricing_override_enabled,
            "customer_hourly_rate": body.customer_hourly_rate,
            "caretaker_hourly_rate": body.caretaker_hourly_rate,
        },
    )

    if not result["success"]:
        raise APIException(message=result["message"], status_code=400, errors=result.get("errors"))

    db.commit()
    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_caretaker_pricing",
        entity_type="caretaker_profile",
        entity_id=body.caretaker_user_id,
        old_values=old,
        new_values=result.get("pricing"),
    )

    return success_response(
        data={"caretaker_user_id": body.caretaker_user_id, "pricing": result["pricing"]},
        message="Caretaker pricing updated. Existing bookings are unchanged.",
    )


@router.post("/update_caregiver_tier_pricing")
def update_caregiver_tier_pricing_route(
    body: UpdateCaregiverTierPricingRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/update_caregiver_tier_pricing"""
    admin_id = int(current_admin["id"])
    cid = body.caretaker_user_id or body.caregiver_user_id or body.user_id
    if not cid:
        raise APIException(message="Caretaker user id is required", status_code=400, errors={"caretaker_user_id": ["Caretaker user id is required"]})

    row = db.execute(
        text("SELECT cp.*, u.id AS user_id, u.role FROM caretaker_profiles cp INNER JOIN users u ON u.id = cp.user_id WHERE cp.user_id = :uid"),
        {"uid": cid},
    ).fetchone()

    if not row or row._mapping.get("role") != "caretaker":
        raise APIException(message="Caretaker not found", status_code=404, errors={"caretaker_user_id": ["Caretaker not found"]})

    old = dict(row._mapping)
    tier_id = body.tier_id or body.pricing_tier_id
    tier_code = (body.tier or body.tier_code or "").strip()

    if not tier_id and tier_code:
        t_row = db.execute(
            text("SELECT id FROM pricing_tiers WHERE slug = :c OR name = :c LIMIT 1"),
            {"c": tier_code},
        ).fetchone()
        tier_id = int(t_row._mapping["id"]) if t_row else 0

    if not tier_id:
        raise APIException(message="Validation failed", status_code=400, errors={"tier_id": ["Pricing tier is required"]})

    tier = get_pricing_tier(db, tier_id)
    if not tier:
        raise APIException(message="Validation failed", status_code=400, errors={"tier_id": ["Pricing tier not found"]})
    if not tier["is_active"]:
        raise APIException(message="Validation failed", status_code=400, errors={"tier_id": ["Pricing tier must be active"]})

    cust_rate = body.customer_rate_per_hour if body.customer_rate_per_hour is not None else (body.customer_rate if body.customer_rate is not None else body.customer_hourly_rate)
    cg_rate = body.caregiver_rate_per_hour if body.caregiver_rate_per_hour is not None else (body.caregiver_rate if body.caregiver_rate is not None else body.caretaker_hourly_rate)
    comm_pct = body.commission_percent if body.commission_percent is not None else (body.commission if body.commission is not None else body.commission_percentage)

    if cust_rate is None:
        cust_rate = float(tier["customer_hourly_rate"])

    if cg_rate is None and comm_pct is not None and cust_rate is not None:
        cg_rate = round(cust_rate - ((cust_rate * comm_pct) / 100), 2)
    elif cg_rate is None:
        cg_rate = float(tier["caretaker_hourly_rate"])

    if comm_pct is None and cust_rate and cg_rate is not None and cust_rate > 0:
        comm_pct = round(((cust_rate - cg_rate) / cust_rate) * 100, 2)

    errors: Dict[str, List[str]] = {}
    if cust_rate is None or cust_rate <= 0:
        errors["customer_rate_per_hour"] = ["Customer rate per hour must be greater than 0"]
    if cg_rate is None or cg_rate < 0:
        errors["caregiver_rate_per_hour"] = ["Caregiver rate per hour must be greater than or equal to 0"]
    if cust_rate is not None and cg_rate is not None and cg_rate > cust_rate:
        errors["caregiver_rate_per_hour"] = ["Caregiver rate cannot exceed customer rate"]
    if comm_pct is None or comm_pct < 0 or comm_pct > 100:
        errors["commission_percent"] = ["Commission percent must be between 0 and 100"]

    if errors:
        raise APIException(message="Validation failed", status_code=400, errors=errors)

    commission = calculate_commission(cust_rate, cg_rate)
    pricing = {
        "pricing_tier_id": tier_id,
        "pricing_tier": tier["slug"],
        "pricing_tier_name": tier["name"],
        "skill_level": tier["skill_level"],
        "customer_hourly_rate": cust_rate,
        "caretaker_hourly_rate": cg_rate,
        "platform_commission_hourly": commission["platform_commission_hourly"],
        "commission_percentage": commission["commission_percentage"],
        "pricing_override_enabled": 1,
    }

    try:
        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET pricing_tier_id = :tid, pricing_tier = :slug, skill_level = :skill, "
                "    customer_hourly_rate = :cust, caretaker_hourly_rate = :cg, "
                "    platform_commission_hourly = :comm_h, commission_percentage = :comm_p, "
                "    pricing_override_enabled = 1, updated_at = NOW() "
                "WHERE user_id = :uid"
            ),
            {
                "tid": tier_id,
                "slug": tier["slug"],
                "skill": tier["skill_level"],
                "cust": cust_rate,
                "cg": cg_rate,
                "comm_h": commission["platform_commission_hourly"],
                "comm_p": commission["commission_percentage"],
                "uid": cid,
            },
        )
        audit_log(
            db=db,
            admin_user_id=admin_id,
            action="update_caregiver_tier_pricing",
            entity_type="caretaker_profile",
            entity_id=cid,
            old_values=old,
            new_values=pricing,
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise APIException(message="Failed to update caregiver tier/pricing", status_code=500)

    updated_row = db.execute(
        text(
            "SELECT cp.*, cp.id AS caretaker_profile_id, u.id AS user_id, u.email, u.username, u.phone_number, u.is_active, u.profile_picture, "
            "       pt.name AS pricing_tier_name, pt.slug AS pricing_tier_slug, "
            "       pt.customer_hourly_rate AS tier_customer_hourly_rate, "
            "       pt.caretaker_hourly_rate AS tier_caretaker_hourly_rate, "
            "       pt.commission_percentage AS tier_commission_percentage "
            "FROM users u INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "LEFT JOIN pricing_tiers pt ON pt.id = cp.pricing_tier_id "
            "WHERE u.id = :cid AND u.role = 'caretaker'"
        ),
        {"cid": cid},
    ).fetchone()

    updated = build_admin_caretaker_response(dict(updated_row._mapping) if updated_row else {})

    return success_response(
        data={
            "caretaker_user_id": cid,
            "name": updated.get("full_name"),
            "caregiver_id": updated.get("caretaker_id"),
            "tier_id": updated.get("tier_id"),
            "tier_name": updated.get("tier_name"),
            "tier_code": updated.get("tier_code"),
            "customer_rate_per_hour": updated.get("customer_rate_per_hour"),
            "caregiver_rate_per_hour": updated.get("caregiver_rate_per_hour"),
            "commission_percent": updated.get("commission_percent"),
            "earning_split_label": updated.get("earning_split_label"),
            "updated_at": updated.get("updated_at"),
            "caregiver": updated,
        },
        message="Caregiver tier/pricing updated successfully",
    )


# ── 9. Pricing Tiers Administration ────────────────────────────────────

@router.get("/pricing_tiers")
def admin_list_pricing_tiers_route(
    status: Optional[str] = Query("active"),
    search: Optional[str] = Query(""),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/pricing_tiers"""
    status_val = str(status or "active").lower().strip()
    if status_val not in ["active", "inactive", "all"]:
        raise APIException(
            message="Invalid status filter",
            status_code=400,
            errors={"status": ["Allowed values: active, inactive, all"]},
        )

    where = []
    params: Dict[str, Any] = {}
    if status_val == "active":
        where.append("pt.is_active = 1")
    elif status_val == "inactive":
        where.append("pt.is_active = 0")

    search_term = str(search or "").strip()
    if search_term:
        where.append("(pt.name LIKE :search OR pt.slug LIKE :search OR pt.skill_level LIKE :search)")
        params["search"] = f"%{search_term}%"

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(
        text(
            f"SELECT pt.*, COUNT(cp.user_id) AS caretaker_count "
            f"FROM pricing_tiers pt "
            f"LEFT JOIN caretaker_profiles cp ON cp.pricing_tier_id = pt.id "
            f"{where_sql} "
            f"GROUP BY pt.id "
            f"ORDER BY pt.is_active DESC, pt.customer_hourly_rate ASC, pt.id ASC"
        ),
        params,
    ).fetchall()

    tiers = []
    for r in rows:
        m = dict(r._mapping)
        m["is_active"] = int(m.get("is_active") or 0) == 1
        m["caretaker_count"] = int(m.get("caretaker_count") or 0)
        m["customer_hourly_rate"] = float(m["customer_hourly_rate"]) if m.get("customer_hourly_rate") is not None else 0.0
        m["caretaker_hourly_rate"] = float(m["caretaker_hourly_rate"]) if m.get("caretaker_hourly_rate") is not None else 0.0
        m["platform_commission_hourly"] = float(m.get("platform_commission_hourly") or 0.0)
        m["commission_percentage"] = float(m.get("commission_percentage") or 0.0)
        cr_at = m.get("created_at")
        up_at = m.get("updated_at")
        if cr_at and hasattr(cr_at, "strftime"):
            m["created_at"] = cr_at.strftime("%Y-%m-%d %H:%M:%S")
        if up_at and hasattr(up_at, "strftime"):
            m["updated_at"] = up_at.strftime("%Y-%m-%d %H:%M:%S")
        tiers.append(m)

    return success_response(data=tiers, message="Pricing tiers retrieved")


@router.post("/create_pricing_tier", status_code=201)
def create_pricing_tier_route(
    body: CreatePricingTierRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/create_pricing_tier"""
    admin_id = int(current_admin["id"])
    name = (body.name or "").strip()
    slug = pricing_tier_slug(name)

    errors: Dict[str, List[str]] = {}
    if not name:
        errors["name"] = ["Name is required"]

    errors.update(validate_pricing_rates(body.customer_hourly_rate, body.caretaker_hourly_rate))
    if errors:
        raise APIException(message="Invalid pricing tier", status_code=400, errors=errors)

    existing = db.execute(
        text("SELECT id FROM pricing_tiers WHERE slug = :s LIMIT 1"),
        {"s": slug},
    ).fetchone()
    if existing:
        raise APIException(
            message="Pricing tier already exists",
            status_code=409,
            errors={"name": ["A pricing tier with this name/slug already exists"]},
        )

    commission = calculate_commission(body.customer_hourly_rate, body.caretaker_hourly_rate)
    is_active_val = 1 if body.is_active is not False else 0

    res = db.execute(
        text(
            "INSERT INTO pricing_tiers "
            "(name, slug, description, skill_level, customer_hourly_rate, caretaker_hourly_rate, "
            " platform_commission_hourly, commission_percentage, is_active, created_at, updated_at) "
            "VALUES (:name, :slug, :desc, :skill, :cust, :cg, :comm_h, :comm_p, :active, NOW(), NOW())"
        ),
        {
            "name": name,
            "slug": slug,
            "desc": body.description or None,
            "skill": body.skill_level or None,
            "cust": body.customer_hourly_rate,
            "cg": body.caretaker_hourly_rate,
            "comm_h": commission["platform_commission_hourly"],
            "comm_p": commission["commission_percentage"],
            "active": is_active_val,
        },
    )
    tier_id = res.lastrowid
    db.commit()

    tier = get_pricing_tier(db, tier_id)
    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="create_pricing_tier",
        entity_type="pricing_tier",
        entity_id=tier_id,
        new_values=tier,
    )

    return success_response(data=tier, message="Pricing tier created", status_code=201)


@router.get("/pricing_tier_detail")
def pricing_tier_detail_route(
    id: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/pricing_tier_detail"""
    if not id or not str(id).isdigit() or int(id) <= 0:
        raise APIException(
            message="Pricing tier id is required",
            status_code=400,
            errors={"id": ["Pricing tier id is required"]},
        )

    tid = int(id)
    tier = get_pricing_tier(db, tid)
    if not tier:
        raise APIException(message="Pricing tier not found", status_code=404)

    count_res = db.execute(
        text("SELECT COUNT(*) FROM caretaker_profiles WHERE pricing_tier_id = :tid"),
        {"tid": tid},
    ).scalar()
    caretaker_count = int(count_res or 0)

    rows = db.execute(
        text(
            "SELECT u.id AS user_id, u.username, u.email, cp.full_name, cp.verification_status, "
            "       cp.customer_hourly_rate, cp.caretaker_hourly_rate, cp.pricing_override_enabled "
            "FROM caretaker_profiles cp "
            "INNER JOIN users u ON u.id = cp.user_id "
            "WHERE cp.pricing_tier_id = :tid "
            "ORDER BY cp.updated_at DESC, cp.id DESC "
            "LIMIT 10"
        ),
        {"tid": tid},
    ).fetchall()

    sample_caretakers = []
    for r in rows:
        m = dict(r._mapping)
        m["customer_hourly_rate"] = float(m["customer_hourly_rate"]) if m.get("customer_hourly_rate") is not None else None
        m["caretaker_hourly_rate"] = float(m["caretaker_hourly_rate"]) if m.get("caretaker_hourly_rate") is not None else None
        m["pricing_override_enabled"] = int(m.get("pricing_override_enabled") or 0) == 1
        sample_caretakers.append(m)

    tier["assigned_caretaker_count"] = caretaker_count
    tier["sample_assigned_caretakers"] = sample_caretakers

    return success_response(data=tier, message="Pricing tier detail retrieved")


@router.post("/update_pricing_tier")
def update_pricing_tier_route(
    body: UpdatePricingTierRequest,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/update_pricing_tier"""
    admin_id = int(current_admin["id"])
    tid = body.id
    if not tid or tid <= 0:
        raise APIException(message="Pricing tier id is required", status_code=400, errors={"id": ["Pricing tier id is required"]})

    old = get_pricing_tier(db, tid)
    if not old:
        raise APIException(message="Pricing tier not found", status_code=404)

    name = (body.name or old["name"]).strip()
    desc = body.description if body.description is not None else old["description"]
    skill = body.skill_level if body.skill_level is not None else old["skill_level"]
    cust_rate = body.customer_hourly_rate if body.customer_hourly_rate is not None else old["customer_hourly_rate"]
    cg_rate = body.caretaker_hourly_rate if body.caretaker_hourly_rate is not None else old["caretaker_hourly_rate"]
    active = int(body.is_active) if body.is_active is not None else (1 if old["is_active"] else 0)
    slug = pricing_tier_slug(name)

    errors: Dict[str, List[str]] = {}
    if not name:
        errors["name"] = ["Name is required"]
    errors.update(validate_pricing_rates(cust_rate, cg_rate))
    if errors:
        raise APIException(message="Invalid pricing tier", status_code=400, errors=errors)

    existing = db.execute(
        text("SELECT id FROM pricing_tiers WHERE slug = :s AND id <> :id LIMIT 1"),
        {"s": slug, "id": tid},
    ).fetchone()
    if existing:
        raise APIException(message="Pricing tier already exists", status_code=409, errors={"name": ["A pricing tier with this name/slug already exists"]})

    commission = calculate_commission(cust_rate, cg_rate)
    db.execute(
        text(
            "UPDATE pricing_tiers "
            "SET name = :name, slug = :slug, description = :desc, skill_level = :skill, "
            "    customer_hourly_rate = :cust, caretaker_hourly_rate = :cg, "
            "    platform_commission_hourly = :comm_h, commission_percentage = :comm_p, "
            "    is_active = :active, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {
            "name": name,
            "slug": slug,
            "desc": desc,
            "skill": skill,
            "cust": cust_rate,
            "cg": cg_rate,
            "comm_h": commission["platform_commission_hourly"],
            "comm_p": commission["commission_percentage"],
            "active": active,
            "id": tid,
        },
    )
    db.commit()

    tier = get_pricing_tier(db, tid)
    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_pricing_tier",
        entity_type="pricing_tier",
        entity_id=tid,
        old_values=old,
        new_values=tier,
    )

    return success_response(
        data=tier,
        message="Tier updated. Existing caretakers and bookings are unchanged unless reassigned manually.",
    )


@router.post("/delete_pricing_tier")
@router.delete("/delete_pricing_tier")
def delete_pricing_tier_route(
    request: Request,
    id: Optional[str] = Query(None),
    body: Optional[DeletePricingTierRequest] = None,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/delete_pricing_tier (POST and DELETE)"""
    admin_id = int(current_admin["id"])
    target_id = None
    if body and body.id:
        target_id = body.id
    elif id and str(id).isdigit():
        target_id = int(id)

    if not target_id:
        raise APIException(
            message="Pricing tier id is required",
            status_code=400,
            errors={"id": ["Pricing tier id is required"]},
        )

    old = get_pricing_tier(db, target_id)
    if not old:
        raise APIException(message="Pricing tier not found", status_code=404)

    db.execute(
        text("UPDATE pricing_tiers SET is_active = 0, updated_at = NOW() WHERE id = :id"),
        {"id": target_id},
    )
    db.commit()

    tier = get_pricing_tier(db, target_id)
    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="deactivate_pricing_tier",
        entity_type="pricing_tier",
        entity_id=target_id,
        old_values=old,
        new_values=tier,
    )

    return success_response(data=tier, message="Pricing tier deactivated")


# ── Booking Management (Admin) ─────────────────────────────────────────

@router.get("/bookings")
def get_admin_bookings_route(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/bookings"""
    from app.services.booking_service import get_admin_bookings

    result = get_admin_bookings(db, page=page, limit=limit, status=status)
    return success_response(data=result, message="Bookings fetched successfully")


@router.get("/booking_detail")
def get_admin_booking_detail_route(
    id: Optional[str] = Query(None),
    booking_id: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/booking_detail"""
    from app.services.booking_service import get_admin_booking_detail

    target_id_raw = booking_id or id
    if not target_id_raw:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id is required"]},
            status_code=400,
        )

    try:
        bid = int(target_id_raw)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    result = get_admin_booking_detail(db, booking_id=bid)
    return success_response(data=result, message="Booking details fetched successfully")


@router.post("/cancel_booking")
async def admin_cancel_booking_route(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Route: api/v1/admin/cancel_booking"""
    from app.services.booking_workflow_service import booking_workflow_transition
    from app.services.refund_service import (
        create_booking_refund_if_payable,
        refund_format_money,
        refund_policy_for_family_cancellation,
        successful_booking_payment_summary,
        sync_cancelled_booking_refund_snapshot,
    )

    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())

    booking_id_raw = data.get("booking_id")
    reason = str(data.get("reason") or data.get("cancel_reason") or data.get("cancel_reason_label") or "").strip()

    errors: Dict[str, List[str]] = {}
    if not booking_id_raw:
        errors["booking_id"] = ["Booking id must be a positive integer"]
    else:
        try:
            bid = int(booking_id_raw)
            if bid < 1:
                errors["booking_id"] = ["Booking id must be a positive integer"]
        except ValueError:
            errors["booking_id"] = ["Booking id must be a positive integer"]

    if not reason:
        errors["reason"] = ["Please provide a reason for cancellation"]

    if errors:
        raise APIException(
            message="Booking id is required" if "booking_id" in errors else "Cancellation reason is required",
            errors=errors,
            status_code=400,
        )

    bid = int(booking_id_raw)
    admin_id = int(current_admin["id"])

    # Lock row
    row = db.execute(
        text("SELECT id, family_user_id, caretaker_user_id, status, booking_date, start_time FROM bookings WHERE id = :bid FOR UPDATE"),
        {"bid": bid},
    ).fetchone()

    if not row:
        raise APIException(message="Booking not found", status_code=404)

    booking = dict(row._mapping)
    payment_summary = successful_booking_payment_summary(db, bid)
    paid_amount = payment_summary["paid_amount"]
    payment_id = payment_summary["payment_id"]

    b_date = str(booking["booking_date"])
    s_time = str(booking["start_time"])
    try:
        visit_start_dt = datetime.strptime(f"{b_date} {s_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            visit_start_dt = datetime.strptime(f"{b_date} {s_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            visit_start_dt = None

    hours_before = (visit_start_dt - datetime.now()).total_seconds() / 3600.0 if visit_start_dt else 0.0
    refund_percentage, policy_label = refund_policy_for_family_cancellation(hours_before)
    refund_amount = refund_format_money(paid_amount * (refund_percentage / 100))

    transition = booking_workflow_transition(
        db=db,
        booking_id=bid,
        actor_user_id=admin_id,
        actor_role="admin",
        to_status="cancelled",
        options={"cancellation_reason": reason},
    )

    if not transition["success"]:
        raise APIException(
            message=transition["message"],
            errors=transition.get("errors"),
            status_code=transition.get("status", 400),
        )

    db.execute(
        text(
            "UPDATE bookings "
            "SET cancelled_by = 'admin', "
            "    cancellation_reason = :reason, "
            "    cancelled_at = NOW(), "
            "    cancelled_by_user_id = :admin_id, "
            "    cancelled_by_role = 'admin', "
            "    cancel_reason_label = :reason, "
            "    payout_status = 'not_applicable', "
            "    updated_at = NOW() "
            "WHERE id = :bid AND status = 'cancelled'"
        ),
        {"reason": reason, "admin_id": admin_id, "bid": bid},
    )

    refund_snapshot = sync_cancelled_booking_refund_snapshot(
        db=db,
        booking_id=bid,
        paid_amount=paid_amount,
        refund_percentage=refund_percentage,
        refund_amount=refund_amount,
    )

    refund_id, refund_record_created = create_booking_refund_if_payable(
        db=db,
        booking=booking,
        paid_amount=refund_snapshot["paid_amount"],
        refund_percentage=refund_snapshot["refund_percentage"],
        refund_amount=refund_snapshot["refund_amount"],
        payment_id=payment_id,
        reason=reason if reason else "Booking cancelled refund",
    )

    db.commit()

    return success_response(
        data={
            "booking_id": bid,
            "old_status": transition["from_status"],
            "new_status": "cancelled",
            "reason": reason,
            "refund": {
                "paid_amount": float(refund_snapshot["paid_amount"]),
                "refund_eligible": refund_snapshot["refund_eligible"],
                "refund_percentage": float(refund_snapshot["refund_percentage"]),
                "refund_amount": float(refund_snapshot["refund_amount"]),
                "refund_status": refund_snapshot["refund_status"],
                "refund_id": refund_id,
                "refund_record_created": refund_record_created,
                "policy_label": policy_label,
            },
        },
        message="Booking cancelled successfully",
    )


# ─────────────────────────────────────────────────────────────
# 24. sos_detail
# ─────────────────────────────────────────────────────────────

@router.get("/sos_detail")
def admin_sos_detail_endpoint(
    id: Optional[Union[int, str]] = Query(None),
    sos_id: Optional[Union[int, str]] = Query(None),
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin detailed view of an SOS alert with joined booking context."""
    effective_id = id if id is not None else sos_id
    data = get_admin_sos_detail(
        db=db,
        admin_user=admin_user,
        sos_id=effective_id,
    )
    return success_response(
        message="SOS alert detail retrieved",
        data=data,
        status_code=200,
    )


# ─────────────────────────────────────────────────────────────
# 25. caretaker_feedback & update_feedback_status
# ─────────────────────────────────────────────────────────────

@router.get("/caretaker_feedback")
def admin_caretaker_feedback_endpoint(
    page: int = Query(1, ge=1),
    limit: Optional[int] = Query(None),
    per_page: Optional[int] = Query(None),
    rating: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_anonymous: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/caretaker_feedback
    Retrieves caretaker feedback list with filtering and statistics.
    """
    from app.services.review_service import get_admin_caretaker_feedback_list

    effective_limit = per_page if per_page is not None else (limit if limit is not None else 50)
    filters = {
        "page": page,
        "limit": effective_limit,
        "per_page": effective_limit,
        "rating": rating,
        "status": status,
        "is_anonymous": is_anonymous,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
    data = get_admin_caretaker_feedback_list(db=db, admin_user=admin_user, filters=filters)
    return success_response("Caretaker feedback retrieved", data)


@router.post("/update_feedback_status")
def admin_update_feedback_status_endpoint(
    req: Dict[str, Any],
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/update_feedback_status
    Updates caretaker feedback status and admin note with audit trail.
    """
    from app.services.review_service import update_feedback_status

    data = update_feedback_status(db=db, admin_user=admin_user, data=req)
    return success_response("Feedback status updated", data)


# ─────────────────────────────────────────────────────────────
# 26. Part 12B Admin Settlement, Payouts, Export & Reports
# ─────────────────────────────────────────────────────────────

@router.get("/earnings")
def admin_earnings_endpoint(
    page: Optional[str] = Query(None),
    limit: Optional[str] = Query(None),
    tab: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/earnings
    """
    from app.services.admin_payout_service import (
        get_admin_earnings_summary,
        get_admin_earnings_tab,
    )

    if tab is not None and str(tab).strip() != "":
        data = get_admin_earnings_tab(db=db, tab=str(tab).strip(), page=page or 1, limit=limit or 50)
        return success_response(message="Payout tab retrieved", data=data)

    data = get_admin_earnings_summary(db=db, page=page or 1, limit=limit or 50)
    return success_response(message="Earnings settlement summary retrieved", data=data)


@router.get("/earnings_export")
def admin_earnings_export_endpoint(
    caretaker_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/earnings_export
    """
    from app.services.admin_payout_service import get_admin_earnings_export

    data = get_admin_earnings_export(
        db=db,
        caretaker_user_id=caretaker_user_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response(message="Earnings export retrieved", data=data)


@router.post("/create_payout", status_code=201)
async def admin_create_payout_endpoint(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/create_payout
    """
    from app.services.admin_payout_service import create_admin_payout_batch

    try:
        body = await request.json()
    except Exception:
        body = {}

    caretaker_user_id = body.get("caretaker_user_id") if isinstance(body, dict) else None
    week_end = body.get("week_end") if isinstance(body, dict) else None
    force = body.get("force", "0") if isinstance(body, dict) else "0"
    admin_note = body.get("admin_note") if isinstance(body, dict) else None

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    data = create_admin_payout_batch(
        db=db,
        admin_user=current_admin,
        caretaker_user_id=caretaker_user_id,
        week_end=week_end,
        force=force,
        admin_note=admin_note,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return success_response(message="Payout created", data=data, status_code=201)


@router.post("/update_payout")
async def admin_update_payout_endpoint(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/update_payout
    """
    from app.services.admin_payout_service import update_admin_payout

    try:
        body = await request.json()
    except Exception:
        body = {}

    payout_id = body.get("id") if isinstance(body, dict) else None
    status = body.get("status") if isinstance(body, dict) else None
    payment_reference = body.get("payment_reference") if isinstance(body, dict) else None
    transaction_reference = body.get("transaction_reference") if isinstance(body, dict) else None
    payment_method = body.get("payment_method") if isinstance(body, dict) else None
    admin_note = body.get("admin_note") if isinstance(body, dict) else None

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    update_admin_payout(
        db=db,
        admin_user=current_admin,
        payout_id=payout_id,
        status=status,
        payment_method=payment_method,
        transaction_reference=transaction_reference,
        payment_reference=payment_reference,
        admin_note=admin_note,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return success_response(message="Payout updated", data=None, status_code=200)


@router.post("/refresh_payout_eligibility")
async def admin_refresh_payout_eligibility_endpoint(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/refresh_payout_eligibility
    """
    from app.services.admin_payout_service import refresh_admin_payout_eligibility

    try:
        body = await request.json()
    except Exception:
        body = {}

    booking_id = body.get("booking_id") if isinstance(body, dict) else None
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    counts = refresh_admin_payout_eligibility(
        db=db,
        admin_user=current_admin,
        booking_id=booking_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return success_response(message="Payout eligibility refreshed", data=counts, status_code=200)


@router.get("/reports_summary")
def admin_reports_summary_endpoint(
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/reports_summary
    """
    from app.services.admin_payout_service import get_admin_reports_summary

    data = get_admin_reports_summary(db=db)
    return success_response(message="Reports summary retrieved", data=data, status_code=200)


# ─────────────────────────────────────────────────────────────
# 27. Part 12C Admin Refund Processing
# ─────────────────────────────────────────────────────────────

@router.get("/refunds")
def admin_refunds_endpoint(
    page: Optional[str] = Query(None),
    limit: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/refunds
    """
    from app.services.admin_refund_service import get_admin_refunds_list

    data = get_admin_refunds_list(
        db=db,
        page=page,
        limit=limit,
        status=status,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    return success_response(message="Refunds retrieved", data=data, status_code=200)


@router.get("/refund_detail")
def admin_refund_detail_endpoint(
    id: Optional[str] = Query(None),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/refund_detail
    """
    from app.services.admin_refund_service import get_admin_refund_detail

    data = get_admin_refund_detail(db=db, refund_id=id)
    return success_response(message="Refund detail retrieved", data=data, status_code=200)


@router.post("/approve_refund")
async def admin_approve_refund_endpoint(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/approve_refund
    """
    from app.services.admin_refund_service import approve_admin_refund

    try:
        body = await request.json()
    except Exception:
        body = {}

    refund_id = body.get("refund_id") if isinstance(body, dict) else None
    admin_note = body.get("admin_note") if isinstance(body, dict) else None

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    data = approve_admin_refund(
        db=db,
        admin_user=current_admin,
        refund_id=refund_id,
        admin_note=admin_note,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return success_response(message="Refund approved", data=data, status_code=200)


@router.post("/reject_refund")
async def admin_reject_refund_endpoint(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/reject_refund
    """
    from app.services.admin_refund_service import reject_admin_refund

    try:
        body = await request.json()
    except Exception:
        body = {}

    refund_id = body.get("refund_id") if isinstance(body, dict) else None
    admin_note = body.get("admin_note") if isinstance(body, dict) else None

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    data = reject_admin_refund(
        db=db,
        admin_user=current_admin,
        refund_id=refund_id,
        admin_note=admin_note,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return success_response(message="Refund rejected", data=data, status_code=200)


@router.post("/mark_refund_processed")
async def admin_mark_refund_processed_endpoint(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/mark_refund_processed
    """
    from app.services.admin_refund_service import mark_admin_refund_processed

    try:
        body = await request.json()
    except Exception:
        body = {}

    refund_id = body.get("refund_id") if isinstance(body, dict) else None
    refund_method = body.get("refund_method") if isinstance(body, dict) else ""
    refund_transaction_id = body.get("refund_transaction_id") if isinstance(body, dict) else ""
    admin_note = body.get("admin_note") if isinstance(body, dict) else None

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    data = mark_admin_refund_processed(
        db=db,
        admin_user=current_admin,
        refund_id=refund_id,
        refund_method=refund_method,
        refund_transaction_id=refund_transaction_id,
        admin_note=admin_note,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return success_response(message="Refund marked processed", data=data, status_code=200)


# ── Admin Audit Logs (Part 12D) ──
@router.get("/audit_logs")
def admin_audit_logs_endpoint(
    page: Optional[int] = Query(default=1),
    limit: Optional[int] = Query(default=50),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/audit_logs
    """
    from app.services.admin_system_service import get_admin_audit_logs

    data = get_admin_audit_logs(db=db, page=page, limit=limit)
    return success_response(message="Audit logs retrieved", data=data, status_code=200)


# ── Notification History (Part 12D) ──
@router.get("/notification_history")
def admin_notification_history_endpoint(
    page: Optional[int] = Query(default=1),
    limit: Optional[int] = Query(default=50),
    target_role: Optional[str] = Query(default=""),
    type: Optional[str] = Query(default=""),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/notification_history
    """
    from app.services.admin_system_service import get_admin_notification_history

    data = get_admin_notification_history(
        db=db,
        page=page,
        limit=limit,
        target_role=target_role,
        type_filter=type,
    )
    return success_response(message="Notification history retrieved", data=data, status_code=200)


# ── Admin Notification Logs (Part 12D) ──
@router.get("/notifications/logs")
def admin_notifications_logs_endpoint(
    page: Optional[int] = Query(default=1),
    limit: Optional[int] = Query(default=20),
    target_role: Optional[str] = Query(default=""),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/notifications/logs
    """
    from app.services.admin_system_service import get_admin_notification_logs

    data = get_admin_notification_logs(
        db=db,
        page=page,
        limit=limit,
        target_role=target_role,
    )
    return success_response(message="Notification logs fetched successfully", data=data, status_code=200)


# ── Admin Notification Targets (Part 12D) ──
@router.get("/notifications/targets")
def admin_notifications_targets_endpoint(
    role: Optional[str] = Query(default=""),
    search: Optional[str] = Query(default=""),
    limit: Optional[int] = Query(default=100),
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/notifications/targets
    """
    from app.services.admin_system_service import get_admin_notification_targets

    data = get_admin_notification_targets(
        db=db,
        role=role,
        search=search,
        limit=limit,
    )
    return success_response(message="Notification targets fetched successfully", data=data, status_code=200)


# ── Admin Send Push Notifications (Part 12D) ──
@router.post("/notifications/send")
async def admin_notifications_send_endpoint(
    request: Request,
    current_admin: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/admin/notifications/send
    """
    from app.services.admin_system_service import send_admin_push_notifications

    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        body = {}

    data = send_admin_push_notifications(
        db=db,
        admin_user=current_admin,
        send_type=body.get("send_type"),
        target_user_id=body.get("target_user_id"),
        title=body.get("title"),
        body=body.get("body"),
        message=body.get("message"),
        notification_type=body.get("type", "admin_push"),
    )
    return success_response(message="Notification processed successfully", data=data, status_code=200)







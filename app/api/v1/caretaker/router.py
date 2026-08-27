"""
WeCare — Caretaker Routes

GET  /api/v1/caretaker/profile             → api/v1/caretaker/profile (GET)
POST /api/v1/caretaker/profile             → api/v1/caretaker/profile (POST)
GET  /api/v1/caretaker/list_caretaker      → api/v1/caretaker/list_caretaker
GET  /api/v1/caretaker/pricing_tiers       → api/v1/caretaker/pricing_tiers
POST /api/v1/caretaker/availability        → api/v1/caretaker/availability
POST /api/v1/caretaker/update_availability → api/v1/caretaker/update_availability
GET  /api/v1/caretaker/availability_status → api/v1/caretaker/availability_status
GET  /api/v1/caretaker/verification_status → api/v1/caretaker/verification_status
POST /api/v1/caretaker/upload_document     → api/v1/caretaker/upload_document
POST /api/v1/caretaker/upload_documents    → api/v1/caretaker/upload_documents
GET  /api/v1/caretaker/document_view       → api/v1/caretaker/document_view
"""

import math
import os
import re
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_caretaker
from app.schemas.caretaker import CaretakerProfileUpdateRequest
from app.services.availability_service import (
    caretaker_availability_payload,
    caretaker_has_active_visit,
    set_caretaker_availability,
    touch_caretaker_presence,
)
from app.services.caretaker_document_service import (
    build_caretaker_document_slots,
    build_caretaker_document_summary,
    caretaker_document_definitions,
    caretaker_document_rows_for_user,
    caretaker_document_safe_original_name,
    caretaker_document_status_for_storage,
    normalize_caretaker_document_type,
    update_caretaker_verification_status_from_documents,
)
from app.services.caretaker_earnings_service import (
    format_visit_label,
    get_caretaker_earnings_history,
    get_caretaker_earnings_summary,
    get_caretaker_recent_earnings,
)
from app.services.pricing_tier_service import list_active_pricing_tiers
from app.services.url_service import caretaker_document_view_url
from app.services.visit_history_service import get_caretaker_visit_history

router = APIRouter()


# ── Profile ─────────────────────────────────────────────────────────────

@router.get("/profile")
def get_caretaker_profile_route(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/profile (GET)
    """
    user_id = int(current_user["id"])
    touch_caretaker_presence(db, user_id)

    row = db.execute(
        text(
            "SELECT u.id, u.email, u.username, u.phone_number, u.role, "
            "       cp.*, "
            "       pt.name AS assigned_pricing_tier_name, "
            "       pt.slug AS assigned_pricing_tier_slug "
            "FROM users u "
            "LEFT JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "LEFT JOIN pricing_tiers pt ON pt.id = cp.pricing_tier_id "
            "WHERE u.id = :uid"
        ),
        {"uid": user_id},
    ).fetchone()

    profile: Dict[str, Any] = dict(row._mapping) if row else {}
    if profile:
        profile.pop("platform_commission_hourly", None)
        profile.pop("commission_percentage", None)
        profile.pop("payout_priority", None)

        doc_rows = caretaker_document_rows_for_user(db, user_id)
        profile["documents"] = doc_rows
        profile["document_map"] = build_caretaker_document_slots(doc_rows)
        profile["documents_by_type"] = profile["document_map"]

        # Date formatting
        for k in ["created_at", "updated_at", "date_of_birth", "last_active_at", "availability_updated_at", "availability_changed_at"]:
            if profile.get(k) is not None:
                val = profile[k]
                profile[k] = val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(val, "strftime") else str(val)

    return success_response(data=profile, message="Caretaker profile retrieved")


@router.post("/profile")
def update_caretaker_profile_route(
    body: CaretakerProfileUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/profile (POST)
    """
    user_id = int(current_user["id"])
    db.execute(
        text(
            "UPDATE caretaker_profiles SET "
            "full_name = :full_name, "
            "gender = :gender, "
            "date_of_birth = :date_of_birth, "
            "experience_years = :experience_years, "
            "qualification = :qualification, "
            "bio = :bio, "
            "address = :address, "
            "city = :city, "
            "state = :state, "
            "pincode = :pincode, "
            "verification_status = 'pending', "
            "is_available = 0, "
            "availability_reason = 'pending_review', "
            "manual_availability_enabled = 0, "
            "availability_changed_at = NOW(), "
            "availability_changed_by = 'system', "
            "availability_updated_at = NOW(), "
            "availability_version = availability_version + 1, "
            "updated_at = NOW() "
            "WHERE user_id = :uid"
        ),
        {
            "full_name": body.full_name,
            "gender": body.gender,
            "date_of_birth": body.date_of_birth,
            "experience_years": body.experience_years or 0,
            "qualification": body.qualification,
            "bio": body.bio,
            "address": body.address,
            "city": body.city,
            "state": body.state,
            "pincode": body.pincode,
            "uid": user_id,
        },
    )
    db.commit()

    return success_response(message="Caretaker profile updated. Waiting for admin approval.")


# ── Listing ─────────────────────────────────────────────────────────────

@router.get("/list_caretaker")
def list_caretaker_route(
    request: Request,
    available_only: Optional[str] = Query("true"),
    online_only: Optional[str] = Query("false"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    paginated: Optional[str] = Query("false"),
    search: Optional[str] = Query(""),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/list_caretaker
    """
    user_id = int(current_user["id"])
    role_str = str(current_user.get("role") or "")
    if role_str == "caretaker":
        touch_caretaker_presence(db, user_id)

    is_available_only = True
    if role_str == "admin" and str(available_only).lower() in ["false", "0", "no"]:
        is_available_only = False

    is_online_only = str(online_only).lower() in ["true", "1", "yes"]
    is_paginated = str(paginated).lower() in ["true", "1", "yes"]
    search_term = str(search or "").strip()

    where_clauses = [
        "u.role = 'caretaker'",
        "u.is_active = 1",
        "cp.verification_status = 'approved'",
    ]
    params: Dict[str, Any] = {}

    if is_available_only:
        where_clauses.append("cp.is_available = 1")

    if is_online_only:
        where_clauses.append("cp.last_active_at >= DATE_SUB(NOW(), INTERVAL 15 MINUTE)")

    if search_term:
        where_clauses.append(
            "(cp.full_name LIKE :search OR cp.city LIKE :search OR cp.skill_level LIKE :search OR cp.pricing_tier LIKE :search)"
        )
        params["search"] = f"%{search_term}%"

    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * limit

    # Count
    count_res = db.execute(
        text(
            f"SELECT COUNT(*) FROM users u "
            f"INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            f"WHERE {where_sql}"
        ),
        params,
    ).scalar()
    total = int(count_res or 0)

    # Fetch
    rows = db.execute(
        text(
            f"SELECT u.id AS user_id, u.username, u.email, u.phone_number, "
            f"       cp.full_name, cp.gender, cp.experience_years, cp.qualification, "
            f"       cp.bio, cp.pricing_tier, cp.skill_level, cp.customer_hourly_rate, "
            f"       cp.city, cp.state, cp.rating, cp.total_reviews, cp.verification_status, "
            f"       cp.is_available, cp.last_active_at "
            f"FROM users u "
            f"INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            f"WHERE {where_sql} "
            f"ORDER BY cp.is_available DESC, cp.last_active_at DESC, cp.rating DESC, cp.total_reviews DESC, cp.id DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    caretakers: List[Dict[str, Any]] = []
    now_ts = time.time()

    for r in rows:
        c = dict(r._mapping)
        c["is_available"] = int(c.get("is_available") or 0) == 1
        c["customer_hourly_rate"] = float(c["customer_hourly_rate"]) if c.get("customer_hourly_rate") is not None else None
        c["rating"] = float(c["rating"]) if c.get("rating") is not None else None

        last_active = c.get("last_active_at")
        if role_str != "admin":
            is_online = False
            if last_active:
                if hasattr(last_active, "timestamp"):
                    diff = now_ts - last_active.timestamp()
                else:
                    try:
                        parsed = datetime.fromisoformat(str(last_active))
                        diff = now_ts - parsed.timestamp()
                    except Exception:
                        diff = 999999
                is_online = diff < 900
            c["is_online"] = is_online
            c.pop("last_active_at", None)
        else:
            if last_active and hasattr(last_active, "strftime"):
                c["last_active_at"] = last_active.strftime("%Y-%m-%d %H:%M:%S")

        caretakers.append(c)

    if is_paginated:
        return success_response(
            data={
                "items": caretakers,
                "caretakers": caretakers,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "total_pages": math.ceil(total / limit) if limit > 0 else 0,
                },
            },
            message="Caretakers retrieved successfully",
        )

    return success_response(data=caretakers, message="Caretakers retrieved successfully")


# ── Pricing Tiers ────────────────────────────────────────────────────────

@router.get("/pricing_tiers")
def get_caretaker_pricing_tiers_route(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/pricing_tiers
    """
    tiers = list_active_pricing_tiers(db)
    return success_response(
        data={
            "tiers": tiers,
            "items": tiers,
            "count": len(tiers),
            "filters_supported": {
                "service_type": True,
                "city": True,
                "duration_days": True,
                "status": True,
                "is_active": True,
            },
        },
        message="Pricing tiers fetched successfully.",
    )


# ── Availability ────────────────────────────────────────────────────────

@router.post("/availability")
async def set_availability_route(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/availability
    """
    user_id = int(current_user["id"])
    body = await request.json()
    if "is_available" not in body or not isinstance(body["is_available"], bool):
        raise APIException(
            message="Valid is_available boolean is required",
            status_code=400,
            errors={"is_available": ["Only boolean true or false is accepted"]},
        )

    is_available_val = bool(body["is_available"])

    if is_available_val and caretaker_has_active_visit(db, user_id):
        raise APIException(
            message="Cannot enable availability during an active visit",
            status_code=409,
            errors={"is_available": ["Complete your current visit before changing availability"]},
        )

    reason = "manual_on" if is_available_val else "manual_off"
    result = set_caretaker_availability(
        db=db,
        caretaker_user_id=user_id,
        available=is_available_val,
        reason=reason,
        changed_by="caretaker",
        actor_user_id=user_id,
    )

    if not result["success"]:
        status_code = 403 if "locked by admin" in result.get("message", "") else 400
        raise APIException(
            message=result["message"],
            status_code=status_code,
            errors=result.get("errors"),
        )

    payload = caretaker_availability_payload(db, user_id) or {}
    availability_status = payload.get("availability_reason") or ("manual_on" if payload.get("is_available") else "manual_off")
    if payload.get("has_active_visit"):
        availability_status = "on_visit"

    return success_response(
        data={
            "is_available": bool(payload.get("is_available")),
            "availability_status": availability_status,
            "manual_availability_enabled": bool(payload.get("manual_availability_enabled")),
            "availability_locked_by_admin": bool(payload.get("availability_locked_by_admin")),
            "availability_reason": payload.get("availability_reason"),
            "availability_updated_at": payload.get("availability_changed_at"),
            "can_accept_booking": bool(payload.get("can_accept_booking")),
            "has_active_visit": bool(payload.get("has_active_visit")),
        },
        message="Availability updated",
    )


@router.post("/update_availability")
async def update_availability_alt_route(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/update_availability
    """
    user_id = int(current_user["id"])
    body = await request.json()
    if "is_available" not in body or not isinstance(body["is_available"], bool):
        raise APIException(
            message="Valid is_available boolean is required",
            status_code=400,
            errors={"is_available": ["Only boolean true or false is accepted"]},
        )

    is_available_val = bool(body["is_available"])
    reason = "manual_on" if is_available_val else "manual_off"

    # Pre-check admin lock
    prof = db.execute(
        text("SELECT availability_locked_by_admin FROM caretaker_profiles WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if prof and int(prof._mapping.get("availability_locked_by_admin") or 0) == 1:
        raise APIException(
            message="Caretaker availability is locked by admin",
            status_code=403,
            errors={"is_available": ["An administrator has locked your availability. Please contact support."]},
        )

    # Pre-check active visit
    if is_available_val and caretaker_has_active_visit(db, user_id):
        raise APIException(
            message="Cannot enable availability during an active visit",
            status_code=409,
            errors={"is_available": ["Complete your current visit before changing availability"]},
        )

    result = set_caretaker_availability(
        db=db,
        caretaker_user_id=user_id,
        available=is_available_val,
        reason=reason,
        changed_by="caretaker",
        actor_user_id=user_id,
    )

    if not result["success"]:
        status_code = 403 if "locked by admin" in result.get("message", "") else 400
        raise APIException(
            message=result["message"],
            status_code=status_code,
            errors=result.get("errors"),
        )

    res_data = result.get("data", {})
    return success_response(
        data={
            "is_available": res_data.get("is_available"),
            "manual_availability_enabled": res_data.get("manual_availability_enabled"),
            "availability_reason": res_data.get("availability_reason"),
            "availability_updated_at": res_data.get("availability_updated_at"),
            "availability_changed_at": res_data.get("availability_changed_at"),
            "availability_changed_by": res_data.get("availability_changed_by"),
        },
        message="Availability updated",
    )


@router.get("/availability_status")
def get_availability_status_route(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/availability_status
    """
    user_id = int(current_user["id"])
    touch_caretaker_presence(db, user_id)
    payload = caretaker_availability_payload(db, user_id)
    if not payload:
        raise APIException(message="Caretaker profile not found", status_code=404)

    return success_response(data=payload, message="Availability status retrieved")


# ── Documents & Verification ───────────────────────────────────────────

@router.get("/verification_status")
def get_verification_status_route(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/verification_status
    """
    user_id = int(current_user["id"])
    row = db.execute(
        text("SELECT verification_status, rejection_reason FROM caretaker_profiles WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchone()

    status_dict = dict(row._mapping) if row else {"verification_status": None, "rejection_reason": None}
    doc_summary = build_caretaker_document_summary(db, user_id, status_dict)
    summary = doc_summary["summary"]

    status_dict["verification_status"] = summary["effective_verification_status"]
    status_dict["caretaker_verification_status"] = status_dict["verification_status"]
    status_dict["is_verified"] = int(current_user.get("is_verified") or 0)
    status_dict["otp_verified"] = status_dict["is_verified"] == 1
    status_dict["account_status"] = "active" if (int(current_user.get("is_active") or 1) == 1) else "suspended"
    status_dict["message"] = (
        "Some documents were rejected. Please reupload them."
        if summary["rejected_documents_count"] > 0
        else ("All required documents are approved." if summary["all_required_approved"] else "Documents are pending review.")
    )
    status_dict["document_summary"] = summary

    docs = []
    for d in doc_summary["slots"].values():
        st = str(d.get("status") or "").lower()
        is_req = bool(d.get("required"))
        d_copy = dict(d)
        d_copy["needs_reupload"] = is_req and (st == "rejected")
        d_copy["blocks_verification"] = is_req and (st != "approved")
        docs.append(d_copy)

    status_dict["documents"] = docs
    status_dict["rejected_documents"] = [d for d in docs if str(d.get("status") or "").lower() == "rejected"]
    status_dict["document_map"] = doc_summary["slots"]
    status_dict["documents_by_type"] = doc_summary["slots"]

    return success_response(data=status_dict, message="Verification status retrieved")


@router.post("/upload_document", status_code=201)
async def upload_document_route(
    document_type: str = Form(...),
    document: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/upload_document
    """
    user_id = int(current_user["id"])
    canonical_type = normalize_caretaker_document_type(document_type)
    if not canonical_type:
        raise APIException(
            message="Invalid document type",
            status_code=400,
            errors={"document_type": ["Use id_proof_front, id_proof_back, training_certificate, experience_proof, or police_verification"]},
        )

    file_bytes = await document.read()
    file_size = len(file_bytes)

    if file_size <= 0:
        raise APIException(
            message="Document file is invalid",
            status_code=400,
            errors={"document": ["File is empty or corrupted"]},
        )

    if file_size > 5 * 1024 * 1024:
        raise APIException(
            message="Document is too large",
            status_code=400,
            errors={"document": ["Maximum file size is 5MB"]},
        )

    allowed_types = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
    }

    mime_type = document.content_type or ""
    if file_bytes.startswith(b"%PDF"):
        mime_type = "application/pdf"
    elif file_bytes.startswith(b"\xff\xd8\xff"):
        mime_type = "image/jpeg"
    elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"

    if mime_type not in allowed_types:
        raise APIException(
            message="Invalid document type",
            status_code=400,
            errors={"document": ["Allowed file types are pdf, jpg, jpeg and png"]},
        )

    upload_dir = os.path.join(os.getcwd(), "uploads", "caretaker_docs")
    os.makedirs(upload_dir, exist_ok=True)

    safe_base = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.splitext(document.filename or "doc")[0])
    file_name = f"{secrets.token_hex(12)}_{safe_base}.{allowed_types[mime_type]}"
    target_path = os.path.join(upload_dir, file_name)
    db_path = f"uploads/caretaker_docs/{file_name}"

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    aliases = caretaker_document_definitions()[canonical_type]["aliases"]
    placeholders = ", ".join([f":a{i}" for i in range(len(aliases))])
    params: Dict[str, Any] = {"uid": user_id}
    for i, a in enumerate(aliases):
        params[f"a{i}"] = a

    existing = db.execute(
        text(
            f"SELECT id, file_path FROM documents "
            f"WHERE user_id = :uid AND document_type IN ({placeholders}) "
            f"ORDER BY id DESC LIMIT 1"
        ),
        params,
    ).fetchone()

    old_file_to_delete = None
    stored_status = caretaker_document_status_for_storage("reuploaded" if existing else "pending")

    try:
        if existing:
            doc_id = int(existing._mapping["id"])
            old_path = existing._mapping.get("file_path")
            if old_path and old_path != db_path:
                old_file_to_delete = os.path.join(os.getcwd(), old_path.replace("/", os.sep))

            db.execute(
                text(
                    "UPDATE documents "
                    "SET document_type = :dt, file_path = :fp, status = :st, admin_note = NULL, "
                    "    uploaded_at = NOW(), updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {"dt": canonical_type, "fp": db_path, "st": stored_status, "id": doc_id},
            )
        else:
            res = db.execute(
                text(
                    "INSERT INTO documents (user_id, document_type, file_path, status, uploaded_at, updated_at) "
                    "VALUES (:uid, :dt, :fp, :st, NOW(), NOW())"
                ),
                {"uid": user_id, "dt": canonical_type, "fp": db_path, "st": stored_status},
            )
            doc_id = res.lastrowid

        update_caretaker_verification_status_from_documents(db, user_id, "pending_review")
        db.commit()
    except Exception as e:
        db.rollback()
        if os.path.exists(target_path):
            os.unlink(target_path)
        raise APIException(message="Document upload failed", status_code=500)

    if old_file_to_delete and os.path.exists(old_file_to_delete):
        try:
            os.unlink(old_file_to_delete)
        except Exception:
            pass

    return success_response(
        data={
            "document_id": doc_id,
            "document_type": canonical_type,
            "status": stored_status,
            "file_path": db_path,
            "view_url": caretaker_document_view_url(doc_id),
        },
        message="Document uploaded successfully",
        status_code=201,
    )


@router.post("/upload_documents", status_code=201)
async def upload_documents_bulk_route(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/upload_documents
    Uses SELECT ... FOR UPDATE row locks.
    """
    user_id = int(current_user["id"])
    form = await request.form()
    defs = caretaker_document_definitions()
    required_types = ["id_proof_front", "id_proof_back", "training_certificate", "police_verification"]
    allowed_mimes = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
    }
    max_size = 5 * 1024 * 1024

    errors: Dict[str, List[str]] = {}
    validated_files: Dict[str, Dict[str, Any]] = {}

    for field, definition in defs.items():
        is_req = field in required_types
        # Find file by alias
        file_obj = None
        for alias in definition["aliases"]:
            if alias in form:
                f_candidate = form[alias]
                if isinstance(f_candidate, UploadFile):
                    file_obj = f_candidate
                    break

        if not file_obj or not file_obj.filename:
            if is_req:
                errors[field] = [f"{definition['label']} file is required"]
            continue

        file_bytes = await file_obj.read()
        file_size = len(file_bytes)

        if file_size <= 0:
            errors[field] = ["File is empty or corrupted"]
            continue

        if file_size > max_size:
            errors[field] = ["Maximum file size is 5MB"]
            continue

        mime_type = file_obj.content_type or ""
        if file_bytes.startswith(b"%PDF"):
            mime_type = "application/pdf"
        elif file_bytes.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"

        if mime_type not in allowed_mimes:
            errors[field] = ["Allowed file types are pdf, jpg, jpeg and png"]
            continue

        validated_files[field] = {
            "bytes": file_bytes,
            "extension": allowed_mimes[mime_type],
            "original_file_name": caretaker_document_safe_original_name(file_obj.filename),
        }

    if errors:
        has_missing_req = any(
            any("file is required" in msg for msg in msgs)
            for f, msgs in errors.items()
            if f in required_types
        )
        raise APIException(
            message="Required documents missing" if has_missing_req else "Document validation failed",
            status_code=400,
            errors=errors,
        )

    upload_dir = os.path.join(os.getcwd(), "uploads", "caretaker_docs")
    os.makedirs(upload_dir, exist_ok=True)
    moved_files: Dict[str, Dict[str, Any]] = {}
    old_files_to_delete: List[str] = []
    documents_result: Dict[str, Dict[str, Any]] = {}

    try:
        for field, info in validated_files.items():
            file_name = f"{field}_{int(time.time()*1000)}_{secrets.token_hex(8)}.{info['extension']}"
            target_path = os.path.join(upload_dir, file_name)
            with open(target_path, "wb") as f:
                f.write(info["bytes"])

            moved_files[field] = {
                "absolute_path": target_path,
                "relative_path": f"uploads/caretaker_docs/{file_name}",
                "original_file_name": info["original_file_name"],
            }

        # FOR UPDATE lock loop
        for doc_type, file_info in moved_files.items():
            aliases = defs[doc_type]["aliases"]
            placeholders = ", ".join([f":a{i}" for i in range(len(aliases))])
            params = {"uid": user_id}
            for i, a in enumerate(aliases):
                params[f"a{i}"] = a

            existing = db.execute(
                text(
                    f"SELECT id, file_path FROM documents "
                    f"WHERE user_id = :uid AND document_type IN ({placeholders}) "
                    f"ORDER BY id DESC LIMIT 1 FOR UPDATE"
                ),
                params,
            ).fetchone()

            if existing:
                doc_id = int(existing._mapping["id"])
                stored_status = caretaker_document_status_for_storage("reuploaded")
                old_path = existing._mapping.get("file_path")
                if old_path and old_path != file_info["relative_path"]:
                    old_files_to_delete.append(os.path.join(os.getcwd(), old_path.replace("/", os.sep)))

                db.execute(
                    text(
                        "UPDATE documents "
                        "SET file_path = :fp, status = :st, admin_note = NULL, "
                        "    uploaded_at = NOW(), updated_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {"fp": file_info["relative_path"], "st": stored_status, "id": doc_id},
                )
            else:
                stored_status = caretaker_document_status_for_storage("pending")
                res = db.execute(
                    text(
                        "INSERT INTO documents (user_id, document_type, file_path, status, uploaded_at, updated_at) "
                        "VALUES (:uid, :dt, :fp, :st, NOW(), NOW())"
                    ),
                    {
                        "uid": user_id,
                        "dt": doc_type,
                        "fp": file_info["relative_path"],
                        "st": stored_status,
                    },
                )
                doc_id = res.lastrowid

            documents_result[doc_type] = {
                "document_id": doc_id,
                "document_type": doc_type,
                "file_path": file_info["relative_path"],
                "view_url": caretaker_document_view_url(doc_id),
                "status": stored_status,
            }

        update_caretaker_verification_status_from_documents(db, user_id, "pending_review")
        db.commit()
    except Exception as e:
        db.rollback()
        for f_info in moved_files.values():
            if os.path.exists(f_info["absolute_path"]):
                os.unlink(f_info["absolute_path"])
        raise APIException(message="Documents upload failed", status_code=500)

    for old_p in old_files_to_delete:
        if os.path.exists(old_p):
            try:
                os.unlink(old_p)
            except Exception:
                pass

    return success_response(
        data={
            "uploaded_count": len(documents_result),
            "documents": documents_result,
        },
        message="Documents uploaded successfully",
        status_code=201,
    )


@router.get("/document_view")
def document_view_route(
    id: Optional[str] = Query(None),
    debug: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/document_view
    """
    if not id or not str(id).isdigit() or int(id) < 1:
        raise APIException(
            message="Validation failed",
            status_code=400,
            errors={"id": ["Document id must be a positive integer"]},
        )

    doc_id = int(id)
    user_id = int(current_user["id"])
    role_str = str(current_user.get("role") or "")
    if role_str not in ["admin", "caretaker"]:
        raise APIException(message="You do not have permission to perform this action.", status_code=403)

    row = db.execute(
        text("SELECT id, user_id, document_type, file_path FROM documents WHERE id = :id LIMIT 1"),
        {"id": doc_id},
    ).fetchone()

    if not row or normalize_caretaker_document_type(row._mapping.get("document_type")) is None:
        raise APIException(message="Document not found", status_code=404)

    doc = row._mapping
    if role_str == "caretaker" and int(doc["user_id"]) != user_id:
        raise APIException(message="You do not have permission to perform this action.", status_code=403)

    rel_path = str(doc.get("file_path") or "").replace("\\", "/").lstrip("/")
    if not rel_path.startswith("uploads/caretaker_docs/"):
        raise APIException(message="Document file is unavailable", status_code=404)

    full_path = os.path.join(os.getcwd(), rel_path.replace("/", os.sep))
    file_exists = os.path.isfile(full_path)
    file_size = os.path.getsize(full_path) if file_exists else 0

    mime = "application/octet-stream"
    if rel_path.endswith(".pdf"):
        mime = "application/pdf"
    elif rel_path.endswith(".jpg") or rel_path.endswith(".jpeg"):
        mime = "image/jpeg"
    elif rel_path.endswith(".png"):
        mime = "image/png"
    elif rel_path.endswith(".webp"):
        mime = "image/webp"

    if debug == "1":
        if role_str != "admin":
            raise APIException(message="You do not have permission to perform this action.", status_code=403)
        return success_response(
            data={
                "document_id": doc_id,
                "expected_view_url": caretaker_document_view_url(doc_id),
                "stored_file_path": rel_path,
                "file_exists": file_exists,
                "file_size": file_size,
                "mime": mime,
                "cors_allowed": True,
            },
            message="Document debug info",
        )

    if not file_exists or file_size <= 0:
        raise APIException(message="Document file is unavailable", status_code=404)

    download_name = os.path.basename(full_path)
    return FileResponse(
        path=full_path,
        media_type=mime,
        headers={
            "Content-Disposition": f'inline; filename="{download_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── Caretaker Booking Routes ──────────────────────────────────────────

@router.get("/booking_detail")
def get_caretaker_booking_detail_route(
    booking_id: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/booking_detail
    """
    from app.services.booking_service import get_caretaker_booking_detail

    if not booking_id:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id is required"]},
            status_code=400,
        )

    try:
        bid = int(booking_id)
    except ValueError:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    result = get_caretaker_booking_detail(
        db=db,
        caretaker_user_id=int(current_user["id"]),
        booking_id=bid,
    )
    return success_response(data=result, message="Booking details retrieved")


@router.get("/requests")
def get_caretaker_legacy_requests_route(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/requests
    """
    from app.services.booking_service import get_legacy_caretaker_requests

    result = get_legacy_caretaker_requests(
        db=db,
        caretaker_user_id=int(current_user["id"]),
        page=page,
        limit=limit,
    )
    return success_response(data=result, message="Booking requests retrieved")


# ── Feedback ────────────────────────────────────────────────────────────

@router.post("/submit_feedback")
def submit_feedback_route(
    req: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/submit_feedback
    Allows approved caretakers to submit feedback and suggestions.
    """
    from app.services.review_service import submit_caretaker_feedback

    submit_caretaker_feedback(
        db=db,
        caretaker_user=current_user,
        data=req,
    )
    return success_response("Feedback submitted successfully", None)


# ── Part 12A Caretaker Endpoints ─────────────────────────────────────────

# ── 1. Legacy Caretaker Dashboard ────────────────────────────────────────
@router.get("/dashboard")
def get_legacy_caretaker_dashboard_route(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/dashboard
    """
    user_id = int(current_user["id"])
    touch_caretaker_presence(db, user_id)

    # 1. Caretaker profile
    profile_row = db.execute(
        text("SELECT cp.full_name, cp.verification_status FROM caretaker_profiles cp WHERE cp.user_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).fetchone()

    if not profile_row:
        raise APIException(message="Caretaker profile not found", status_code=404)

    profile = dict(profile_row._mapping)

    # 2. Availability
    availability = caretaker_availability_payload(db, user_id)
    if not availability:
        raise APIException(message="Caretaker availability profile not found", status_code=404)

    # 3. Today's visits
    todays_visits_row = db.execute(
        text(
            "SELECT COUNT(*) FROM bookings "
            "WHERE caretaker_user_id = :uid "
            "  AND booking_date = CURDATE() "
            "  AND status IN ('accepted','in_progress','completed')"
        ),
        {"uid": user_id},
    ).fetchone()
    todays_visits = int(todays_visits_row[0]) if todays_visits_row else 0

    # 4. New requests count
    new_requests_count_row = db.execute(
        text("SELECT COUNT(*) FROM bookings WHERE caretaker_user_id = :uid AND status = 'pending'"),
        {"uid": user_id},
    ).fetchone()
    new_requests_count = int(new_requests_count_row[0]) if new_requests_count_row else 0

    def _dashboard_booking_row(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "booking_id": int(row["booking_id"]),
            "patient_name": row.get("patient_name") or "",
            "service_type": row.get("service_type") or "",
            "booking_date": str(row["booking_date"]) if row.get("booking_date") else None,
            "start_time": str(row["start_time"]) if row.get("start_time") else None,
            "end_time": str(row["end_time"]) if row.get("end_time") else None,
            "visit_label": format_visit_label(row.get("start_time"), row.get("end_time")),
            "address": row.get("address") or "",
            "status": row.get("status") or "",
        }

    # 5. Active visit
    active_visit_row = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "       b.address, b.status, p.patient_name, "
            "       vt.id AS visit_id, vt.check_in_time "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "LEFT JOIN visit_tracking vt "
            "  ON vt.booking_id = b.id "
            " AND vt.caretaker_user_id = b.caretaker_user_id "
            " AND vt.check_out_time IS NULL "
            "WHERE b.caretaker_user_id = :uid "
            "  AND b.status = 'in_progress' "
            "ORDER BY vt.check_in_time DESC, b.id DESC "
            "LIMIT 1"
        ),
        {"uid": user_id},
    ).fetchone()

    active_visit = None
    if active_visit_row:
        avr = dict(active_visit_row._mapping)
        active_visit = _dashboard_booking_row(avr)
        active_visit["visit_id"] = int(avr["visit_id"]) if avr.get("visit_id") is not None else None
        check_in_val = avr.get("check_in_time")
        active_visit["check_in_time"] = check_in_val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(check_in_val, "strftime") else (str(check_in_val) if check_in_val else None)
        active_visit["can_check_out"] = True
        active_visit["sos_available"] = True

    # 6. Upcoming visits
    upcoming_rows = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "       b.address, b.status, p.patient_name "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE b.caretaker_user_id = :uid "
            "  AND b.status = 'accepted' "
            "  AND ( "
            "    b.booking_date > CURDATE() "
            "    OR (b.booking_date = CURDATE() AND b.start_time >= CURTIME()) "
            "  ) "
            "ORDER BY b.booking_date ASC, b.start_time ASC, b.id ASC "
            "LIMIT 5"
        ),
        {"uid": user_id},
    ).fetchall()
    upcoming_visits = [_dashboard_booking_row(dict(r._mapping)) for r in upcoming_rows]

    # 7. New requests (LIMIT 5)
    new_req_rows = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "       b.address, b.status, p.patient_name "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE b.caretaker_user_id = :uid "
            "  AND b.status = 'pending' "
            "ORDER BY b.created_at DESC, b.id DESC "
            "LIMIT 5"
        ),
        {"uid": user_id},
    ).fetchall()
    new_requests = [_dashboard_booking_row(dict(r._mapping)) for r in new_req_rows]

    # 8. Availability status logic
    availability_status = availability.get("availability_reason") or ("manual_on" if availability.get("is_available") else "manual_off")
    if availability.get("has_active_visit"):
        availability_status = "on_visit"

    verification_status = str(profile.get("verification_status") or "pending")

    return success_response(
        message="Caretaker dashboard loaded",
        data={
            "caretaker": {
                "id": user_id,
                "name": profile.get("full_name") or current_user.get("username") or "",
                "availability_status": availability_status,
                "is_available": bool(availability.get("is_available")),
                "manual_availability_enabled": bool(availability.get("manual_availability_enabled")),
                "availability_locked_by_admin": bool(availability.get("availability_locked_by_admin")),
                "availability_reason": availability.get("availability_reason"),
                "can_accept_booking": bool(availability.get("can_accept_booking")),
                "has_active_visit": bool(availability.get("has_active_visit")),
                "availability_updated_at": availability.get("availability_changed_at"),
                "verification_status": verification_status,
            },
            "summary": {
                "todays_visits": todays_visits,
                "new_requests": new_requests_count,
            },
            "active_visit": active_visit,
            "upcoming_visits": upcoming_visits,
            "new_requests": new_requests,
            "capabilities": {
                "can_toggle_availability": (
                    verification_status == "approved"
                    and not availability.get("availability_locked_by_admin")
                    and not availability.get("has_active_visit")
                ),
                "sos_available": active_visit is not None,
            },
        },
    )


# ── 2. Earnings Dashboard ────────────────────────────────────────────────
@router.get("/earnings_dashboard")
@router.get("/earnings-dashboard", include_in_schema=False)
def get_caretaker_earnings_dashboard_route(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/earnings_dashboard
    """
    user_id = int(current_user["id"])
    summary = get_caretaker_earnings_summary(db, user_id)
    summary["recent_earnings"] = get_caretaker_recent_earnings(db, user_id, 3)
    return success_response(data=summary, message="Earnings dashboard retrieved")


# ── 3. Earnings History ──────────────────────────────────────────────────
@router.get("/earnings_history")
@router.get("/earnings-history", include_in_schema=False)
def get_caretaker_earnings_history_route(
    request: Request,
    page: Optional[str] = Query(None),
    limit: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/earnings_history
    """
    user_id = int(current_user["id"])
    p_raw = page if page is not None else request.query_params.get("page", 1)
    l_raw = limit if limit is not None else request.query_params.get("limit", 20)
    st_raw = status if status is not None else request.query_params.get("status", "all")
    s_date = start_date if start_date is not None else request.query_params.get("start_date")
    e_date = end_date if end_date is not None else request.query_params.get("end_date")

    result = get_caretaker_earnings_history(
        db=db,
        caretaker_user_id=user_id,
        page_raw=p_raw,
        limit_raw=l_raw,
        status=st_raw,
        start_date=s_date,
        end_date=e_date,
    )
    return success_response(data=result, message="Earnings history retrieved")


# ── 4. Payout Summary ────────────────────────────────────────────────────
@router.get("/payout_summary")
@router.get("/payout-summary", include_in_schema=False)
def get_caretaker_payout_summary_route(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/payout_summary
    """
    user_id = int(current_user["id"])
    summary = get_caretaker_earnings_summary(db, user_id)
    return success_response(
        message="Payout summary retrieved",
        data={
            "currency": summary["currency"],
            "ready_for_payout": summary["ready_for_payout"],
            "hold_earnings": summary["hold_earnings"],
            "paid_earnings": summary["paid_earnings"],
            "disputed_earnings": summary["disputed_earnings"],
            "next_payout_date": summary["next_payout_date"],
            "payout_note": summary["payout_note"],
            "manual_withdrawal_supported": False,
        },
    )


# ── 5. Visit History ─────────────────────────────────────────────────────
@router.get("/visit_history")
@router.get("/visit-history", include_in_schema=False)
def get_caretaker_visit_history_route(

    request: Request,
    page: Optional[str] = Query(None),
    limit: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    patient_name: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/caretaker/visit_history
    """
    user_id = int(current_user["id"])
    p_raw = page if page is not None else request.query_params.get("page", 1)
    l_raw = limit if limit is not None else request.query_params.get("limit", 20)
    st_raw = status if status is not None else request.query_params.get("status", "")
    s_date = start_date if start_date is not None else request.query_params.get("start_date", "")
    e_date = end_date if end_date is not None else request.query_params.get("end_date", "")
    p_name = patient_name if patient_name is not None else request.query_params.get("patient_name", "")

    result = get_caretaker_visit_history(
        db=db,
        caretaker_user_id=user_id,
        page_raw=p_raw,
        limit_raw=l_raw,
        status_param=st_raw,
        start_date=s_date,
        end_date=e_date,
        patient_name=p_name,
    )
    return success_response(data=result, message="Visit history fetched successfully")




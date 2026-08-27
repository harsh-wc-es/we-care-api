"""
WeCare — Caretaker Document & Verification Service

Mirrors helpers/caretaker_documents.
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.url_service import caretaker_document_view_url


def caretaker_document_definitions() -> Dict[str, Dict[str, Any]]:
    """
    Route: caretaker_document_definitions() — helpers/caretaker_documents L3-32
    """
    return {
        "id_proof_front": {
            "label": "ID Proof Front",
            "required": True,
            "aliases": ["id_proof_front", "id_front"],
        },
        "id_proof_back": {
            "label": "ID Proof Back",
            "required": True,
            "aliases": ["id_proof_back", "id_back"],
        },
        "training_certificate": {
            "label": "Training Certificate",
            "required": True,
            "aliases": ["training_certificate", "training", "certificate"],
        },
        "experience_proof": {
            "label": "Experience Proof",
            "required": False,
            "aliases": ["experience_proof", "experience_document", "experience"],
        },
        "police_verification": {
            "label": "Police Verification",
            "required": True,
            "aliases": ["police_verification", "police", "police_certificate", "non_criminal_certificate"],
        },
    }


def normalize_caretaker_document_type(doc_type: Optional[str]) -> Optional[str]:
    """
    Route: normalize_caretaker_document_type() — helpers/caretaker_documents L34-44
    """
    if not doc_type:
        return None
    cleaned = str(doc_type).lower().strip()
    for canonical, definition in caretaker_document_definitions().items():
        if cleaned in definition["aliases"]:
            return canonical
    return None


def caretaker_document_safe_original_name(name: Optional[str]) -> Optional[str]:
    """
    Route: caretaker_document_safe_original_name() — helpers/caretaker_documents L389-398
    """
    if not name:
        return None
    name_str = str(name).strip()
    if not name_str:
        return None
    base = os.path.basename(name_str)
    cleaned = re.sub(r"[\x00-\x1F\x7F]+", "", base)
    return cleaned[:255] if cleaned else None


def caretaker_required_document_types() -> List[str]:
    """
    Route: caretaker_required_document_types() — helpers/caretaker_documents L212-218
    """
    return [k for k, v in caretaker_document_definitions().items() if v.get("required", True)]


def caretaker_optional_document_types() -> List[str]:
    """
    Route: caretaker_optional_document_types() — helpers/caretaker_documents L220-226
    """
    return [k for k, v in caretaker_document_definitions().items() if not v.get("required", True)]


def caretaker_is_banned_payload(row: Dict[str, Any]) -> bool:
    """
    Route: caretaker_is_banned_payload() — helpers/caretaker_documents L228-232
    """
    return int(row.get("is_banned") or 0) == 1 or row.get("verification_status") == "banned"


def caretaker_profile_status_for_storage(desired_status: str) -> str:
    """
    Route: caretaker_profile_status_for_storage() — helpers/caretaker_documents L179-196
    Live MySQL enum is ('pending', 'approved', 'rejected')
    """
    fallbacks = {
        "pending_review": "pending",
        "needs_resubmission": "rejected",
        "banned": "rejected",
        "approved": "approved",
        "rejected": "rejected",
        "pending": "pending",
    }
    return fallbacks.get(desired_status, "pending")


def caretaker_document_status_for_storage(desired_status: str) -> str:
    """
    Route: caretaker_document_status_for_storage() — helpers/caretaker_documents L198-210
    Live MySQL enum is ('uploaded', 'pending', 'approved', 'rejected')
    """
    if desired_status == "reuploaded":
        return "pending"
    if desired_status in ["approved", "rejected", "pending", "uploaded"]:
        return desired_status
    return "pending"


def build_caretaker_document_slots(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Route: build_caretaker_document_slots() — helpers/caretaker_documents L68-130
    """
    slots: Dict[str, Dict[str, Any]] = {}
    for canonical, definition in caretaker_document_definitions().items():
        req = bool(definition.get("required", True))
        slots[canonical] = {
            "document_id": None,
            "id": None,
            "document_type": canonical,
            "label": definition["label"],
            "display_name": definition["label"],
            "required": req,
            "optional": not req,
            "uploaded": False,
            "status": None,
            "file_url": None,
            "view_url": None,
            "original_file_name": None,
            "uploaded_at": None,
            "admin_note": None,
            "rejection_reason": None,
            "reviewed_by_admin_id": None,
            "reviewed_at": None,
            "can_reupload": True,
        }

    for row in rows:
        canonical = normalize_caretaker_document_type(row.get("document_type"))
        if canonical is None or slots[canonical]["uploaded"]:
            continue

        doc_id = int(row.get("id") or 0)
        status = row.get("status")
        can_reupload = status != "approved"
        definition = caretaker_document_definitions()[canonical]
        req = bool(definition.get("required", True))
        file_path = row.get("file_path")

        slots[canonical] = {
            "document_id": doc_id if doc_id > 0 else None,
            "id": doc_id if doc_id > 0 else None,
            "document_type": canonical,
            "stored_document_type": row.get("document_type") or canonical,
            "label": definition["label"],
            "display_name": definition["label"],
            "required": req,
            "optional": not req,
            "uploaded": doc_id > 0 and bool(file_path),
            "status": status,
            "file_url": caretaker_document_view_url(doc_id) if doc_id > 0 else None,
            "view_url": caretaker_document_view_url(doc_id) if doc_id > 0 else None,
            "original_file_name": row.get("original_file_name"),
            "uploaded_at": str(row.get("uploaded_at") or row.get("created_at") or ""),
            "admin_note": row.get("admin_note") or row.get("rejection_reason"),
            "rejection_reason": row.get("rejection_reason") or row.get("admin_note"),
            "reviewed_by_admin_id": int(row["reviewed_by_admin_id"]) if row.get("reviewed_by_admin_id") is not None else None,
            "reviewed_at": str(row.get("reviewed_at")) if row.get("reviewed_at") else None,
            "can_reupload": can_reupload,
        }

    return slots


def caretaker_document_rows_for_user(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """
    Route: caretaker_document_rows_for_user() — helpers/caretaker_documents L400-437
    """
    rows = db.execute(
        text(
            "SELECT id, document_type, file_path, status, admin_note, uploaded_at, updated_at "
            "FROM documents "
            "WHERE user_id = :uid "
            "ORDER BY id DESC"
        ),
        {"uid": int(user_id)},
    ).fetchall()

    results = []
    for r in rows:
        m = r._mapping
        up_at = m.get("uploaded_at")
        upd_at = m.get("updated_at")
        up_str = up_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(up_at, "strftime") else (str(up_at) if up_at else None)
        results.append({
            "id": int(m["id"]),
            "document_type": m.get("document_type"),
            "file_path": m.get("file_path"),
            "status": m.get("status"),
            "admin_note": m.get("admin_note"),
            "created_at": up_str,
            "uploaded_at": up_str,
            "updated_at": upd_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(upd_at, "strftime") else (str(upd_at) if upd_at else None),
            "original_file_name": None,
            "rejection_reason": m.get("admin_note"),
            "reviewed_by_admin_id": None,
            "reviewed_at": None,
        })
    return results


def build_caretaker_document_summary(
    db: Session,
    caretaker_user_id: int,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Route: build_caretaker_document_summary() — helpers/caretaker_documents L234-343
    """
    rows = caretaker_document_rows_for_user(db, caretaker_user_id)
    slots = build_caretaker_document_slots(rows)
    required_types = caretaker_required_document_types()
    optional_types = caretaker_optional_document_types()

    summary = {
        "total_required_documents": len(required_types),
        "uploaded_documents_count": 0,
        "pending_documents_count": 0,
        "approved_documents_count": 0,
        "rejected_documents_count": 0,
        "missing_documents_count": 0,
        "latest_reupload_at": None,
        "required_document_types": required_types,
        "optional_document_types": optional_types,
        "optional_documents_count": len(optional_types),
        "optional_uploaded_documents_count": 0,
        "optional_pending_documents_count": 0,
        "optional_approved_documents_count": 0,
        "optional_rejected_documents_count": 0,
        "all_required_uploaded": False,
        "all_required_approved": False,
        "has_pending_documents": False,
        "has_rejected_documents": False,
    }

    for t in required_types:
        slot = slots.get(t) or {}
        uploaded = bool(slot.get("uploaded"))
        status = str(slot.get("status") or "").lower()

        if not uploaded:
            summary["missing_documents_count"] += 1
            continue

        summary["uploaded_documents_count"] += 1
        if status == "approved":
            summary["approved_documents_count"] += 1
        elif status == "rejected":
            summary["rejected_documents_count"] += 1
            summary["has_rejected_documents"] = True
        else:
            summary["pending_documents_count"] += 1
            summary["has_pending_documents"] = True

        up_at = slot.get("uploaded_at")
        if up_at and (not summary["latest_reupload_at"] or str(up_at) > str(summary["latest_reupload_at"])):
            summary["latest_reupload_at"] = str(up_at)

    for t in optional_types:
        slot = slots.get(t) or {}
        uploaded = bool(slot.get("uploaded"))
        status = str(slot.get("status") or "").lower()

        if not uploaded:
            continue

        summary["optional_uploaded_documents_count"] += 1
        if status == "approved":
            summary["optional_approved_documents_count"] += 1
        elif status == "rejected":
            summary["optional_rejected_documents_count"] += 1
        else:
            summary["optional_pending_documents_count"] += 1

        up_at = slot.get("uploaded_at")
        if up_at and (not summary["latest_reupload_at"] or str(up_at) > str(summary["latest_reupload_at"])):
            summary["latest_reupload_at"] = str(up_at)

    summary["all_required_uploaded"] = summary["missing_documents_count"] == 0
    summary["all_required_approved"] = summary["approved_documents_count"] == summary["total_required_documents"]

    is_banned = caretaker_is_banned_payload(profile) if profile else False
    profile_status = profile.get("verification_status") if profile else None

    effective_status = "pending_review"
    if is_banned:
        effective_status = "banned"
    elif profile_status == "approved" and summary["all_required_approved"]:
        effective_status = "approved"
    elif summary["has_rejected_documents"]:
        effective_status = "needs_resubmission"
    elif not summary["all_required_uploaded"] or summary["has_pending_documents"]:
        effective_status = "pending_review"
    elif summary["all_required_approved"]:
        effective_status = "approved" if profile_status == "approved" else "pending_review"

    summary["effective_verification_status"] = effective_status
    summary["can_approve"] = not is_banned and summary["all_required_approved"] and profile_status != "approved"
    total_uploaded = summary["uploaded_documents_count"] + summary["optional_uploaded_documents_count"]
    summary["total_uploaded_documents_count"] = total_uploaded
    summary["can_reject"] = not is_banned and total_uploaded > 0 and profile_status != "approved"
    summary["can_ban"] = not is_banned
    summary["can_unban"] = is_banned

    return {
        "rows": rows,
        "slots": slots,
        "summary": summary,
    }


def update_caretaker_verification_status_from_documents(
    db: Session,
    caretaker_user_id: int,
    force_status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: update_caretaker_verification_status_from_documents() — helpers/caretaker_documents L345-387
    """
    row = db.execute(
        text(
            "SELECT cp.user_id, cp.verification_status, cp.is_available, u.is_active AS user_is_active "
            "FROM caretaker_profiles cp "
            "INNER JOIN users u ON u.id = cp.user_id "
            "WHERE cp.user_id = :cid "
            "LIMIT 1"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    if not row:
        return {"status": None, "summary": None}

    profile = dict(row._mapping)
    document_payload = build_caretaker_document_summary(db, caretaker_user_id, profile)
    summary = document_payload["summary"]

    desired = force_status if force_status else summary["effective_verification_status"]
    if desired == "approved" and not summary["all_required_approved"]:
        desired = "needs_resubmission" if summary["has_rejected_documents"] else "pending_review"

    storage_status = caretaker_profile_status_for_storage(desired)
    set_parts = ["verification_status = :storage_status"]
    params: Dict[str, Any] = {
        "storage_status": storage_status,
        "cid": int(caretaker_user_id),
    }

    if desired in ["pending_review", "needs_resubmission", "rejected", "banned"]:
        set_parts.append("is_available = 0")
        set_parts.append("availability_updated_at = NOW()")

    set_parts.append("updated_at = NOW()")

    db.execute(
        text(f"UPDATE caretaker_profiles SET {', '.join(set_parts)} WHERE user_id = :cid"),
        params,
    )
    db.commit()

    summary["effective_verification_status"] = desired
    return {
        "status": desired,
        "storage_status": storage_status,
        "summary": summary,
    }

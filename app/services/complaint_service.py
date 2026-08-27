"""
WeCare — Complaint Service

Complete implementation of Complaint domain business logic mirroring Route: - api/v1/complaint/create_complaint
- api/v1/complaint/my_complaints
- api/v1/complaint/view_proof
- api/v1/complaint/admin_list
- api/v1/complaint/admin_view
- api/v1/complaint/admin_update_status
- helpers/admin_complaints
"""

import math
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.audit_service import audit_log
from app.services.notification_service import notify_complaint_updated
from app.services.url_service import public_file_path, public_file_url


def _get_user_id(user: Any) -> int:
    """Extracts integer user ID from dict or User model."""
    if isinstance(user, dict):
        return int(user["id"])
    return int(user.id)


def _format_dt(val: Any) -> Optional[str]:
    """Formats datetime values to standard string representation."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def _format_date(val: Any) -> Optional[str]:
    """Formats date values to standard string."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    return str(val)


def _admin_complaint_text(value: Any) -> Optional[str]:
    """admin_complaint_text()"""
    if value is None:
        return None
    val_str = str(value).strip()
    return val_str if val_str != "" else None


def _admin_complaint_type(row: Dict[str, Any]) -> str:
    """admin_complaint_type()"""
    candidate = _admin_complaint_text(row.get("complaint_type")) or _admin_complaint_text(row.get("type"))
    if candidate is None:
        return "general"
    cand_clean = re.sub(r"[^a-z0-9]+", "_", candidate.lower()).strip("_")
    return cand_clean if cand_clean != "" else "general"


def _admin_complaint_actor_name(row: Dict[str, Any], prefix: str) -> Optional[str]:
    """admin_complaint_actor_name()"""
    return (
        _admin_complaint_text(row.get(f"{prefix}_username"))
        or _admin_complaint_text(row.get(f"{prefix}_email"))
        or _admin_complaint_text(row.get(f"{prefix}_phone"))
    )


def _admin_complaint_payout_impact(row: Dict[str, Any]) -> Tuple[str, str]:
    """admin_complaint_payout_impact()"""
    complaint_status = str(row.get("status") or "")
    payout_status = _admin_complaint_text(row.get("payout_status"))

    if complaint_status in ("resolved", "rejected"):
        return (
            "released",
            "Resolved. Payout hold released."
            if complaint_status == "resolved"
            else "Rejected. Complaint review no longer blocks payout.",
        )

    if payout_status == "paid":
        return ("paid", "Payout was already paid before complaint review.")

    if payout_status == "disputed":
        return ("held", "Complaint is open. Booking payout is under review.")

    if payout_status == "hold":
        return ("held", "Complaint is open. Payout remains on hold.")

    return ("review", "Complaint requires admin review before payout release.")


def _admin_complaint_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """Route: admin_complaint_payload() — helpers/admin_complaints L32-77"""
    fam_uid = int(row.get("family_user_id") or row.get("booking_family_user_id") or 0)
    car_uid_raw = row.get("caretaker_user_id") if row.get("caretaker_user_id") is not None else row.get("booking_caretaker_user_id")
    caretaker_user_id = int(car_uid_raw) if car_uid_raw is not None else None

    patient_name = _admin_complaint_text(row.get("patient_name")) or _admin_complaint_actor_name(row, "family")
    caretaker_name = _admin_complaint_text(row.get("caretaker_profile_name")) or _admin_complaint_actor_name(row, "caretaker")
    comp_type = _admin_complaint_type(row)
    hold_status, impact_message = _admin_complaint_payout_impact(row)

    proof_path_raw = row.get("proof_file")
    proof_public_path = public_file_path(proof_path_raw)
    has_proof = proof_public_path is not None
    proof_url = public_file_url(proof_path_raw)

    comp_id = int(row.get("id") or 0)
    result = dict(row)
    result.update({
        "id": comp_id,
        "booking_id": int(row.get("booking_id") or 0),
        "type": comp_type,
        "complaint_type": comp_type,
        "filed_by_user_id": fam_uid if fam_uid > 0 else None,
        "filed_by_name": patient_name,
        "filed_by_role": "family",
        "against_user_id": caretaker_user_id,
        "against_name": caretaker_name,
        "against_role": "caretaker" if caretaker_user_id else None,
        "family_user_id": fam_uid if fam_uid > 0 else None,
        "patient_name": patient_name,
        "caretaker_user_id": caretaker_user_id,
        "caretaker_name": caretaker_name,
        "payout_hold_status": hold_status,
        "payout_impact_message": impact_message,
        "has_proof": has_proof,
        "proof_path": proof_public_path,
        "proof_file_url": proof_url,
        "proof_url": proof_url,
        "file_url": proof_url,
        "attachment_url": proof_url,
        "proof_view_url": f"/complaint/view_proof?id={comp_id}" if has_proof else None,
        "booking_date": _format_date(row.get("booking_date")),
        "created_at": _format_dt(row.get("created_at")),
        "updated_at": _format_dt(row.get("updated_at")),
        "resolved_at": _format_dt(row.get("resolved_at")),
    })
    return result


# ── Create Complaint ─────────────────────────────────────────────────────────

def create_complaint(
    db: Session,
    family_user: Any,
    booking_id: Optional[Union[int, str]],
    subject: Optional[str],
    description: Optional[str],
    proof_file: Optional[UploadFile] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/complaint/create_complaint
    Submits a complaint for a completed booking within the 24-hour window.
    """
    user_id = _get_user_id(family_user)

    subj_str = str(subject).strip() if subject is not None else ""
    desc_str = str(description).strip() if description is not None else ""

    if booking_id is None or str(booking_id).strip() == "" or not subj_str or not desc_str:
        raise APIException("Booking id, subject and description are required", status_code=400)

    try:
        booking_id_int = int(booking_id)
    except (ValueError, TypeError):
        raise APIException("Booking id, subject and description are required", status_code=400)

    # Check completed booking ownership
    b_row = db.execute(
        text(
            "SELECT b.id, b.family_user_id, b.caretaker_user_id, b.status, b.updated_at, "
            "       vt.check_out_time "
            "FROM bookings b "
            "LEFT JOIN visit_tracking vt ON vt.booking_id = b.id "
            "WHERE b.id = :bid AND b.family_user_id = :uid AND b.status = 'completed' "
            "ORDER BY vt.id DESC "
            "LIMIT 1"
        ),
        {"bid": booking_id_int, "uid": user_id},
    ).fetchone()

    if not b_row:
        raise APIException("Completed booking not found", status_code=404)

    # 24-hour complaint window check
    completed_at = b_row.check_out_time or b_row.updated_at
    if not completed_at:
        raise APIException("Complaint window expired", status_code=400)

    if isinstance(completed_at, datetime):
        completed_ts = completed_at.timestamp()
    else:
        try:
            completed_ts = datetime.strptime(str(completed_at), "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            completed_ts = 0

    if completed_ts < time.time() - 86400:
        raise APIException("Complaint window expired", status_code=400)

    # Handle proof file upload
    stored_proof_rel: Optional[str] = None
    if proof_file and hasattr(proof_file, "filename") and proof_file.filename:
        if hasattr(proof_file, "file") and hasattr(proof_file.file, "read"):
            content = proof_file.file.read()
        elif hasattr(proof_file, "read"):
            content = proof_file.read()
        else:
            content = b""

        if len(content) > 5 * 1024 * 1024:
            raise APIException("Proof file is too large", status_code=400)

        # Validate MIME / extension
        allowed_mimes = {
            "application/pdf": "pdf",
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        content_type = proof_file.content_type or ""
        ext = allowed_mimes.get(content_type)
        if not ext:
            fn_ext = proof_file.filename.split(".")[-1].lower() if "." in proof_file.filename else ""
            if fn_ext in ("pdf", "jpg", "jpeg", "png", "webp"):
                ext = "jpg" if fn_ext == "jpeg" else fn_ext
            else:
                raise APIException("Invalid proof file type", status_code=400)

        # Upload directory
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        upload_dir = os.path.join(base_dir, "uploads", "complaints")
        os.makedirs(upload_dir, exist_ok=True)

        orig_base = os.path.splitext(proof_file.filename)[0]
        safe_base = re.sub(r"[^A-Za-z0-9_.-]", "_", orig_base)
        rand_token = secrets.token_hex(12)
        saved_filename = f"{rand_token}_{safe_base}.{ext}"
        full_dest = os.path.join(upload_dir, saved_filename)

        with open(full_dest, "wb") as f:
            f.write(content)

        stored_proof_rel = f"uploads/complaints/{saved_filename}"

    db.execute(
        text(
            "INSERT INTO complaints "
            "(booking_id, family_user_id, caretaker_user_id, subject, description, proof_file) "
            "VALUES (:bid, :fid, :cid, :subj, :desc, :proof)"
        ),
        {
            "bid": booking_id_int,
            "fid": user_id,
            "cid": b_row.caretaker_user_id,
            "subj": subj_str,
            "desc": desc_str,
            "proof": stored_proof_rel,
        },
    )
    complaint_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())
    db.commit()

    return {
        "complaint_id": complaint_id,
        "proof_path": public_file_path(stored_proof_rel),
        "proof_url": public_file_url(stored_proof_rel),
    }


# ── Family Complaints List ───────────────────────────────────────────────────

def get_family_complaints(
    db: Session,
    family_user: Any,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/complaint/my_complaints
    Retrieves complaints submitted by the authenticated family user.
    """
    user_id = _get_user_id(family_user)
    page = max(1, int(page))
    limit = min(100, max(1, int(limit)))
    offset = (page - 1) * limit

    status_str = str(status).strip() if status is not None else ""
    params: Dict[str, Any] = {"uid": user_id, "limit": limit, "offset": offset}
    status_sql = ""

    if status_str != "" and status_str != "all":
        if status_str not in ("open", "in_review", "resolved", "rejected"):
            raise APIException(
                "Validation failed",
                status_code=400,
                errors={"status": ["Invalid complaint status"]},
            )
        status_sql = " AND c.status = :status_filter"
        params["status_filter"] = status_str

    count_query = f"SELECT COUNT(*) AS total FROM complaints c WHERE c.family_user_id = :uid {status_sql}"
    count_row = db.execute(text(count_query), params).fetchone()
    total = int(count_row.total) if count_row else 0

    query = f"""
        SELECT c.id, c.booking_id, c.family_user_id, c.caretaker_user_id, c.subject,
               c.description, c.proof_file, c.status, c.admin_note, c.resolved_by,
               c.resolved_at, c.created_at, c.updated_at, b.service_type, b.booking_date
        FROM complaints c
        INNER JOIN bookings b ON b.id = c.booking_id
        WHERE c.family_user_id = :uid {status_sql}
        ORDER BY c.id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(query), params).fetchall()

    items = []
    for r in rows:
        proof_path_val = public_file_path(r.proof_file)
        proof_url_val = public_file_url(r.proof_file)
        items.append({
            "id": int(r.id),
            "booking_id": int(r.booking_id),
            "family_user_id": int(r.family_user_id),
            "caretaker_user_id": int(r.caretaker_user_id) if r.caretaker_user_id is not None else None,
            "subject": r.subject,
            "description": r.description,
            "proof_file": r.proof_file,
            "status": str(r.status.value if hasattr(r.status, "value") else r.status),
            "admin_note": r.admin_note,
            "resolved_by": int(r.resolved_by) if r.resolved_by is not None else None,
            "resolved_at": _format_dt(r.resolved_at),
            "created_at": _format_dt(r.created_at),
            "updated_at": _format_dt(r.updated_at),
            "service_type": r.service_type,
            "booking_date": _format_date(r.booking_date),
            "proof_path": proof_path_val,
            "proof_url": proof_url_val,
            "file_url": proof_url_val,
        })

    total_pages = math.ceil(total / limit) if limit > 0 else 1

    return {
        "items": items,
        "complaints": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
        },
    }


# ── Admin Complaints ─────────────────────────────────────────────────────────

def _admin_complaint_select_sql() -> str:
    """Route: admin_complaint_select_sql() — helpers/admin_complaints L5-25"""
    return """
        SELECT c.id, c.booking_id, c.family_user_id, c.caretaker_user_id, c.subject,
               c.description, c.proof_file, c.status, c.admin_note, c.resolved_by,
               c.resolved_at, c.created_at, c.updated_at,
               b.service_type, b.booking_date, b.payout_status, b.payout_hold_until,
               b.family_user_id AS booking_family_user_id,
               b.caretaker_user_id AS booking_caretaker_user_id,
               p.patient_name,
               fu.username AS family_username, fu.email AS family_email, fu.phone_number AS family_phone,
               cu.username AS caretaker_username, cu.email AS caretaker_email, cu.phone_number AS caretaker_phone,
               cp.full_name AS caretaker_profile_name
        FROM complaints c
        INNER JOIN bookings b ON b.id = c.booking_id
        LEFT JOIN patient_details p ON p.id = b.patient_id
        LEFT JOIN users fu ON fu.id = COALESCE(c.family_user_id, b.family_user_id)
        LEFT JOIN users cu ON cu.id = COALESCE(c.caretaker_user_id, b.caretaker_user_id)
        LEFT JOIN caretaker_profiles cp ON cp.user_id = COALESCE(c.caretaker_user_id, b.caretaker_user_id)
    """


def get_admin_complaints_list(
    db: Session,
    admin_user: Any,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/complaint/admin_list
    Admin listing of complaints with rich payload formatting and status filtering.
    """
    page = max(1, int(page))
    limit = min(100, max(1, int(limit)))
    offset = (page - 1) * limit

    status_str = str(status).strip() if status is not None else ""
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    where_sql = ""

    if status_str != "" and status_str != "all":
        if status_str not in ("open", "in_review", "resolved", "rejected"):
            raise APIException("Invalid complaint status", status_code=400)
        where_sql = "WHERE c.status = :status_filter"
        params["status_filter"] = status_str

    count_query = f"SELECT COUNT(*) AS total FROM complaints c {where_sql}"
    count_row = db.execute(text(count_query), params).fetchone()
    total = int(count_row.total) if count_row else 0

    query = f"""
        {_admin_complaint_select_sql()}
        {where_sql}
        ORDER BY c.id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(query), params).mappings().all()
    items = [_admin_complaint_payload(dict(r)) for r in rows]

    total_pages = math.ceil(total / limit) if limit > 0 else 1

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "items": items,
    }


def get_admin_complaint_detail(
    db: Session,
    admin_user: Any,
    complaint_id: Optional[Union[int, str]],
) -> Dict[str, Any]:
    """
    Route: api/v1/complaint/admin_view
    Admin view single complaint detail.
    """
    if complaint_id is None or str(complaint_id).strip() == "":
        raise APIException("Complaint id is required", status_code=400)

    try:
        cid = int(complaint_id)
    except (ValueError, TypeError):
        raise APIException("Complaint id is required", status_code=400)

    query = f"{_admin_complaint_select_sql()} WHERE c.id = :cid"
    row = db.execute(text(query), {"cid": cid}).mappings().first()

    if not row:
        raise APIException("Complaint not found", status_code=404)

    return _admin_complaint_payload(dict(row))


def admin_update_complaint_status(
    db: Session,
    admin_user: Any,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/complaint/admin_update_status
    Updates complaint status, sets resolved_by / resolved_at, writes audit log, and notifies family.
    """
    admin_id = _get_user_id(admin_user)

    cid_raw = data.get("id") or data.get("complaint_id")
    status_str = str(data.get("status", "")).strip()
    admin_note = str(data.get("admin_note", "")).strip()

    if cid_raw is None or str(cid_raw).strip() == "" or not status_str or status_str not in ("open", "in_review", "resolved", "rejected"):
        raise APIException("Valid complaint id and status are required", status_code=400)

    try:
        cid = int(cid_raw)
    except (ValueError, TypeError):
        raise APIException("Valid complaint id and status are required", status_code=400)

    old_row = db.execute(
        text(
            "SELECT id, booking_id, family_user_id, caretaker_user_id, subject, description, "
            "       proof_file, status, admin_note, resolved_by, resolved_at, created_at, updated_at "
            "FROM complaints "
            "WHERE id = :cid"
        ),
        {"cid": cid},
    ).fetchone()

    if not old_row:
        raise APIException("Complaint not found", status_code=404)

    old_dict = {
        "id": int(old_row.id),
        "booking_id": int(old_row.booking_id),
        "family_user_id": int(old_row.family_user_id),
        "caretaker_user_id": int(old_row.caretaker_user_id) if old_row.caretaker_user_id is not None else None,
        "subject": old_row.subject,
        "description": old_row.description,
        "proof_file": old_row.proof_file,
        "status": str(old_row.status.value if hasattr(old_row.status, "value") else old_row.status),
        "admin_note": old_row.admin_note,
        "resolved_by": int(old_row.resolved_by) if old_row.resolved_by is not None else None,
        "resolved_at": _format_dt(old_row.resolved_at),
    }

    resolved_by = admin_id if status_str in ("resolved", "rejected") else None
    resolved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if status_str in ("resolved", "rejected") else None

    db.execute(
        text(
            "UPDATE complaints "
            "SET status = :status, "
            "    admin_note = :admin_note, "
            "    resolved_by = :resolved_by, "
            "    resolved_at = :resolved_at, "
            "    updated_at = NOW() "
            "WHERE id = :cid"
        ),
        {
            "status": status_str,
            "admin_note": admin_note if admin_note != "" else None,
            "resolved_by": resolved_by,
            "resolved_at": resolved_at,
            "cid": cid,
        },
    )

    audit_log(
        db=db,
        admin_user_id=admin_id,
        action="update_complaint_status",
        entity_type="complaint",
        entity_id=cid,
        old_values=old_dict,
        new_values={
            "status": status_str,
            "admin_note": admin_note,
        },
    )

    notify_complaint_updated(db, cid)
    db.commit()

    return {
        "complaint_id": cid,
        "proof_path": public_file_path(old_row.proof_file),
        "proof_url": public_file_url(old_row.proof_file),
    }


def get_complaint_proof_file(
    db: Session,
    admin_user: Any,
    complaint_id: Optional[Union[int, str]],
) -> Tuple[str, str, str]:
    """
    Route: api/v1/complaint/view_proof
    Returns (absolute_file_path, filename, media_type) for streaming the proof file.
    """
    if complaint_id is None or str(complaint_id).strip() == "":
        raise APIException(
            "Complaint id is required",
            status_code=400,
            errors={"id": ["Complaint id must be a positive integer"]},
        )

    try:
        cid = int(complaint_id)
        if cid < 1:
            raise APIException(
                "Complaint id is required",
                status_code=400,
                errors={"id": ["Complaint id must be a positive integer"]},
            )
    except (ValueError, TypeError):
        raise APIException(
            "Complaint id is required",
            status_code=400,
            errors={"id": ["Complaint id must be a positive integer"]},
        )

    row = db.execute(
        text("SELECT id, proof_file FROM complaints WHERE id = :cid LIMIT 1"),
        {"cid": cid},
    ).fetchone()

    if not row:
        raise APIException("Complaint not found", status_code=404)

    clean_path = public_file_path(row.proof_file)
    if not clean_path or not clean_path.startswith("/uploads/complaints/"):
        raise APIException("Proof file is unavailable", status_code=404)

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    proof_root = os.path.realpath(os.path.join(base_dir, "uploads", "complaints"))
    rel_path = clean_path.lstrip("/").replace("/", os.sep)
    file_path = os.path.realpath(os.path.join(base_dir, rel_path))

    if not file_path.startswith(proof_root + os.sep) or not os.path.isfile(file_path) or os.path.getsize(file_path) <= 0:
        raise APIException("Proof file is unavailable", status_code=404)

    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
    allowed_mimes = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    if ext not in allowed_mimes:
        raise APIException("Proof file type is not supported", status_code=404)

    media_type = allowed_mimes[ext]
    filename = os.path.basename(file_path)
    return file_path, filename, media_type

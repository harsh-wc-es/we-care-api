"""
WeCare — Complaint API Router (Part 9)
Provides canonical and legacy  routes for complaint submission, retrieval, review, and proof viewing.
"""

from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_admin, require_family
from app.schemas.complaint import AdminUpdateComplaintStatusRequest, CreateComplaintRequest
from app.services import complaint_service

router = APIRouter(tags=["Complaints"])


# ── Create Complaint ─────────────────────────────────────────────────────────

async def _handle_create_complaint(
    request: Request,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:

    content_type = request.headers.get("content-type", "")

    booking_id: Optional[Union[int, str]] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    proof_file: Optional[UploadFile] = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        booking_id = form.get("booking_id")  # type: ignore[assignment]
        subject = form.get("subject")  # type: ignore[assignment]
        description = form.get("description")  # type: ignore[assignment]
        file_field = form.get("proof_file")
        if file_field is not None and hasattr(file_field, "filename") and file_field.filename:
            proof_file = file_field  # type: ignore[assignment]
    else:
        try:
            body = await request.json()
            booking_id = body.get("booking_id")
            subject = body.get("subject")
            description = body.get("description")
        except Exception:
            pass

    data = complaint_service.create_complaint(
        db=db,
        family_user=current_user,
        booking_id=booking_id,
        subject=subject,
        description=description,
        proof_file=proof_file,
    )
    return success_response(data=data, message="Complaint created", status_code=201)


@router.post("/create_complaint")
async def create_complaint_canonical(
    request: Request,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_create_complaint(request, current_user, db)
def _handle_my_complaints(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = complaint_service.get_family_complaints(
        db=db,
        family_user=current_user,
        status=status,
        page=page,
        limit=limit,
    )
    return success_response(data=data, message="Complaints retrieved")


@router.get("/my_complaints")
def get_my_complaints_canonical(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_my_complaints(status, page, limit, current_user, db)
def _handle_view_proof(
    id: Optional[int] = Query(None),
    complaint_id: Optional[int] = Query(None),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Any:
    target_id = id if id is not None else complaint_id
    file_path, filename, media_type = complaint_service.get_complaint_proof_file(
        db=db,
        admin_user=current_user,
        complaint_id=target_id,
    )
    headers = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=300",
    }
    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers=headers,
    )


@router.get("/view_proof")
def view_proof_canonical(
    id: Optional[int] = Query(None),
    complaint_id: Optional[int] = Query(None),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Any:
    return _handle_view_proof(id, complaint_id, current_user, db)
def _handle_admin_list(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = complaint_service.get_admin_complaints_list(
        db=db,
        admin_user=current_user,
        status=status,
        page=page,
        limit=limit,
    )
    return success_response(data=data, message="Complaints retrieved")


@router.get("/admin_list")
def admin_list_canonical(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_admin_list(status, page, limit, current_user, db)
def _handle_admin_view(
    id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = complaint_service.get_admin_complaint_detail(
        db=db,
        admin_user=current_user,
        complaint_id=id,
    )
    return success_response(data=data, message="Complaint retrieved")


@router.get("/admin_view")
def admin_view_canonical(
    id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_admin_view(id, current_user, db)
async def _handle_admin_update_status(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = complaint_service.admin_update_complaint_status(
        db=db,
        admin_user=current_user,
        data=body,
    )
    return success_response(data=data, message="Complaint status updated")


@router.post("/admin_update_status")
async def admin_update_status_canonical(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_admin_update_status(request, current_user, db)

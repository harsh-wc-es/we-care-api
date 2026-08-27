"""
WeCare — Visit Domain Router

Registers all 9 Visit Execution endpoints with dual canonical and legacy  aliases.
"""

from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_user,
    require_caretaker,
)
from app.schemas.visit import (
    AddNoteRequest,
    CheckInRequest,
    CheckOutRequest,
    UpdateTaskStatusRequest,
    VerifyOtpRequest,
)
from app.services.visit_service import (
    add_visit_note,
    check_in_visit,
    check_out_visit,
    get_active_visit,
    get_completed_summary,
    get_full_report,
    get_visit_detail,
    update_visit_task_status,
    verify_visit_start_otp,
)

router = APIRouter(tags=["Visit"])


# ─────────────────────────────────────────────────────────────
# 1. view_visit
# ─────────────────────────────────────────────────────────────

@router.get("/view_visit")
def view_visit_endpoint(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/view_visit
    Accessible by caretaker, family, or admin with role-scoped authorization.
    """
    data = get_visit_detail(db, booking_id, current_user)
    return success_response(data=data, message="Visit detail retrieved")


# ─────────────────────────────────────────────────────────────
# 2. verify_start_otp
# ─────────────────────────────────────────────────────────────

@router.post("/verify_start_otp")
def verify_start_otp_endpoint(
    req: VerifyOtpRequest,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/verify_start_otp
    Caretaker verifies family-provided visit start OTP.
    """
    data = verify_visit_start_otp(
        db=db,
        booking_id=req.booking_id,
        otp=req.otp,
        caretaker_user_id=int(current_user["id"]),
    )
    return success_response(data=data, message="Visit OTP verified successfully")


# ─────────────────────────────────────────────────────────────
# 3. check_in
# ─────────────────────────────────────────────────────────────

@router.post("/check_in", status_code=201)
def check_in_endpoint(
    req: CheckInRequest,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/check_in
    Caretaker check-in with verified OTP prerequisite.
    """
    data = check_in_visit(
        db=db,
        booking_id=req.booking_id,
        caretaker_user_id=int(current_user["id"]),
        latitude=req.latitude,
        longitude=req.longitude,
        notes=req.notes,
    )
    return success_response(data=data, message="Check-in successful", status_code=201)


# ─────────────────────────────────────────────────────────────
# 4. active_visit
# ─────────────────────────────────────────────────────────────

@router.get("/active_visit")
def active_visit_endpoint(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/active_visit
    Returns active in-progress visit payload for caretaker.
    """
    data = get_active_visit(
        db=db,
        booking_id=booking_id,
        caretaker_user_id=int(current_user["id"]),
    )
    return success_response(data=data, message="Active visit fetched successfully")


# ─────────────────────────────────────────────────────────────
# 5. add_note
# ─────────────────────────────────────────────────────────────

@router.post("/add_note", status_code=201)
def add_note_endpoint(
    req: AddNoteRequest,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/add_note
    Adds an immutable care note during active visit.
    """
    data = add_visit_note(
        db=db,
        booking_id=req.booking_id,
        note=req.note,
        caretaker_user_id=int(current_user["id"]),
    )
    return success_response(data=data, message="Note added successfully", status_code=201)


# ─────────────────────────────────────────────────────────────
# 6. update_task_status
# ─────────────────────────────────────────────────────────────

@router.post("/update_task_status")
def update_task_status_endpoint(
    req: UpdateTaskStatusRequest,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/update_task_status
    Updates checklist task status during active visit.
    """
    data = update_visit_task_status(
        db=db,
        booking_id=req.booking_id,
        task_id=req.task_id,
        status=req.status,
        caretaker_user_id=int(current_user["id"]),
    )
    return success_response(data=data, message="Task updated successfully")


# ─────────────────────────────────────────────────────────────
# 7. check_out
# ─────────────────────────────────────────────────────────────

@router.post("/check_out")
def check_out_endpoint(
    req: CheckOutRequest,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/check_out
    Completes visit, awards care points, and restores availability.
    """
    data = check_out_visit(
        db=db,
        booking_id=req.booking_id,
        caretaker_user_id=int(current_user["id"]),
        latitude=req.latitude,
        longitude=req.longitude,
        notes=req.notes,
    )
    return success_response(data=data, message="Check-out successful")


# ─────────────────────────────────────────────────────────────
# 8. completed_summary
# ─────────────────────────────────────────────────────────────

@router.get("/completed_summary")
def completed_summary_endpoint(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/completed_summary
    Returns completed visit summary metrics for caretaker popup.
    """
    data = get_completed_summary(
        db=db,
        booking_id=booking_id,
        caretaker_user_id=int(current_user["id"]),
    )
    return success_response(data=data, message="Visit summary fetched successfully")


# ─────────────────────────────────────────────────────────────
# 9. full_report
# ─────────────────────────────────────────────────────────────

@router.get("/full_report")
def full_report_endpoint(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/visit/full_report
    Returns detailed report for completed visit with customer financials masked.
    """
    data = get_full_report(
        db=db,
        booking_id=booking_id,
        caretaker_user_id=int(current_user["id"]),
    )
    return success_response(data=data, message="Visit report fetched successfully")

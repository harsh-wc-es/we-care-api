"""
WeCare — Checklist API Router (Part 10)
Provides canonical and legacy  routes for booking checklist tasks.
"""

from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_caretaker, require_family
from app.schemas.checklist import CreateTaskRequest, MarkDoneRequest
from app.services import checklist_service

router = APIRouter(tags=["Checklist"])


# ── Booking Tasks ───────────────────────────────────────────────────────────

def _handle_booking_tasks(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = checklist_service.get_booking_tasks(
        db=db,
        current_user=current_user,
        booking_id=booking_id,
    )
    return success_response(data=data, message="Checklist tasks retrieved")


@router.get("/booking_tasks")
def booking_tasks_canonical(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_booking_tasks(booking_id, current_user, db)
async def _handle_create_task(
    request: Request,
    payload: Optional[CreateTaskRequest] = None,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    booking_id = body.get("booking_id") if "booking_id" in body else (payload.booking_id if payload else None)
    title = body.get("title") if "title" in body else (payload.title if payload else None)
    description = body.get("description") if "description" in body else (payload.description if payload else None)

    data = checklist_service.create_task(
        db=db,
        family_user=current_user,
        booking_id=booking_id,
        title=title,
        description=description,
    )
    return success_response(data=data, message="Checklist task created", status_code=201)


@router.post("/create_task")
async def create_task_canonical(
    request: Request,
    payload: Optional[CreateTaskRequest] = None,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_create_task(request, payload, current_user, db)
async def _handle_mark_done(
    request: Request,
    payload: Optional[MarkDoneRequest] = None,
    current_user: Any = Depends(require_caretaker),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    task_id = body.get("task_id") if "task_id" in body else (payload.task_id if payload else None)
    status = body.get("status", "completed") if "status" in body else (payload.status if payload else "completed")

    data = checklist_service.mark_done(
        db=db,
        caretaker_user=current_user,
        task_id=task_id,
        status=status,
    )
    return success_response(data=data, message="Checklist task updated")


@router.post("/mark_done")
async def mark_done_canonical(
    request: Request,
    payload: Optional[MarkDoneRequest] = None,
    current_user: Any = Depends(require_caretaker),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_mark_done(request, payload, current_user, db)

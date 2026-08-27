"""
WeCare — Replacement Tickets API Router (Part 9)
Provides canonical and legacy  routes for replacement ticket submission and admin management.
"""

from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_admin, require_caretaker
from app.services import replacement_service

router = APIRouter(tags=["Replacement Tickets"])


# ── Create Ticket ─────────────────────────────────────────────────────────────

async def _handle_create_ticket(
    request: Request,
    current_user: Any = Depends(require_caretaker),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}

    data = replacement_service.create_replacement_ticket(
        db=db,
        caretaker_user=current_user,
        booking_id=body.get("booking_id"),
        reason=body.get("reason"),
        complaint_id=body.get("complaint_id"),
    )
    return success_response(data=data, message="Replacement ticket created", status_code=201)


@router.post("/create_ticket")
async def create_ticket_canonical(
    request: Request,
    current_user: Any = Depends(require_caretaker),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_create_ticket(request, current_user, db)
def _handle_admin_list(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = replacement_service.get_admin_replacement_tickets_list(
        db=db,
        admin_user=current_user,
        status=status,
        page=page,
        limit=limit,
    )
    return success_response(data=data, message="Replacement tickets retrieved")


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
    data = replacement_service.get_admin_replacement_ticket_detail(
        db=db,
        admin_user=current_user,
        ticket_id=id,
    )
    return success_response(data=data, message="Replacement ticket retrieved")


@router.get("/admin_view")
def admin_view_canonical(
    id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_admin_view(id, current_user, db)
async def _handle_admin_assign(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = replacement_service.admin_assign_replacement_caretaker(
        db=db,
        admin_user=current_user,
        data=body,
    )
    return success_response(data=data, message="Replacement caretaker assigned")


@router.post("/admin_assign")
async def admin_assign_canonical(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_admin_assign(request, current_user, db)
async def _handle_admin_update_status(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = replacement_service.admin_update_replacement_ticket_status(
        db=db,
        admin_user=current_user,
        data=body,
    )
    return success_response(data=data, message="Replacement ticket updated")


@router.post("/admin_update_status")
async def admin_update_status_canonical(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_admin_update_status(request, current_user, db)
async def _handle_admin_resolve(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = replacement_service.admin_resolve_replacement_ticket(
        db=db,
        admin_user=current_user,
        data=body,
    )
    return success_response(data=data, message="Replacement ticket resolved")


@router.post("/admin_resolve")
async def admin_resolve_canonical(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_admin_resolve(request, current_user, db)
async def _handle_admin_cancel(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = replacement_service.admin_cancel_replacement_ticket(
        db=db,
        admin_user=current_user,
        data=body,
    )
    return success_response(data=data, message="Replacement ticket cancelled")


@router.post("/admin_cancel")
async def admin_cancel_canonical(
    request: Request,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_admin_cancel(request, current_user, db)
async def _handle_admin_delete(
    request: Request,
    id: Optional[Union[int, str]] = None,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    target_id = id or request.query_params.get("id")
    if target_id is None:
        try:
            body = await request.json()
            if isinstance(body, dict):
                target_id = body.get("id")
        except Exception:
            pass
    if target_id is None:
        try:
            form = await request.form()
            target_id = form.get("id")
        except Exception:
            pass

    replacement_service.admin_delete_replacement_ticket(
        db=db,
        admin_user=current_user,
        ticket_id=target_id,
    )
    return success_response(data=None, message="Replacement ticket deleted")


@router.post("/admin_delete")
async def admin_delete_post_canonical(
    request: Request,
    id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_admin_delete(request, id, current_user, db)
@router.delete("/admin_delete")
async def admin_delete_canonical(
    request: Request,
    id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_admin_delete(request, id, current_user, db)

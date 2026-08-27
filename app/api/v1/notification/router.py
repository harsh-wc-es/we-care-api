"""
WeCare — Notification API Router (Part 10)
Provides canonical and legacy  routes for user notifications and device tokens.
"""

from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.schemas.notification import (
    CreateNotificationRequest,
    MarkReadRequest,
    RegisterDeviceRequest,
    RemoveDeviceRequest,
)
from app.services import notification_service

router = APIRouter(tags=["Notifications"])


# ── My Notifications ─────────────────────────────────────────────────────────

def _handle_my_notifications(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    unread_only: Optional[str] = Query("false"),
    type: Optional[str] = Query(None),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = notification_service.get_my_notifications(
        db=db,
        current_user=current_user,
        page=page,
        limit=limit,
        unread_only=unread_only,
        notification_type=type,
    )
    return success_response(data=data, message="Notifications retrieved successfully")


@router.get("/my_notifications")
def get_my_notifications_canonical(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    unread_only: Optional[str] = Query("false"),
    type: Optional[str] = Query(None),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_my_notifications(page, limit, unread_only, type, current_user, db)
async def _handle_mark_read(
    request: Request,
    payload: Optional[MarkReadRequest] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    notification_id = body.get("notification_id")
    if notification_id is None and payload is not None:
        notification_id = payload.notification_id

    data = notification_service.mark_notification_read(
        db=db,
        current_user=current_user,
        notification_id=notification_id,
    )
    return success_response(data=data, message="Notification marked as read")


@router.post("/mark_read")
async def mark_read_canonical(
    request: Request,
    payload: Optional[MarkReadRequest] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_mark_read(request, payload, current_user, db)
def _handle_mark_all_read(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = notification_service.mark_all_notifications_read(
        db=db,
        current_user=current_user,
    )
    return success_response(data=data, message="All notifications marked as read")


@router.post("/mark_all_read")
def mark_all_read_canonical(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_mark_all_read(current_user, db)
async def _handle_create_notification(
    request: Request,
    payload: Optional[CreateNotificationRequest] = None,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    user_id = body.get("user_id") if "user_id" in body else (payload.user_id if payload else None)
    title = body.get("title") if "title" in body else (payload.title if payload else None)
    message = body.get("message") if "message" in body else (payload.message if payload else None)

    data = notification_service.admin_create_notification(
        db=db,
        admin_user=current_user,
        user_id=user_id,
        title=title,
        message=message,
    )
    return success_response(data=data, message="Notification created successfully", status_code=201)


@router.post("/create_notification")
async def create_notification_canonical(
    request: Request,
    payload: Optional[CreateNotificationRequest] = None,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_create_notification(request, payload, current_user, db)
async def _handle_register_device(
    request: Request,
    payload: Optional[RegisterDeviceRequest] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    device_token = body.get("device_token") if "device_token" in body else (payload.device_token if payload else None)
    platform = body.get("platform") if "platform" in body else (payload.platform if payload else None)
    app_type = body.get("app_type") if "app_type" in body else (payload.app_type if payload else None)

    data = notification_service.register_device_token(
        db=db,
        current_user=current_user,
        device_token=device_token,
        platform=platform,
        app_type=app_type,
    )
    return success_response(data=data, message="Device registered successfully")


@router.post("/register_device")
async def register_device_canonical(
    request: Request,
    payload: Optional[RegisterDeviceRequest] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_register_device(request, payload, current_user, db)
async def _handle_remove_device(
    request: Request,
    payload: Optional[RemoveDeviceRequest] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    device_token = body.get("device_token") if "device_token" in body else (payload.device_token if payload else None)

    data = notification_service.remove_device_token(
        db=db,
        current_user=current_user,
        device_token=device_token,
    )
    return success_response(data=data, message="Device removed successfully")


@router.post("/remove_device")
async def remove_device_canonical(
    request: Request,
    payload: Optional[RemoveDeviceRequest] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_remove_device(request, payload, current_user, db)

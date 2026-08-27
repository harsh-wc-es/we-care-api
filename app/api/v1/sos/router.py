"""
WeCare — Emergency SOS Router

Registers all SOS endpoints with dual canonical and legacy  aliases:
1. POST /api/v1/sos/create_sos[]
2. POST /api/v1/sos/create[]
3. GET  /api/v1/sos/my_sos[]
4. POST /api/v1/sos/resolve_sos[]
5. POST /api/v1/sos/update_status[]
6. GET  /api/v1/sos/admin_sos_list[]
7. GET  /api/v1/sos/sos_detail[]
"""

from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import (
    get_current_user,
    require_admin,
    require_caretaker,
)
from app.schemas.sos import (
    CaretakerCreateSosRequest,
    CreateSosRequest,
    ResolveSosRequest,
    UpdateSosStatusRequest,
)
from app.services.sos_service import (
    create_caretaker_sos,
    create_sos_alert,
    get_admin_sos_detail,
    get_admin_sos_list,
    get_user_sos_list,
    resolve_sos_alert,
    update_sos_status,
)

router = APIRouter(tags=["SOS"])


# ─────────────────────────────────────────────────────────────
# 1. create_sos
# ─────────────────────────────────────────────────────────────

@router.post("/create_sos")
def create_sos_endpoint(
    req: CreateSosRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Triggers an SOS alert for Family, Caretaker, or Admin."""
    data = create_sos_alert(
        db=db,
        user=current_user,
        data=req.model_dump(),
    )
    return success_response(
        message="SOS alert created successfully",
        data=data,
        status_code=201,
    )


# ─────────────────────────────────────────────────────────────
# 2. create (caretaker-specific fast trigger)
# ─────────────────────────────────────────────────────────────

@router.post("/create")
def create_caretaker_sos_endpoint(
    req: CaretakerCreateSosRequest,
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
):
    """Caretaker-only fast SOS trigger on accepted/in_progress booking."""
    data = create_caretaker_sos(
        db=db,
        user=current_user,
        data=req.model_dump(),
    )
    return success_response(
        message="SOS alert created successfully",
        data=data,
        status_code=201,
    )


# ─────────────────────────────────────────────────────────────
# 3. my_sos
# ─────────────────────────────────────────────────────────────

@router.get("/my_sos")
def my_sos_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves paginated SOS alerts created by the current user."""
    data = get_user_sos_list(
        db=db,
        user=current_user,
        page=page,
        limit=limit,
    )
    return success_response(
        message="SOS alerts retrieved successfully",
        data=data,
        status_code=200,
    )


# ─────────────────────────────────────────────────────────────
# 4. resolve_sos
# ─────────────────────────────────────────────────────────────

@router.post("/resolve_sos")
def resolve_sos_endpoint(
    req: ResolveSosRequest,
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin quick resolution of an SOS alert."""
    resolve_sos_alert(
        db=db,
        admin_user=admin_user,
        sos_id=req.sos_id,
    )
    return success_response(
        message="SOS alert resolved successfully",
        data=None,
        status_code=200,
    )


# ─────────────────────────────────────────────────────────────
# 5. update_status
# ─────────────────────────────────────────────────────────────

@router.post("/update_status")
def update_status_endpoint(
    req: UpdateSosStatusRequest,
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin status update ('open' | 'resolved') with audit trail."""
    update_sos_status(
        db=db,
        admin_user=admin_user,
        sos_id=req.sos_id,
        status=req.status,
    )
    return success_response(
        message="SOS status updated",
        data=None,
        status_code=200,
    )


# ─────────────────────────────────────────────────────────────
# 6. admin_sos_list
# ─────────────────────────────────────────────────────────────

@router.get("/admin_sos_list")
def admin_sos_list_endpoint(
    status: str = Query("all"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin list of SOS alerts with status filtering and joined metadata."""
    data = get_admin_sos_list(
        db=db,
        admin_user=admin_user,
        status=status,
        page=page,
        limit=limit,
    )
    return success_response(
        message="SOS alerts retrieved successfully",
        data=data,
        status_code=200,
    )


# ─────────────────────────────────────────────────────────────
# 7. sos_detail
# ─────────────────────────────────────────────────────────────

@router.get("/sos_detail")
def sos_detail_endpoint(
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

"""
WeCare — Dashboard API Router (Part 11)

Endpoints:
  1. GET /api/v1/dashboard/admin_dashboard (+  alias)
  2. GET /api/v1/dashboard/caretaker_dashboard (+  alias)
  3. GET /api/v1/dashboard/family_dashboard (+  alias)
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_admin, require_caretaker, require_family
from app.services.dashboard_service import (
    get_admin_dashboard,
    get_caretaker_dashboard,
    get_family_dashboard,
)

router = APIRouter()


# ============================================================
# 1. Admin Dashboard
# ============================================================


@router.get("/admin_dashboard")
def admin_dashboard_endpoint(
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Route: api/v1/dashboard/admin_dashboard
    Retrieves core metrics, primary/secondary KPIs, live operations, and recent audit activity.
    """
    data = get_admin_dashboard(db=db, admin_user=current_user)
    return {
        "success": True,
        "message": "Admin dashboard retrieved",
        "data": data,
        "errors": None,
    }


# ============================================================
# 2. Caretaker Dashboard
# ============================================================


@router.get("/caretaker_dashboard")
def caretaker_dashboard_endpoint(
    current_user: Dict[str, Any] = Depends(require_caretaker),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Route: api/v1/dashboard/caretaker_dashboard
    Retrieves caretaker profile status, earnings, availability payload, today's/active/upcoming visits.
    Updates caretaker presence timestamp on every request.
    """
    data = get_caretaker_dashboard(db=db, caretaker_user=current_user)
    return {
        "success": True,
        "message": "Caretaker dashboard retrieved",
        "data": data,
        "errors": None,
    }


# ============================================================
# 3. Family Dashboard
# ============================================================


@router.get("/family_dashboard")
def family_dashboard_endpoint(
    current_user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Route: api/v1/dashboard/family_dashboard
    Retrieves family metrics: total patients, total bookings, status counts, and open SOS alerts.
    """
    data = get_family_dashboard(db=db, family_user=current_user)
    return {
        "success": True,
        "message": "Family dashboard retrieved",
        "data": data,
        "errors": None,
    }

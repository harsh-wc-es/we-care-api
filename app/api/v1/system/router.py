"""
WeCare — System API Router (Part 11)

Endpoints:
  1. GET /api/v1/system/db_diagnostics (+  alias)
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.services.system_service import get_db_diagnostics

router = APIRouter()


@router.get("/db_diagnostics")
def db_diagnostics_endpoint(
    current_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Route: api/v1/system/db_diagnostics
    Database and environment diagnostic probes. Accessible only when APP_DEBUG=true.
    """
    data = get_db_diagnostics(db=db)
    return {
        "success": True,
        "message": "Database diagnostics",
        "data": data,
        "errors": None,
    }

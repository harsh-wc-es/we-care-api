"""
WeCare — Refresh Token Route (STEP 11)

POST /api/v1/auth/refresh-token → refresh_token
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response import success_response, error_response
from app.db.session import get_db
from app.schemas.auth import RefreshRequest
from app.services.auth_service import refresh_access_token

router = APIRouter()


@router.post("/refresh-token")
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    """
    Route: refresh_token L1-82

    Accepts refresh token, verifies JWT + DB, issues new access token.
    Does NOT require Bearer auth — only the refresh JWT in body.
    """
    # accepts both field names (refresh_token L14)
    token = (body.refresh or body.refresh_token or "").strip()

    if not token:
        return error_response("Refresh token is required", {
            "refresh": ["Refresh token is required"],
        }, 400)

    result = refresh_access_token(db, token)

    if result is None:
        return error_response("Refresh token is required", status_code=400)

    if "error" in result:
        return error_response(result["error"], status_code=result.get("status", 401))

    return success_response("Token refreshed", result)

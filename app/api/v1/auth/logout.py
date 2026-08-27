"""
WeCare — Logout Route (STEP 12)

POST /api/v1/auth/logout → logout
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response import success_response, error_response
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.schemas.auth import LogoutRequest
from app.services.auth_service import logout_user

router = APIRouter()


@router.post("/logout")
def logout(
    body: LogoutRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Route: logout L1-32

    Blacklists the token pair matching user_id + refresh_token.
    """
    refresh = (body.refresh or "").strip()

    if not refresh:
        return error_response("Refresh token is required", {
            "refresh": ["Refresh token is required"],
        }, 400)

    success = logout_user(db, user["id"], refresh)

    if not success:
        return error_response("Token not found or already logged out", status_code=400)

    return success_response("Logged out successfully")

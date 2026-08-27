"""
WeCare — Review Endpoints Router

Routes:
- POST /api/v1/review/add_review[]
- GET  /api/v1/review/caretaker_reviews[]
"""

from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_family
from app.schemas.review import AddReviewRequest
from app.services.review_service import (
    add_booking_review,
    get_caretaker_reviews,
)

router = APIRouter()


@router.post("/add_review", status_code=201)
def add_review_endpoint(
    req: AddReviewRequest,
    current_user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/review/add_review
    Submits a review for a completed booking.
    """
    data = add_booking_review(
        db=db,
        family_user=current_user,
        data=req.model_dump(exclude_unset=True),
    )
    return success_response("Review submitted successfully", data, status_code=201)


@router.get("/caretaker_reviews")
def caretaker_reviews_endpoint(
    caretaker_user_id: Optional[Union[int, str]] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/review/caretaker_reviews
    Retrieves reviews for a caretaker.
    """
    data = get_caretaker_reviews(
        db=db,
        user=current_user,
        caretaker_user_id=caretaker_user_id,
        page=page,
        limit=limit,
    )
    return success_response("Reviews retrieved successfully", data)

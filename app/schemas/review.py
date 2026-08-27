"""
WeCare — Review and Caretaker Feedback Schemas (Part 8)
"""

from typing import Optional, Union
from pydantic import BaseModel, Field


class AddReviewRequest(BaseModel):
    booking_id: Optional[Union[int, str]] = None
    rating: Optional[Union[int, str]] = None
    comment: Optional[str] = None


class SubmitCaretakerFeedbackRequest(BaseModel):
    rating: Optional[Union[int, str]] = None
    feedback: Optional[str] = None
    suggestion: Optional[str] = None
    is_anonymous: Optional[Union[bool, int, str]] = False


class UpdateFeedbackStatusRequest(BaseModel):
    feedback_id: Optional[Union[int, str]] = None
    status: Optional[str] = None
    admin_note: Optional[str] = None

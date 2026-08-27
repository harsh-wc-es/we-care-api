"""
WeCare — Complaint Schemas (Part 9)
"""

from typing import Optional, Union
from pydantic import BaseModel, Field


class CreateComplaintRequest(BaseModel):
    booking_id: Optional[Union[int, str]] = None
    subject: Optional[str] = None
    description: Optional[str] = None


class AdminUpdateComplaintStatusRequest(BaseModel):
    id: Optional[Union[int, str]] = None
    complaint_id: Optional[Union[int, str]] = None
    status: Optional[str] = None
    admin_note: Optional[str] = None

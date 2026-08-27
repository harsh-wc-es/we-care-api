"""
WeCare — User Profile Schemas
"""

from typing import Optional
from pydantic import BaseModel


class UserProfileResponse(BaseModel):
    id: int
    username: str
    email: str
    phone_number: Optional[str] = None
    role: str
    is_verified: int
    profile_picture: Optional[str] = None
    profile_picture_url: Optional[str] = None
    is_active: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_available: Optional[bool] = None
    availability_updated_at: Optional[str] = None


class ProfileUpdateForm(BaseModel):
    username: Optional[str] = None
    phone_number: Optional[str] = None

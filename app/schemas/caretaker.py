"""
WeCare — Caretaker Schemas
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class CaretakerProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    experience_years: Optional[int] = 0
    qualification: Optional[str] = None
    bio: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class AvailabilityUpdateRequest(BaseModel):
    is_available: bool


class AvailabilityPayloadData(BaseModel):
    is_available: bool
    manual_availability_enabled: bool
    availability_reason: Optional[str] = None
    availability_locked_by_admin: bool = False
    availability_locked_note: Optional[str] = None
    availability_locked_at: Optional[str] = None
    availability_changed_at: Optional[str] = None
    availability_changed_by: Optional[str] = None
    availability_auto_restored_at: Optional[str] = None
    availability_version: int = 1
    last_active_at: Optional[str] = None
    can_accept_booking: bool = False
    has_active_visit: bool = False

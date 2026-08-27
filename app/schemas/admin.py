"""
WeCare — Admin Management Schemas
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AdminProfileResponse(BaseModel):
    id: int
    name: str
    username: str
    email: str
    phone_number: Optional[str] = None
    role: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AdminProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: str
    phone_number: Optional[str] = None
    phone: Optional[str] = None


class UpdateUserStatusRequest(BaseModel):
    user_id: int
    is_active: int


class ApproveCaretakerRequest(BaseModel):
    user_id: Optional[int] = None
    caretaker_user_id: Optional[int] = None
    pricing_tier_id: Optional[int] = None
    tier_id: Optional[int] = None
    pricing_override_enabled: Optional[bool] = False
    customer_hourly_rate: Optional[float] = None
    caretaker_hourly_rate: Optional[float] = None
    payout_priority: Optional[int] = 0


class RejectCaretakerRequest(BaseModel):
    user_id: int
    rejection_reason: Optional[str] = ""


class BanCaretakerRequest(BaseModel):
    caretaker_user_id: Optional[int] = None
    user_id: Optional[int] = None
    reason: Optional[str] = None
    ban_reason: Optional[str] = None
    admin_note: Optional[str] = None


class ApproveDocumentRequest(BaseModel):
    caretaker_user_id: Optional[int] = None
    user_id: Optional[int] = None
    document_id: Optional[int] = None
    id: Optional[int] = None


class RejectDocumentItem(BaseModel):
    document_id: Optional[int] = None
    id: Optional[int] = None
    reason: Optional[str] = None
    admin_note: Optional[str] = None
    rejection_reason: Optional[str] = None


class RejectSelectedDocumentsRequest(BaseModel):
    caretaker_user_id: Optional[int] = None
    user_id: Optional[int] = None
    documents: List[RejectDocumentItem]


class SingleRejectDocumentRequest(BaseModel):
    document_id: Optional[int] = None
    id: Optional[int] = None
    reason: Optional[str] = None
    admin_note: Optional[str] = None
    rejection_reason: Optional[str] = None


class SetAvailabilityOverrideRequest(BaseModel):
    caretaker_user_id: int
    is_available: bool
    lock_availability: Optional[bool] = False
    reason: Optional[str] = ""
    note: Optional[str] = ""

"""
WeCare — Pricing Tier Schemas
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class CreatePricingTierRequest(BaseModel):
    name: str
    description: Optional[str] = None
    skill_level: Optional[str] = None
    customer_hourly_rate: float
    caretaker_hourly_rate: float
    is_active: Optional[bool] = True


class UpdatePricingTierRequest(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    skill_level: Optional[str] = None
    customer_hourly_rate: Optional[float] = None
    caretaker_hourly_rate: Optional[float] = None
    is_active: Optional[bool] = None


class DeletePricingTierRequest(BaseModel):
    id: Optional[int] = None


class UpdateCaretakerPricingRequest(BaseModel):
    caretaker_user_id: int
    pricing_tier_id: int
    pricing_override_enabled: Optional[bool] = False
    customer_hourly_rate: Optional[float] = None
    caretaker_hourly_rate: Optional[float] = None


class UpdateCaregiverTierPricingRequest(BaseModel):
    caretaker_user_id: Optional[int] = None
    caregiver_user_id: Optional[int] = None
    user_id: Optional[int] = None
    tier_id: Optional[int] = None
    pricing_tier_id: Optional[int] = None
    tier: Optional[str] = None
    tier_code: Optional[str] = None
    customer_rate_per_hour: Optional[float] = None
    customer_rate: Optional[float] = None
    customer_hourly_rate: Optional[float] = None
    caregiver_rate_per_hour: Optional[float] = None
    caregiver_rate: Optional[float] = None
    caretaker_hourly_rate: Optional[float] = None
    commission_percent: Optional[float] = None
    commission: Optional[float] = None
    commission_percentage: Optional[float] = None
    admin_note: Optional[str] = None
    reason: Optional[str] = None
    admin_notes: Optional[str] = None

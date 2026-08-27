"""
WeCare — Payment & Refund Schemas (Part 10)

Request schemas for payment endpoints.
Refund endpoints in Part 10 are READ-ONLY — no refund creation/admin processing schemas.
"""

from typing import Optional, Union
from pydantic import BaseModel


class PayAdvanceRequest(BaseModel):
    booking_id: Optional[Union[int, str]] = None
    payment_method: Optional[str] = None
    transaction_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class PayRemainingRequest(BaseModel):
    booking_id: Optional[Union[int, str]] = None
    payment_method: Optional[str] = None
    transaction_id: Optional[str] = None
    idempotency_key: Optional[str] = None

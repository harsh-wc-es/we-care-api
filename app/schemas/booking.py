"""
WeCare — Booking Schemas

Pydantic v2 schemas for all booking requests and responses.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class BookingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    caretaker_user_id: Union[int, str]
    patient_id: Union[int, str]
    service_type: str
    booking_date: str
    start_time: str
    end_time: str
    address: str
    notes: Optional[str] = ""


class BookingRespondRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    action: str
    decline_reason_code: Optional[str] = None
    decline_reason_label: Optional[str] = None
    decline_note: Optional[str] = None


class BookingAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]


class BookingRejectRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    reason: Optional[str] = None
    decline_reason_code: Optional[str] = None
    decline_reason_label: Optional[str] = None
    decline_note: Optional[str] = None


class BookingCancelRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    cancellation_reason: Optional[str] = None
    reason: Optional[str] = None


class CaretakerCancelBookingRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    reason: Optional[str] = None
    cancellation_reason: Optional[str] = None


class AdminCancelBookingRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    reason: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancel_reason_code: Optional[str] = None
    cancel_reason_label: Optional[str] = None
    cancel_note: Optional[str] = None


class BookingCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]


class BookingVisitOtpRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]

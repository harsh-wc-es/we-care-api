"""
WeCare — Visit Execution Schemas

Pydantic v2 schemas for Visit domain requests.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class VerifyOtpRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    otp: str


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    latitude: Optional[Union[float, str]] = None
    longitude: Optional[Union[float, str]] = None
    notes: Optional[str] = None


class CheckOutRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    latitude: Optional[Union[float, str]] = None
    longitude: Optional[Union[float, str]] = None
    notes: Optional[str] = None


class AddNoteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    note: str


class UpdateTaskStatusRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Union[int, str]
    task_id: Union[int, str]
    status: str

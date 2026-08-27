"""
WeCare — Emergency SOS Schemas

Pydantic v2 schemas for SOS domain requests.
"""

from typing import Optional, Union
from pydantic import BaseModel, ConfigDict


class CreateSosRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Optional[Union[int, str]] = None
    message: Optional[str] = None
    latitude: Optional[Union[float, str]] = None
    longitude: Optional[Union[float, str]] = None


class CaretakerCreateSosRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    booking_id: Optional[Union[int, str]] = None
    message: Optional[str] = None
    latitude: Optional[Union[float, str]] = None
    longitude: Optional[Union[float, str]] = None


class ResolveSosRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sos_id: Optional[Union[int, str]] = None


class UpdateSosStatusRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sos_id: Optional[Union[int, str]] = None
    status: Optional[str] = None

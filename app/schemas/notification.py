"""
WeCare — Notification Schemas (Part 10)

Request/response schemas for notification endpoints.
"""

from typing import Optional, Union
from pydantic import BaseModel


class MarkReadRequest(BaseModel):
    notification_id: Optional[Union[int, str]] = None


class CreateNotificationRequest(BaseModel):
    user_id: Optional[Union[int, str]] = None
    title: Optional[str] = None
    message: Optional[str] = None


class RegisterDeviceRequest(BaseModel):
    device_token: Optional[str] = None
    platform: Optional[str] = None
    app_type: Optional[str] = None


class RemoveDeviceRequest(BaseModel):
    device_token: Optional[str] = None

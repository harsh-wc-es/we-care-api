"""
WeCare — Checklist Schemas (Part 10)

Request schemas for booking checklist task endpoints.
"""

from typing import Optional, Union
from pydantic import BaseModel


class CreateTaskRequest(BaseModel):
    booking_id: Optional[Union[int, str]] = None
    title: Optional[str] = None
    description: Optional[str] = None


class MarkDoneRequest(BaseModel):
    task_id: Optional[Union[int, str]] = None
    status: Optional[str] = "completed"

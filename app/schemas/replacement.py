"""
WeCare — Replacement Ticket Schemas (Part 9)
"""

from typing import Optional, Union
from pydantic import BaseModel, Field


class CreateReplacementTicketRequest(BaseModel):
    booking_id: Optional[Union[int, str]] = None
    complaint_id: Optional[Union[int, str]] = None
    reason: Optional[str] = None


class AdminAssignReplacementTicketRequest(BaseModel):
    ticket_id: Optional[Union[int, str]] = None
    id: Optional[Union[int, str]] = None
    replacement_caretaker_user_id: Optional[Union[int, str]] = None
    admin_note: Optional[str] = None
    admin_notes: Optional[str] = None


class AdminUpdateReplacementTicketStatusRequest(BaseModel):
    id: Optional[Union[int, str]] = None
    ticket_id: Optional[Union[int, str]] = None
    status: Optional[str] = None
    replacement_caretaker_user_id: Optional[Union[int, str]] = None
    admin_note: Optional[str] = None


class AdminResolveReplacementTicketRequest(BaseModel):
    ticket_id: Optional[Union[int, str]] = None
    id: Optional[Union[int, str]] = None
    admin_note: Optional[str] = None
    admin_notes: Optional[str] = None


class AdminCancelReplacementTicketRequest(BaseModel):
    ticket_id: Optional[Union[int, str]] = None
    id: Optional[Union[int, str]] = None
    admin_note: Optional[str] = None
    admin_notes: Optional[str] = None


class AdminDeleteReplacementTicketRequest(BaseModel):
    id: Optional[Union[int, str]] = None

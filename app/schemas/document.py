"""
WeCare — Caretaker Document Schemas
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class SingleDocumentUploadResponse(BaseModel):
    document_id: int
    document_type: str
    status: str
    file_path: str
    view_url: str


class BulkDocumentItem(BaseModel):
    document_id: int
    document_type: str
    file_path: str
    view_url: str
    status: str


class BulkDocumentUploadResponse(BaseModel):
    uploaded_count: int
    documents: Dict[str, BulkDocumentItem]


class DocumentSlotItem(BaseModel):
    document_id: Optional[int] = None
    id: Optional[int] = None
    document_type: str
    label: str
    display_name: str
    required: bool
    optional: bool
    uploaded: bool
    status: Optional[str] = None
    file_url: Optional[str] = None
    view_url: Optional[str] = None
    original_file_name: Optional[str] = None
    uploaded_at: Optional[str] = None
    admin_note: Optional[str] = None
    rejection_reason: Optional[str] = None
    reviewed_by_admin_id: Optional[int] = None
    reviewed_at: Optional[str] = None
    can_reupload: bool = True

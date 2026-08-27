"""
WeCare — Patient Details Schemas
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AddPatientRequest(BaseModel):
    patient_name: str
    age: int
    gender: str
    medical_condition: Optional[str] = None
    allergies: Optional[str] = None
    medications: Optional[str] = None
    special_instructions: Optional[str] = None
    mobility_status: Optional[str] = None
    care_type: Optional[str] = None


class UpdatePatientRequest(BaseModel):
    id: int
    patient_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    medical_condition: Optional[str] = None
    allergies: Optional[str] = None
    medications: Optional[str] = None
    special_instructions: Optional[str] = None
    mobility_status: Optional[str] = None
    care_type: Optional[str] = None


class DeletePatientRequest(BaseModel):
    id: int


class PatientResponse(BaseModel):
    id: int
    family_user_id: int
    patient_name: str
    age: int
    gender: str
    medical_condition: Optional[str] = None
    allergies: Optional[str] = None
    medications: Optional[str] = None
    special_instructions: Optional[str] = None
    mobility_status: Optional[str] = None
    care_type: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PatientPaginationInfo(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class PatientListResponse(BaseModel):
    items: List[PatientResponse]
    patients: List[PatientResponse]
    pagination: PatientPaginationInfo

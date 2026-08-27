"""
WeCare — Patient Routes

POST /api/v1/patient/add_patient    → api/v1/patient/add_patient
GET  /api/v1/patient/view_patient   → api/v1/patient/view_patient
POST /api/v1/patient/update_patient → api/v1/patient/update_patient
POST /api/v1/patient/delete_patient → api/v1/patient/delete_patient
GET  /api/v1/patient/list_patients  → api/v1/patient/list_patients
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_family
from app.schemas.patient import (
    AddPatientRequest,
    DeletePatientRequest,
    UpdatePatientRequest,
)
from app.services.patient_service import (
    add_patient,
    delete_patient,
    get_patient_by_id,
    list_patients,
    update_patient,
)

router = APIRouter()


@router.post("/add_patient", status_code=201)
def add_patient_route(
    body: AddPatientRequest,
    current_user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/patient/add_patient
    """
    user_id = int(current_user["id"])
    patient = add_patient(db=db, family_user_id=user_id, data=body.model_dump())
    return success_response(
        data=patient,
        message="Patient details added successfully",
        status_code=201,
    )


@router.get("/view_patient")
def view_patient_route(
    id: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/patient/view_patient
    """
    if not id or not str(id).strip():
        raise APIException(message="Patient id is required", status_code=400)

    try:
        patient_id = int(id)
    except ValueError:
        raise APIException(message="Patient id is required", status_code=400)

    user_id = int(current_user["id"])
    patient = get_patient_by_id(db=db, patient_id=patient_id, family_user_id=user_id)
    return success_response(data=patient, message="Patient retrieved successfully")


@router.post("/update_patient")
def update_patient_route(
    body: UpdatePatientRequest,
    current_user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/patient/update_patient
    """
    user_id = int(current_user["id"])
    update_patient(db=db, family_user_id=user_id, data=body.model_dump())
    return success_response(message="Patient updated successfully")


@router.post("/delete_patient")
def delete_patient_route(
    body: DeletePatientRequest,
    current_user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/patient/delete_patient
    """
    user_id = int(current_user["id"])
    delete_patient(db=db, patient_id=body.id, family_user_id=user_id)
    return success_response(message="Patient deleted successfully")


@router.get("/list_patients")
def list_patients_route(
    current_user: Dict[str, Any] = Depends(require_family),
    db: Session = Depends(get_db),
):
    """
    Route: api/v1/patient/list_patients
    """
    user_id = int(current_user["id"])
    result = list_patients(db=db, family_user_id=user_id)
    return success_response(data=result, message="Patients retrieved successfully")

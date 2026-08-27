"""
WeCare — Patient Service

Mirrors api/v1/patient/ endpoints logic.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException


def patient_to_dict(row: Any) -> Dict[str, Any]:
    """Convert a patient database row or mapping to a dictionary."""
    if hasattr(row, "_mapping"):
        m = row._mapping
    elif isinstance(row, dict):
        m = row
    else:
        m = row.__dict__

    created_at = m.get("created_at")
    updated_at = m.get("updated_at")

    return {
        "id": int(m["id"]),
        "family_user_id": int(m["family_user_id"]),
        "patient_name": m["patient_name"],
        "age": int(m["age"]),
        "gender": str(m["gender"].value if hasattr(m["gender"], "value") else m["gender"]),
        "medical_condition": m.get("medical_condition"),
        "allergies": m.get("allergies"),
        "medications": m.get("medications"),
        "special_instructions": m.get("special_instructions"),
        "mobility_status": m.get("mobility_status"),
        "care_type": m.get("care_type"),
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else (str(created_at) if created_at else None),
        "updated_at": updated_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(updated_at, "strftime") else (str(updated_at) if updated_at else None),
    }


def add_patient(
    db: Session,
    family_user_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/patient/add_patient
    Enforces 1-patient-per-family limit (409 Conflict).
    """
    patient_name = str(data.get("patient_name", "")).strip()
    age = data.get("age")
    gender = str(data.get("gender", "")).strip().lower()

    errors: Dict[str, List[str]] = {}
    if not patient_name:
        errors["patient_name"] = ["Patient name is required"]
    if age is None or str(age) == "":
        errors["age"] = ["Age is required"]
    else:
        try:
            age_int = int(age)
            if age_int <= 0:
                errors["age"] = ["Age must be greater than 0"]
        except ValueError:
            errors["age"] = ["Age must be an integer"]

    if not gender:
        errors["gender"] = ["Gender is required"]
    elif gender not in ["male", "female", "other"]:
        errors["gender"] = ["Gender must be male, female, or other"]

    if errors:
        raise APIException(
            message="Validation failed",
            status_code=400,
            errors=errors,
        )

    # Check 1-patient-per-family limit
    existing = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :uid LIMIT 1"),
        {"uid": family_user_id},
    ).fetchone()

    if existing:
        raise APIException(
            message="Family account already has a patient profile",
            status_code=409,
            errors={"patient": ["Only one patient profile is allowed per family account"]},
        )

    db.execute(
        text(
            "INSERT INTO patient_details "
            "(family_user_id, patient_name, age, gender, medical_condition, "
            "allergies, medications, special_instructions, mobility_status, care_type, created_at, updated_at) "
            "VALUES (:family_user_id, :patient_name, :age, :gender, :medical_condition, "
            ":allergies, :medications, :special_instructions, :mobility_status, :care_type, NOW(), NOW())"
        ),
        {
            "family_user_id": family_user_id,
            "patient_name": patient_name,
            "age": int(age),
            "gender": gender,
            "medical_condition": data.get("medical_condition"),
            "allergies": data.get("allergies"),
            "medications": data.get("medications"),
            "special_instructions": data.get("special_instructions"),
            "mobility_status": data.get("mobility_status"),
            "care_type": data.get("care_type"),
        },
    )
    db.commit()

    created = db.execute(
        text("SELECT * FROM patient_details WHERE family_user_id = :uid LIMIT 1"),
        {"uid": family_user_id},
    ).fetchone()

    return patient_to_dict(created)


def get_patient_by_id(
    db: Session,
    patient_id: int,
    family_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/patient/view_patient
    """
    patient = db.execute(
        text("SELECT * FROM patient_details WHERE id = :id AND family_user_id = :uid LIMIT 1"),
        {"id": patient_id, "uid": family_user_id},
    ).fetchone()

    if not patient:
        raise APIException(message="Patient not found", status_code=404)

    return patient_to_dict(patient)


def update_patient(
    db: Session,
    family_user_id: int,
    data: Dict[str, Any],
) -> None:
    """
    Route: api/v1/patient/update_patient
    """
    patient_id = data.get("id")
    if not patient_id:
        raise APIException(message="Patient id is required", status_code=400)

    try:
        patient_id_int = int(patient_id)
    except ValueError:
        raise APIException(message="Patient id is required", status_code=400)

    patient = db.execute(
        text("SELECT * FROM patient_details WHERE id = :id AND family_user_id = :uid LIMIT 1"),
        {"id": patient_id_int, "uid": family_user_id},
    ).fetchone()

    if not patient:
        raise APIException(message="Patient not found", status_code=404)

    p_dict = patient_to_dict(patient)

    patient_name = data.get("patient_name", p_dict["patient_name"])
    age = data.get("age", p_dict["age"])
    gender = data.get("gender", p_dict["gender"])
    medical_condition = data.get("medical_condition", p_dict["medical_condition"])
    allergies = data.get("allergies", p_dict["allergies"])
    medications = data.get("medications", p_dict["medications"])
    special_instructions = data.get("special_instructions", p_dict["special_instructions"])
    mobility_status = data.get("mobility_status", p_dict["mobility_status"])
    care_type = data.get("care_type", p_dict["care_type"])

    db.execute(
        text(
            "UPDATE patient_details SET "
            "patient_name = :patient_name, "
            "age = :age, "
            "gender = :gender, "
            "medical_condition = :medical_condition, "
            "allergies = :allergies, "
            "medications = :medications, "
            "special_instructions = :special_instructions, "
            "mobility_status = :mobility_status, "
            "care_type = :care_type, "
            "updated_at = NOW() "
            "WHERE id = :id AND family_user_id = :uid"
        ),
        {
            "patient_name": patient_name,
            "age": int(age) if age is not None else p_dict["age"],
            "gender": gender,
            "medical_condition": medical_condition,
            "allergies": allergies,
            "medications": medications,
            "special_instructions": special_instructions,
            "mobility_status": mobility_status,
            "care_type": care_type,
            "id": patient_id_int,
            "uid": family_user_id,
        },
    )
    db.commit()


def delete_patient(
    db: Session,
    patient_id: int,
    family_user_id: int,
) -> None:
    """
    Route: api/v1/patient/delete_patient
    """
    result = db.execute(
        text("DELETE FROM patient_details WHERE id = :id AND family_user_id = :uid"),
        {"id": patient_id, "uid": family_user_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise APIException(message="Patient not found", status_code=404)


def list_patients(
    db: Session,
    family_user_id: int,
) -> Dict[str, Any]:
    """
    Route: api/v1/patient/list_patients
    """
    count_res = db.execute(
        text("SELECT COUNT(*) FROM patient_details WHERE family_user_id = :uid"),
        {"uid": family_user_id},
    ).scalar()
    total = min(1, int(count_res or 0))

    rows = db.execute(
        text(
            "SELECT * FROM patient_details "
            "WHERE family_user_id = :uid "
            "ORDER BY id DESC LIMIT 1 OFFSET 0"
        ),
        {"uid": family_user_id},
    ).fetchall()

    patients = [patient_to_dict(r) for r in rows]

    return {
        "items": patients,
        "patients": patients,
        "pagination": {
            "page": 1,
            "limit": 1,
            "total": total,
            "total_pages": 1 if total > 0 else 0,
        },
    }

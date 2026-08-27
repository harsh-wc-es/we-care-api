"""
WeCare — Patient Endpoint Tests

Tests all 5 patient endpoints:
- POST /api/v1/patient/add_patient
- GET  /api/v1/patient/view_patient
- POST /api/v1/patient/update_patient
- GET  /api/v1/patient/list_patients
- POST /api/v1/patient/delete_patient
"""

import pytest
from tests.conftest import make_auth_headers


def test_patient_crud_flow(client, test_user):
    headers = make_auth_headers(test_user)

    # 1. Add patient
    payload = {
        "patient_name": "Grandpa John",
        "age": 78,
        "gender": "male",
        "medical_condition": "Mild arthritis",
        "allergies": "Penicillin",
        "medications": "Pain relievers",
        "special_instructions": "Needs walking assistance",
        "mobility_status": "Assisted",
        "care_type": "Elderly Care",
    }
    res_add = client.post("/api/v1/patient/add_patient", json=payload, headers=headers)
    assert res_add.status_code == 201
    add_body = res_add.json()
    assert add_body["success"] is True
    assert add_body["message"] == "Patient details added successfully"
    patient_id = add_body["data"]["id"]
    assert add_body["data"]["patient_name"] == "Grandpa John"
    assert add_body["data"]["age"] == 78
    assert add_body["data"]["gender"] == "male"

    # 2. Add second patient should fail with 409 Conflict (1-patient-per-family rule)
    res_add_dup = client.post("/api/v1/patient/add_patient", json=payload, headers=headers)
    assert res_add_dup.status_code == 409
    dup_body = res_add_dup.json()
    assert dup_body["success"] is False
    assert "already has a patient profile" in dup_body["message"]

    # 3. View patient
    res_view = client.get(f"/api/v1/patient/view_patient?id={patient_id}", headers=headers)
    assert res_view.status_code == 200
    view_body = res_view.json()
    assert view_body["success"] is True
    assert view_body["data"]["id"] == patient_id
    assert view_body["data"]["patient_name"] == "Grandpa John"

    # 4. List patients
    res_list = client.get("/api/v1/patient/list_patients", headers=headers)
    assert res_list.status_code == 200
    list_body = res_list.json()
    assert list_body["success"] is True
    assert len(list_body["data"]["items"]) == 1
    assert list_body["data"]["pagination"]["total"] == 1

    # 5. Update patient
    res_update = client.post(
        "/api/v1/patient/update_patient",
        json={"id": patient_id, "patient_name": "Grandpa John Updated", "age": 79},
        headers=headers,
    )
    assert res_update.status_code == 200
    assert res_update.json()["message"] == "Patient updated successfully"

    # Verify update
    res_view2 = client.get(f"/api/v1/patient/view_patient?id={patient_id}", headers=headers)
    assert res_view2.json()["data"]["patient_name"] == "Grandpa John Updated"
    assert res_view2.json()["data"]["age"] == 79

    # 6. Delete patient
    res_del = client.post("/api/v1/patient/delete_patient", json={"id": patient_id}, headers=headers)
    assert res_del.status_code == 200
    assert res_del.json()["message"] == "Patient deleted successfully"

    # 7. View after delete should return 404
    res_view_deleted = client.get(f"/api/v1/patient/view_patient?id={patient_id}", headers=headers)
    assert res_view_deleted.status_code == 404

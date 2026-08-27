"""
Tests for API Response & Exception Infrastructure (STEP 4)

Verifies:
- Standard response envelope format: success, message, data, errors
- Status codes on success/error responses
- APIException raising and FastAPI exception handler wrapping
"""

import json
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import APIException, api_exception_handler
from app.core.response import success_response, error_response


def test_success_response_structure():
    """success_response returns expected JSON structure."""
    resp = success_response("Operation succeeded", {"item_id": 123}, status_code=201)
    assert resp.status_code == 201

    body = json.loads(resp.body)
    assert body["success"] is True
    assert body["message"] == "Operation succeeded"
    assert body["data"] == {"item_id": 123}
    assert body["errors"] is None


def test_error_response_structure():
    """error_response returns expected JSON structure."""
    resp = error_response("Validation error", {"email": ["Email is required"]}, status_code=422)
    assert resp.status_code == 422

    body = json.loads(resp.body)
    assert body["success"] is False
    assert body["message"] == "Validation error"
    assert body["data"] is None
    assert body["errors"] == {"email": ["Email is required"]}


def test_error_response_string_wrapping():
    """String errors are wrapped as {'general': [str]} matching response."""
    resp = error_response("Failed", "Something went wrong", status_code=400)
    body = json.loads(resp.body)
    assert body["errors"] == {"general": ["Something went wrong"]}


def test_api_exception_handled():
    """APIException is caught and rendered in the standard error envelope."""
    test_app = FastAPI()
    test_app.add_exception_handler(APIException, api_exception_handler)

    @test_app.get("/test-error")
    def trigger_error():
        raise APIException("Unauthorized access", errors={"auth": ["Invalid token"]}, status_code=401)

    client = TestClient(test_app)
    response = client.get("/test-error")

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["message"] == "Unauthorized access"
    assert data["data"] is None
    assert data["errors"] == {"auth": ["Invalid token"]}

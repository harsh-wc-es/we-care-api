"""
STEP 15a: Test that the FastAPI application starts and health endpoint works.
"""


def test_health_endpoint_returns_success(client):
    """Health endpoint must match api/v1/health response."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["message"] == "API is reachable"
    assert data["errors"] is None
    assert data["data"]["app"] == "WeCare API"
    assert data["data"]["version"] == "Demo Prototype"
    assert data["data"]["api_base_path"] == "/api/v1"
    assert "environment" in data["data"]
    assert "time" in data["data"]


def test_health_endpoint_time_format(client):
    """health uses date('Y-m-d H:i:s') format."""
    response = client.get("/api/v1/health")
    time_str = response.json()["data"]["time"]
    # Verify format: YYYY-MM-DD HH:MM:SS
    import datetime
    parsed = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    assert parsed is not None


def test_health_method_not_allowed(client):
    """health only allows GET."""
    response = client.post("/api/v1/health")
    assert response.status_code == 405

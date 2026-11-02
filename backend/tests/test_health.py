from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_standard_success_response():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "DukaanFlow API is running",
        "data": {"status": "healthy"},
    }


def test_unknown_route_returns_standard_error_response():
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "RESOURCE_NOT_FOUND"
    assert body["details"] == {}


def test_cors_allows_configured_frontend_origin():
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

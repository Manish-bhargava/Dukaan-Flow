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


def test_unexpected_error_is_a_json_500_with_cors_headers_and_no_traceback():
    """A bug in an endpoint must still reach the browser as the standard error (with CORS
    headers, so the frontend can show it) and never as a traceback, even with DEBUG on."""
    from app.core.config import settings
    from app.main import create_app

    test_app = create_app(settings.model_copy(update={"DEBUG": True}))

    def broken():
        raise RuntimeError("secret internal detail")

    test_app.add_api_route("/api/v1/_broken", broken)
    origin = settings.cors_origins_list[0]
    response = TestClient(test_app, raise_server_exceptions=False).get("/api/v1/_broken", headers={"Origin": origin})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == origin
    assert response.json() == {"success": False, "message": "An unexpected error occurred",
                               "error_code": "INTERNAL_SERVER_ERROR", "details": {}}
    assert "secret internal detail" not in response.text and "Traceback" not in response.text

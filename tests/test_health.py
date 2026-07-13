from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_application_initializes() -> None:
    assert app.title == "TaskFlow API"


def test_health_returns_success() -> None:
    response = client.get("/health")

    assert response.status_code == 200


def test_health_response_format() -> None:
    response = client.get("/health")

    assert response.json() == {
        "status": "ok",
        "service": "TaskFlow API",
        "version": "0.1.0",
    }


def test_health_is_available_under_api_v1_prefix() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200

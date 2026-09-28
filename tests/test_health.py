from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_app_imports_and_health_endpoint_works() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "askmydocs-ai",
        "version": "0.1.0",
    }

from importlib.metadata import version

from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings


def _client() -> TestClient:
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://osrm.test",
        osrm_url_foot="http://osrm.test",
        osrm_url_bike="http://osrm.test",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_get_health_returns_ok() -> None:
    with _client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": version("engineer-route-plan-backend"),
    }


def test_get_health_content_type_is_json() -> None:
    with _client() as client:
        response = client.get("/health")

    assert response.headers["content-type"] == "application/json"

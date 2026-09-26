from tests.api.region_fakes import client


def test_list_regions() -> None:
    response = client().get("/api/v1/regions")

    assert response.status_code == 200
    assert response.json() == [
        {"code": "east", "name": "Восток"},
        {"code": "south_east", "name": "Юго-Восток"},
    ]
    assert response.headers["X-Request-ID"]

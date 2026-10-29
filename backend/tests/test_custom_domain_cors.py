import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def isolated_data():
    # CORS preflights end in the middleware and never access persistence or AI.
    yield


@pytest.mark.parametrize("origin", [
    "https://razync.com.br",
    "https://www.razync.com.br",
    "https://rodrigofrrsilva1703-a11y.github.io",
])
def test_frontend_domains_can_preflight_uploads(origin):
    response = TestClient(app).options("/api/v1/companies", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unrelated_domain_is_not_allowed():
    response = TestClient(app).options("/api/v1/companies", headers={
        "Origin": "https://unrelated.example",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers

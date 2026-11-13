from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest

from app import operating_hours
from app.main import app

BRT = ZoneInfo("America/Sao_Paulo")


@pytest.mark.parametrize("day", range(19, 26))
def test_acesso_24h_todos_os_dias(day):
    for hour, minute in [(0, 0), (6, 59), (7, 0), (23, 59)]:
        instant = datetime(2026, 10, day, hour, minute, tzinfo=BRT)
        assert operating_hours.is_open(instant)
        assert operating_hours.seconds_until_open(instant) == 0


def test_api_nao_depende_mais_do_bloqueio_legado(monkeypatch):
    monkeypatch.setattr(operating_hours, "is_open", lambda *a: False)
    monkeypatch.setattr(operating_hours, "seconds_until_open", lambda *a: 1200)
    client = TestClient(app)
    response = client.get("/api/v1/companies", headers={"Origin": "https://razync.com.br"})
    assert response.status_code == 200
    assert "retry-after" not in response.headers
    assert response.headers["access-control-allow-origin"] == "https://razync.com.br"
    assert client.get("/health").status_code == 200


def test_api_disponivel_de_madrugada(monkeypatch):
    monkeypatch.setattr(operating_hours, "current_time", lambda now=None:
                        datetime(2026, 10, 25, 0, 0, tzinfo=BRT))
    assert TestClient(app).get("/api/v1/companies").status_code == 200

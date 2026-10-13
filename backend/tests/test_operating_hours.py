from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import operating_hours
from app.main import app

BRT = ZoneInfo("America/Sao_Paulo")


def test_janela_brasilia_abre_as_sete():
    assert not operating_hours.is_open(datetime(2026, 10, 14, 0, 0, tzinfo=BRT))
    assert not operating_hours.is_open(datetime(2026, 10, 14, 6, 59, tzinfo=BRT))
    assert operating_hours.is_open(datetime(2026, 10, 14, 7, 0, tzinfo=BRT))
    assert operating_hours.is_open(datetime(2026, 10, 14, 23, 59, tzinfo=BRT))


def test_segundos_ate_abertura_nao_usam_horario_do_servidor():
    assert operating_hours.seconds_until_open(
        datetime(2026, 10, 14, 6, 30, tzinfo=BRT)) == 1800
    assert operating_hours.seconds_until_open(
        datetime(2026, 10, 14, 7, 0, tzinfo=BRT)) == 0
    assert operating_hours.seconds_until_open(
        datetime(2026, 10, 14, 23, 0, tzinfo=BRT)) == 0


def test_fora_do_horario_api_bloqueia_sem_impedir_healthcheck(monkeypatch):
    monkeypatch.setattr(operating_hours, "is_open", lambda *a: False)
    monkeypatch.setattr(operating_hours, "seconds_until_open", lambda *a: 1200)
    client = TestClient(app)
    response = client.get("/api/v1/companies",
                          headers={"Origin": "https://rodrigofrrsilva1703-a11y.github.io"})
    assert response.status_code == 503
    assert response.json()["codigo"] == "FORA_DO_EXPEDIENTE"
    assert response.headers["retry-after"] == "1200"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get("access-control-allow-origin") == "https://rodrigofrrsilva1703-a11y.github.io"
    assert client.get("/health").status_code == 200


def test_durante_expediente_api_libera_fluxo(monkeypatch):
    monkeypatch.setattr(operating_hours, "is_open", lambda *a: True)
    response = TestClient(app).get("/api/v1/companies")
    assert response.status_code == 200


def test_domingo_fechado_o_dia_inteiro():
    for hour in (0, 6, 7, 12, 23):
        assert not operating_hours.is_open(datetime(2026, 10, 18, hour, 0, tzinfo=BRT))
    assert operating_hours.is_open(datetime(2026, 10, 17, 23, 59, tzinfo=BRT))
    assert operating_hours.is_open(datetime(2026, 10, 19, 7, 0, tzinfo=BRT))


def test_domingo_reabre_apenas_segunda_as_sete():
    assert operating_hours.seconds_until_open(
        datetime(2026, 10, 18, 0, 0, tzinfo=BRT)) == 31 * 3600
    assert operating_hours.seconds_until_open(
        datetime(2026, 10, 18, 12, 0, tzinfo=BRT)) == 19 * 3600
    assert operating_hours.seconds_until_open(
        datetime(2026, 10, 19, 6, 59, tzinfo=BRT)) == 60

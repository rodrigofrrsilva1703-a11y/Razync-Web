"""Uso agregado das IAs: contadores locais sem dados fiscais ou chaves."""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import ai_budget
from app.main import app


@pytest.fixture(autouse=True)
def isolate_counters(monkeypatch):
    monkeypatch.setattr(ai_budget, "_daily", {})
    monkeypatch.setattr(ai_budget, "_windows", {})
    monkeypatch.setattr(ai_budget, "_slots", {})


def _run(provider, model, body, raw):
    with ai_budget.request_slot(provider, model, body) as record:
        record(raw)


def test_uso_separa_provedores_e_modelos_sem_conteudo_privado(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "SEGREDO-TESTE")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GROQ_ZDR_CONFIRMED", "1")
    groq_body = {"messages": [{"role": "user", "content": "HISTORICO-CONFIDENCIAL-XYZ"}],
                 "max_completion_tokens": 100}
    _run("groq", "openai/gpt-oss-20b", groq_body, {"usage": {"total_tokens": 152}})
    _run("gemini", "gemini-2.5-flash-lite",
         {"contents": [{"parts": [{"text":"NOTA-FISCAL-SECRET"}]}]},
         {"usageMetadata": {"promptTokenCount": 10, "totalTokenCount": 27}})
    _run("openrouter", "openrouter/free",
         {"messages": [{"role": "user", "content": "NOME-CLIENTE"}]},
         {"choices": [], "usage": {}})
    response = TestClient(app).get("/api/v1/conferencia-fiscal/ia/uso")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["escopo"] == "instancia_atual"
    assert body["data_utc"] == datetime.now(timezone.utc).date().isoformat()
    assert len(body["provedores"]) == 3
    providers = {p["id"]: p for p in body["provedores"]}
    assert providers["groq"]["chamadas"] == 1
    assert providers["groq"]["respostas"] == 1
    assert providers["groq"]["tokens_informados"] == 152
    assert providers["gemini"]["tokens_informados"] == 27
    assert providers["openrouter"]["respostas_sem_tokens"] == 1
    assert providers["openrouter"]["tokens_informados"] == 0
    assert providers["openrouter"]["saldo_diario_real"] is None
    assert providers["gemini"]["cota_diaria_real"] is None
    assert providers["groq"]["controle_local"]["requisicoes_minuto"] == 30
    for private in ("SEGREDO-TESTE", "HISTORICO-CONFIDENCIAL-XYZ",
                    "NOTA-FISCAL-SECRET", "NOME-CLIENTE"):
        assert private not in response.text


def test_falhas_e_respostas_sao_contadas_separadamente():
    with pytest.raises(RuntimeError):
        with ai_budget.request_slot(
            "openrouter", "openrouter/free", {"messages": [{"role":"user", "content": "Teste"}]}
        ) as _:
            raise RuntimeError("dado sigiloso arbitrário")
    row = ai_budget.daily_report()["provedores"][2]
    assert row["chamadas"] == 1
    assert row["falhas"] == 1
    assert row["respostas"] == 0


def test_nao_reutiliza_consumo_entre_dias_nem_inventa_saldo():
    ai_budget._daily[("2000-01-01", "groq", "older")] = {
        "chamadas": 300, "respostas": 100, "falhas": 200, "tokens_informados": 1000,
        "respostas_sem_tokens": 0, "ultima_chamada": None,
        "ultima_resposta": None, "ultima_falha": None,
    }
    report = ai_budget.daily_report()
    assert report["provedores"][0]["chamadas"] == 0
    assert report["provedores"][0]["saldo_diario_real"] is None
    assert "último reinício" in report["observacao"]
    assert not report["provedores"][0]["modelos"]


def test_rejeicao_local_nao_conta_como_chamada_externa(monkeypatch):
    monkeypatch.setattr(ai_budget, "_LOCAL_LIMITS", dict(ai_budget._LOCAL_LIMITS, groq=(0, 0)))
    with pytest.raises(HTTPException) as error:
        with ai_budget.request_slot("groq", "openai/gpt-oss-20b",
                                    {"messages": [{"role": "user", "content": "Teste"}]}):
            raise AssertionError("não deve executar a chamada externa")
    assert error.value.status_code == 429
    assert ai_budget.daily_report()["provedores"][0]["chamadas"] == 0

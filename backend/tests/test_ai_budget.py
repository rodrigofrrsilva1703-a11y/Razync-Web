import json
import pytest
from fastapi import HTTPException
from app import ai_budget, fiscal_ai


@pytest.fixture(autouse=True)
def budget_state(monkeypatch):
    monkeypatch.setattr(ai_budget, "_windows", {})
    monkeypatch.setattr(ai_budget, "_slots", {})


def test_usuarios_compartilham_limite_de_pedidos_e_renovacao(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ai_budget.time, "monotonic", lambda: now[0])
    for _ in range(15):
        with ai_budget.request_slot("gemini", "test", {"contents": []}):
            pass
    with pytest.raises(HTTPException) as error:
        with ai_budget.request_slot("gemini", "test", {}):
            pytest.fail("não deve transmitir")
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "60"
    now[0] += 61
    with ai_budget.request_slot("gemini", "test", {}):
        pass


def test_tokens_reais_substituem_estimativa_sem_guardar_dados():
    with ai_budget.request_slot("groq", "test", {"messages": [{"content":"dado privado"}]}) as usage:
        usage({"usage": {"total_tokens": 7900}})
    with pytest.raises(HTTPException):
        with ai_budget.request_slot("groq", "test", {"messages": []}):
            pytest.fail("não deve transmitir")
    assert "dado privado" not in str(ai_budget._windows)


def test_compactacao_gemini_preserva_historico_valores_refs_e_origem(monkeypatch):
    record = {"referencia":"L1", "conta":"123", "historico":"histórico completo " * 50,
              "debito":123.45, "credito":0, "debito_brl":"R$ 123,45", "credito_brl":"R$ 0,00", "data":"01/10/2026"}
    context = {"grupos":[{"resumo":{"conta":"123"}, "lancamentos":[record]}]}
    payload = {"contents":[{"parts":[{"text":json.dumps(context)}]}]}
    seen = []
    monkeypatch.setattr(fiscal_ai, "_gemini_send", lambda body, *a, **k: seen.append(body) or ({}, "test", {}))
    fiscal_ai._gemini_completion(payload, "synthetic", "test")
    sent = json.loads(seen[0]["contents"][0]["parts"][0]["text"])["grupos"][0]["lancamentos"][0]
    assert sent["historico"] == record["historico"]
    assert sent["debito_brl"] == record["debito_brl"]
    assert sent["referencia"] == "L1"
    assert "debito" not in sent
    assert json.loads(payload["contents"][0]["parts"][0]["text"]) == context

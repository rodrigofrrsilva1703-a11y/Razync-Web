"""Regressões do provedor Groq gratuito, com requisições inteiramente simuladas."""
import io
import json
import urllib.error

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import fiscal_ai, groq_fiscal
from app.main import app


@pytest.fixture(autouse=True)
def isolated_groq(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.delenv("GROQ_ZDR_CONFIRMED", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("RAZYNC_AI_PRIMARY", "groq")
    monkeypatch.setenv("RAZYNC_AI_LEGACY_GEMINI", "0")


def example_report():
    return {
        "empresa": "FICTICIA",
        "periodo_fiscal": {"inicio":"2026-08-01","fim":"2026-08-31"},
        "periodo_razao": {"inicio":"2026-08-01","fim":"2026-08-31"},
        "lancamentos": [{
            "conta": "508", "data": "2026-08-07",
            "historico": "Compra NF 100 CPF 123.456.789-01 usuario@teste.com",
            "contrapartida": "1000", "debito": 8000, "credito": 0,
            "classificacao":"debito", "natureza":"ENTRADAS",
        }],
        "contas": [{
            "conta": "508", "tipo": "ENTRADAS", "descricao": "Estoque",
            "acumuladores": "123", "detalhes_fiscais": [{"codigo":"123","descricao":"Compras"}],
            "fiscal": 10000.0, "contabil":8000.0,
            "total_conta":8000.0, "diferenca":-2000.0,
            "extras": 0, "sem_evidencia":0, "situacao":"REVISAR",
        }]
    }


def enabled(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GROQ_ZDR_CONFIRMED", "1")


def test_groq_nao_chama_api_sem_privacidade_e_plano_confirmados(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    called = []
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen",
                        lambda *_args, **_kw: called.append(1))
    assert not groq_fiscal.is_enabled()
    assert TestClient(app).get("/api/v1/conferencia-fiscal/ia/status").json()["configurado"] is False
    with pytest.raises(HTTPException) as exc:
        fiscal_ai.explain(example_report())
    assert exc.value.status_code == 503
    assert called == []


def test_groq_produz_parecer_realmente_validado_sem_alterar_valores(monkeypatch):
    enabled(monkeypatch)
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n):
            return json.dumps({"choices":[{
                "finish_reason":"stop",
                "message":{"content":json.dumps({"analises":[{
                    "grupo":"G1",
                    "explicacao":"Diferença na conta 508 evidenciada em L1; causa não confirmada.",
                    "verificar":"1. Conferir notas; 2. Revisar razão e acumulador 123.",
                    "evidencias":["L1"]
                }]})}
            }]}).encode()
    def mock(req, timeout):
        data = json.loads(req.data)
        requests.append(data)
        assert req.full_url == "https://api.groq.com/openai/v1/chat/completions"
        assert req.get_header("Authorization") == "Bearer synthetic-test-key"
        assert timeout == 35
        assert data["model"] == "openai/gpt-oss-120b"
        assert data["response_format"]["json_schema"]["strict"] is True
        assert data["response_format"]["json_schema"]["schema"]["properties"]["analises"]["items"]["additionalProperties"] is False
        assert data["reasoning_effort"] == "low"
        assert "R$ 10.000,00" in data["messages"][1]["content"]
        assert "123.456.789-01" not in data["messages"][1]["content"]
        assert "usuario@teste.com" not in data["messages"][1]["content"]
        return Response()
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", mock)
    result = fiscal_ai.explain(example_report())
    assert len(requests) == 1
    assert result["provedor"] == "groq"
    assert result["gratuito"] is True
    assert result["fallback_usado"] is False
    assert result["analises"][0]["valores"]["fiscal"] == 10000
    assert result["analises"][0]["valores"]["contabil"] == 8000
    assert result["analises"][0]["evidencias"][0]["referencia"] == "L1"
    status = TestClient(app).get("/api/v1/conferencia-fiscal/ia/status").json()
    assert status["provedor"] == "groq"
    assert status["configurado"] is True


def test_groq_rejeita_lancamento_inexistente_no_texto(monkeypatch):
    enabled(monkeypatch)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n):
            return json.dumps({"choices":[{
                "finish_reason":"stop",
                "message":{"content":json.dumps({"analises":[{
                    "grupo":"G1",
                    "explicacao":"O lançamento L999 explica a diferença.",
                    "verificar":"1. Conferir",
                    "evidencias":[]
                }]})}
            }]}).encode()
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(HTTPException) as exc:
        fiscal_ai.explain(example_report())
    assert exc.value.status_code == 502


def test_groq_limite_429_faz_fallback_para_gemini_sem_perder_valores(monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY","test-gemini")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED","1")
    def refused(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "rate", {},
            io.BytesIO(b'{"error":{"message":"private client document"}}'))
    monkeypatch.setattr(groq_fiscal.urllib.request,"urlopen", refused)
    monkeypatch.setattr(fiscal_ai, "_gemini_completion", lambda *args, **kwargs: (
        {"analises":[{"grupo":"G1", "explicacao":"Conferir diferença documental.",
                     "verificar":"1. Compare o Razão.", "evidencias":[]}]}, "gemini-3.1-flash-lite"))
    result=fiscal_ai.explain(example_report())
    assert result["provedor"] == "gemini"
    assert result["fallback_usado"] is True
    assert result["analises"][0]["valores"]["diferenca"] == -2000.0


def test_groq_sem_confirmacao_nao_substitui_openrouter(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY","synthetic-test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY","test-openrouter")
    monkeypatch.setenv("RAZYNC_AI_PRIMARY","groq")
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("Groq desabilitada não faz request"))
    monkeypatch.setattr(fiscal_ai, "_openrouter_completion", lambda *args: (
        {"analises":[{"grupo":"G1", "explicacao":"Conferir fiscal com contábil.",
                     "verificar":"Conferir lançamentos", "evidencias":[]}]}, "openrouter/free"))
    result=fiscal_ai.explain(example_report())
    assert result["provedor"] == "openrouter"

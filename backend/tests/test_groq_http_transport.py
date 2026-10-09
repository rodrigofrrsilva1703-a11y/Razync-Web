"""Segurança e interoperabilidade da integração oficial com a API Groq."""
import io
import json
import urllib.error

import pytest
from fastapi import HTTPException
from app import groq_fiscal


@pytest.fixture(autouse=True)
def free_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key-not-real")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GROQ_ZDR_CONFIRMED", "1")


def sample():
    context = {"grupos": [{
        "grupo": "G1", "situacao": "REVISAR", "resumo": {},
        "valores_brl": {"fiscal": "R$ 10.000,00"},
        "cobertura": {"existentes": 0}, "lancamentos": [],
    }]}
    return {"contents": [{"parts": [{"text": json.dumps(context)}]}]}


def test_groq_http_envia_identificacao_de_cliente_sem_enviar_a_chave_no_corpo(monkeypatch):
    def fake(req, timeout):
        assert timeout == 35
        assert req.get_header("User-agent") == "Razync-Web/1.0"
        assert req.get_header("Accept") == "application/json"
        assert req.get_header("Authorization") == "Bearer fake-key-not-real"
        assert "fake-key-not-real" not in req.data.decode("utf-8")
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, *_):
                return json.dumps({"choices": [{
                    "finish_reason": "stop",
                    "message": {"content": json.dumps({"analises": [{
                        "grupo": "G1", "explicacao": "Exemplo de teste.",
                        "verificar": "Conferir.", "evidencias": []
                    }]})}
                }]}).encode()
        return Response()

    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", fake)
    result, model = groq_fiscal.complete(sample(), "fake-key-not-real", "openai/gpt-oss-120b")
    assert model == "openai/gpt-oss-120b"
    assert result["analises"][0]["grupo"] == "G1"


def test_groq_resposta_html_403_e_identificada_sem_vazar_conteudo(monkeypatch, caplog):
    def fake(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", {"Content-Type": "text/html"},
            io.BytesIO(b"<html>error code: 1010 PRIVATE-INFORMATION-NOT-FOR-LOGS</html>")
        )
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", fake)
    with pytest.raises(HTTPException) as exc:
        groq_fiscal.complete(sample(), "fake-key-not-real", "openai/gpt-oss-120b")
    assert exc.value.status_code == 403
    assert "proteção" in exc.value.detail
    assert "bloqueio_http_cliente_1010" in caplog.text
    assert "PRIVATE-INFORMATION-NOT-FOR-LOGS" not in caplog.text
    assert "PRIVATE-INFORMATION-NOT-FOR-LOGS" not in exc.value.detail


def test_groq_json_403_preserva_classificacao_de_permissoes(monkeypatch):
    def fake(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", {"Content-Type": "application/json"},
            io.BytesIO(json.dumps({"error": {
                "code": "model_permission_blocked_org",
                "message": "SECRET-DO-NOT-LOG"
            }}).encode())
        )
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", fake)
    with pytest.raises(HTTPException) as exc:
        groq_fiscal.complete(sample(), "fake-key-not-real", "openai/gpt-oss-120b")
    assert exc.value.status_code == 403
    assert "organização" in exc.value.detail
    assert "SECRET-DO-NOT-LOG" not in exc.value.detail

"""Regressões para provedores gratuitos — chamadas externas simuladas."""
import io
import json
import logging
import urllib.error

import pytest
from fastapi import HTTPException
from app import fiscal_ai, groq_fiscal


def report():
    return {
        "periodo_fiscal": {"inicio": "2026-08-01", "fim": "2026-08-31"},
        "periodo_razao": {"inicio": "2026-08-01", "fim": "2026-08-31"},
        "contas": [{
            "conta": "508", "tipo": "ENTRADAS", "descricao": "Compras",
            "fiscal": 1500, "contabil": 1200, "total_conta": 1200,
            "diferenca": -300, "situacao": "REVISAR", "detalhes_fiscais": [
                {"codigo": "125", "descricao": "Compras", "valor": 1500}
            ],
        }],
        "lancamentos": [{
            "conta": "508", "data": "2026-08-04",
            "historico": "Compra NF 100", "debito": 1200, "credito": 0,
        }],
    }


class StubResponse:
    def __init__(self, answer):
        self.answer = answer
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def read(self, size):
        return json.dumps(self.answer).encode()


def valid_choice(model="apodex/apodex-1.1-mini:free"):
    return {
        "model": model,
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({"analises": [{
                "grupo": "G1", "explicacao": "Revisar os documentos do acumulador.",
                "verificar": "1. Confira o Razão e as notas.", "evidencias": [],
            }]})},
        }],
    }


def test_openrouter_choices_vazio_tenta_proximo_modelo_gratuito(monkeypatch, caplog):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-or-key")
    monkeypatch.setenv("OPENROUTER_MODELS",
                       "dots-studio/dots-3-note-preview:free,apodex/apodex-1.1-mini:free")
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.setattr(fiscal_ai, "model_cooldowns", {})
    monkeypatch.setattr(fiscal_ai, "_groq_enabled", lambda: False)
    seen = []
    def fake(req, timeout):
        body = json.loads(req.data)
        seen.append(body)
        assert body["provider"]["max_price"] == {"prompt": 0, "completion": 0}
        assert body["provider"]["data_collection"] == "deny"
        assert body["model"].endswith(":free")
        assert "synthetic-or-key" not in req.data.decode()
        return StubResponse({"choices": []} if len(seen) == 1 else valid_choice())
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", fake)
    with caplog.at_level(logging.WARNING):
        answer = fiscal_ai.explain(report(), only_provider="openrouter")
    assert [x["model"] for x in seen] == [
        "dots-studio/dots-3-note-preview:free",
        "apodex/apodex-1.1-mini:free",
    ]
    assert answer["provedor"] == "openrouter"
    assert answer["analises"][0]["conta"] == "508"
    assert "category=empty_content" in caplog.text
    assert "synthetic-or-key" not in caplog.text


def test_openrouter_choices_vazio_duas_vezes_falha_sem_inventar_parecer(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-or-key")
    monkeypatch.setenv("OPENROUTER_MODELS", "openrouter/free")
    monkeypatch.setenv("OPENROUTER_ROUTER_FIRST", "1")
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.setattr(fiscal_ai, "_groq_enabled", lambda: False)
    seen = []
    def fake(req, timeout):
        seen.append(1)
        assert json.loads(req.data)["provider"]["max_price"] == {"prompt":0, "completion":0}
        return StubResponse({"choices": []})
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", fake)
    with pytest.raises(HTTPException) as err:
        fiscal_ai.explain(report(), only_provider="openrouter")
    assert err.value.status_code == 502
    assert len(seen) == 2


def groq_payload():
    return {"contents": [{"parts": [{"text": json.dumps({"grupos": [{
        "grupo": "G1", "lancamentos": [], "resumo": {},
        "valores_brl": {"fiscal": "R$ 100,00"}, "cobertura": {},
    }]})}]}]}


def test_groq_400_reexecuta_json_mode_com_validador_integral(monkeypatch, caplog):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-groq-key")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GROQ_ZDR_CONFIRMED", "1")
    seen = []
    def fake(req, timeout):
        body = json.loads(req.data)
        seen.append(body)
        assert body["model"] == "openai/gpt-oss-20b"
        assert "synthetic-groq-key" not in req.data.decode()
        if len(seen) == 1:
            assert body["response_format"]["json_schema"]["strict"] is True
            raise urllib.error.HTTPError(req.full_url, 400, "invalid format", {},
                io.BytesIO(b'{"error":{"message":"PRIVATE-CUSTOMER-DATA"}}'))
        assert body["response_format"] == {"type":"json_object"}
        assert body["reasoning_format"] == "hidden"
        return StubResponse(valid_choice("openai/gpt-oss-20b"))
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", fake)
    with caplog.at_level(logging.WARNING):
        answer, model = groq_fiscal.complete(groq_payload(), "synthetic-groq-key",
                                             "openai/gpt-oss-20b")
    assert model == "openai/gpt-oss-20b"
    assert answer["analises"][0]["grupo"] == "G1"
    assert len(seen) == 2
    assert "PRIVATE-CUSTOMER-DATA" not in caplog.text


def test_groq_400_duas_vezes_falha_sem_mostrar_dados(monkeypatch, caplog):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-groq-key")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GROQ_ZDR_CONFIRMED", "1")
    count = []
    def fake(req, timeout):
        count.append(1)
        raise urllib.error.HTTPError(req.full_url, 400, "fail", {},
            io.BytesIO(b'{"error":{"message":"SENSITIVE-CUSTOMER-NOTE"}}'))
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", fake)
    with pytest.raises(HTTPException) as err:
        groq_fiscal.complete(groq_payload(), "synthetic-groq-key", "openai/gpt-oss-20b")
    assert err.value.status_code == 502
    assert len(count) == 2
    assert "SENSITIVE-CUSTOMER-NOTE" not in caplog.text
    assert "SENSITIVE-CUSTOMER-NOTE" not in err.value.detail


def test_gemini_sucesso_registrado_sem_dados_de_clientes(monkeypatch, caplog):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("RAZYNC_AI_LEGACY_GEMINI", raising=False)
    monkeypatch.setenv("RAZYNC_AI_PRIMARY", "gemini")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-key")
    monkeypatch.setenv("GEMINI_FREE_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setattr(fiscal_ai, "_groq_enabled", lambda: False)
    monkeypatch.setattr(fiscal_ai, "_gemini_completion", lambda *_a, **_k: (
        {"analises": [{"grupo": "G1", "explicacao": "Conferir documento.",
                       "verificar": "1. Consulte o Razão.", "evidencias": []}]},
        "gemini-3.1-flash-lite",
    ))
    with caplog.at_level(logging.INFO, logger="app.fiscal_ai"):
        result = fiscal_ai.explain(report(), only_provider="gemini")
    assert result["provedor"] == "gemini"
    assert "fiscal_ia_gemini_success" in caplog.text
    assert "synthetic-gemini-key" not in caplog.text
    assert "Compra NF 100" not in caplog.text


def test_gemini_erro_registrado_sem_conteudo_ou_chave(monkeypatch, caplog):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-key")
    monkeypatch.setenv("GEMINI_FREE_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setattr(fiscal_ai, "_groq_enabled", lambda: False)
    monkeypatch.setattr(fiscal_ai, "_gemini_completion",
        lambda *_a, **_k: (_ for _ in ()).throw(HTTPException(429, "Sensitive content")))
    with pytest.raises(HTTPException) as err:
        fiscal_ai.explain(report(), only_provider="gemini")
    assert err.value.status_code == 429
    assert "fiscal_ia_gemini_failure status=429" in caplog.text
    assert "synthetic-gemini-key" not in caplog.text
    assert "Sensitive content" not in caplog.text

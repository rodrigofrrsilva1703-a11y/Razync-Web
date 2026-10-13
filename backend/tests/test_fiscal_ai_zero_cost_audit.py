import json
import pytest
from fastapi import HTTPException
from app import fiscal_ai
from app.fiscal_ai_audit import audit_analysis


def _analysis(**overrides):
    value = {
        "conta": "501",
        "valores": {"fiscal": 100.00, "contabil": 80.00, "diferenca": -20.00},
        "explicacao": "A diferença encontrada foi R$ 20,00.",
        "verificar": "Conferir o lançamento L1 no Razão.",
        "evidencias": [{"referencia": "L1", "debito": 80.00, "credito": 0}],
    }
    value.update(overrides)
    return value


def test_auditoria_conciliacao_com_evidencia_nao_inventa_conclusao():
    result = audit_analysis(_analysis())
    assert result["situacao"] == "conferencia_assistida"
    assert result["valores_sem_comprovacao"] == 0
    assert result["lancamentos_citados"] == 1
    assert "revisão" in result["aviso"]


def test_auditoria_indica_valor_nao_confirmado_e_falta_de_evidencia():
    result = audit_analysis(_analysis(explicacao="Diferença de R$ 999,99.", evidencias=[]))
    assert result["situacao"] == "revisao_necessaria"
    assert result["valores_sem_comprovacao"] == 1
    assert len(result["alertas"]) == 2


def test_auditoria_nao_altera_dados_original():
    source = _analysis()
    before = json.dumps(source, sort_keys=True)
    audit_analysis(source)
    assert json.dumps(source, sort_keys=True) == before


def test_legado_pago_nunca_habilita_gemini(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("RAZYNC_AI_LEGACY_GEMINI", "1")
    monkeypatch.setattr(fiscal_ai, "_groq_enabled", lambda: False)
    result = fiscal_ai.status()
    assert result["configurado"] is False
    assert result["modo_custo_zero_obrigatorio"] is True
    assert result["modelo_pago_permitido"] is False


def test_gemini_sem_confirmacao_bloqueia_requisicao(monkeypatch):
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("Não deve enviar ao provedor"))
    with pytest.raises(HTTPException) as error:
        fiscal_ai._gemini_send({"contents": []}, "chave-falsa", "gemini-3.1-flash-lite")
    assert error.value.status_code == 503


def test_gemini_bloqueia_ferramentas_potencialmente_pagas(monkeypatch):
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "1")
    with pytest.raises(HTTPException) as error:
        fiscal_ai._gemini_send({"contents": [], "tools": [{"googleSearch": {}}]},
                               "chave-falsa", "gemini-3.1-flash-lite")
    assert error.value.status_code == 503


def test_redacao_protege_cpf_cnpj_email_sem_truncar_historico():
    payload = {"contents": [{"parts": [{"text": json.dumps({
        "grupos": [{"resumo": {"descricao": "JOAO CPF 123.456.789-09"},
                    "lancamentos": [{"historico": "NF de pessoa 12.345.678/0001-90 contato x@y.com",
                                     "debito": 100, "credito": 0, "referencia": "L1"}]}]
    })}]}]}
    sent = fiscal_ai._compact_transport(payload)
    raw = sent["contents"][0]["parts"][0]["text"]
    assert "123.456.789-09" not in raw
    assert "12.345.678/0001-90" not in raw
    assert "x@y.com" not in raw
    assert "L1" in raw
    assert "100" in raw
    assert payload["contents"][0]["parts"][0]["text"] != raw

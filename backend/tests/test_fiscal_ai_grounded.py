import copy
from app.fiscal_ai_audit import structured_analysis, audit_analysis
from app import fiscal_ai_sessions


def test_model_claims_never_become_verified_facts():
    item = {"valores": {"fiscal": 100, "contabil": 80, "total_conta": 90, "diferenca": -20},
            "explicacao": "Fatos: Houve duplicidade.\n\nDiferença: -20.\n\nHipóteses: Pode ser corte de período (L1).\n\nLimitações: Conferir notas."}
    original = copy.deepcopy(item)
    result = structured_analysis(item, [{}] * 12, sent=10, shortened=True)
    assert all("duplicidade" not in str(fact) for fact in result["fatos"])
    assert result["fatos"][-1]["valor"] == -20
    assert result["hipoteses"] == "Pode ser corte de período (L1)."
    assert result["cobertura"] == {"disponiveis": 12, "enviados": 10, "parcial": True, "historicos_abreviados": True}
    assert item == original


def test_full_context_and_documentary_limits():
    result = structured_analysis({"explicacao": "Narrativa sem rótulos."}, [{}], documentary=True)
    assert result["cobertura"]["parcial"] is False
    assert result["cobertura"]["enviados"] == 1
    assert "não identifica" in result["hipoteses"]
    assert result["interpretacao"] == "Narrativa sem rótulos."
    assert not any("não contém documentos" in x for x in result["informacoes_faltantes"])


def test_unknown_text_reference_is_flagged_locally():
    result = audit_analysis({"explicacao": "Conferir L999 e L1.", "evidencias": [{"referencia": "L1"}]})
    assert result["referencias_sem_evidencia"] == ["L999"]
    assert result["situacao"] == "revisao_necessaria"


def test_prompt_version_invalidates_cache_without_deleting_reports(monkeypatch):
    report = {"contas": []}
    before = fiscal_ai_sessions._cache_digest(report)
    assert fiscal_ai_sessions._cache_digest(report) == before
    monkeypatch.setattr(fiscal_ai_sessions, "ANALYSIS_VERSION", "future")
    assert fiscal_ai_sessions._cache_digest(report) != before
    assert report == {"contas": []}


import pytest

@pytest.mark.parametrize("text", [
    "## Fatos\nResumo.\n## Hipóteses\nPode ser período (L1).\n## Limitações\nConferir notas.",
    "1. **Fatos:** Resumo.\n2. **Possíveis causas:** Pode ser período (L1).\n3. **Informações faltantes:** Conferir notas.",
    "Fatos: Resumo. Hipoteses: Pode ser período (L1). Limitacoes: Conferir notas.",
    "**Fatos**: Resumo. **Causas prováveis**: Pode ser período (L1). **Limitações dos dados**: Conferir notas.",
])
def test_provider_heading_variants_have_same_layout(text):
    result = structured_analysis({"explicacao": text}, [])
    assert result["hipoteses"] == "Pode ser período (L1)."
    assert result["interpretacao"] == ""
    assert result["informacoes_faltantes"][-1] == "Limitação indicada pela IA: Conferir notas."

@pytest.mark.parametrize("provider,model", [("groq", "openai/gpt-oss-120b"), ("gemini", "gemini-2.5-flash-lite"), ("openrouter", "openrouter/free")])
def test_provider_identity_survives_common_validation(provider, model):
    from app import fiscal_ai
    source = {"contas": [{"conta": "1", "tipo": "ENTRADAS", "fiscal": 100, "contabil": 80,
                          "total_conta": 80, "diferenca": -20}], "lancamentos": []}
    raw = {"analises": [{"grupo": "G1", "explicacao": "Possíveis causas: Conferir período.",
                         "verificar": "1. Conferir documentos.", "evidencias": []}]}
    result = fiscal_ai._validar_resposta_ia(raw, source, {"G1": {"conta": "1", "tipo": "ENTRADAS"}}, {},
                                          provider=provider, model=model)[0]
    assert result["provedor"] == provider
    assert result["modelo_usado"] == model
    assert result["parecer"]["hipoteses"] == "Conferir período."

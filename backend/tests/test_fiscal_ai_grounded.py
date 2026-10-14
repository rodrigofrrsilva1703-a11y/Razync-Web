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


def test_singular_limitation_stays_separate_from_hypothesis():
    result = structured_analysis({"explicacao": "Hipótese: Pode ser período. Limitação: Faltam documentos individuais."}, [])
    assert result["hipoteses"] == "Pode ser período."
    assert result["informacoes_faltantes"][-1] == "Limitação indicada pela IA: Faltam documentos individuais."


def test_assertive_missing_posting_claim_triggers_local_review():
    result = audit_analysis({"explicacao": "Hipóteses: os valores não foram lançados. Limitação: confirmar a omissão.", "evidencias": []})
    assert any("não comprova essa causa" in text for text in result["alertas"])


def test_explains_equal_totals_without_treating_all_ledger_as_fiscal():
    from app.fiscal_ai_audit import comparison_reading
    item = {"conta":"354", "tipo":"ENTRADAS", "acumuladores":"1252",
        "valores":{"fiscal":1610.56, "contabil":1610.56, "total_conta":5202.19, "diferenca":0}}
    rows = [{"_referencia_ia":f"L{i}", "data":"17/08/2026", "historico":history,
        "debito":amount, "credito":0, "natureza":"DÉBITO", "classificacao":classification}
        for i,amount,history,classification in [
        (5,1831.06,"Pago: energia", "ALERTA - NÃO FISCAL"),
        (6,150.01,"Pago: energia", "ALERTA - NÃO FISCAL"),
        (7,800,"SERVIÇOS DE TERCEIROS CF NF 1", "FISCAL PROVÁVEL"),
        (8,810.56,"SERVIÇOS DE TERCEIROS CF NF 2", "FISCAL PROVÁVEL"),
        (9,148.89,"Pago: energia", "ALERTA - NÃO FISCAL"),
        (10,1461.67,"Pago: energia", "ALERTA - NÃO FISCAL")]]
    original = copy.deepcopy(rows)
    result = comparison_reading(item, rows)
    text = " ".join(result["explicacoes"])
    assert "R$ 5.202,19" in text and "R$ 1.610,56" in text and "R$ 3.591,63" in text
    assert "2 foram considerados" in text and "4 ficaram fora" in text
    assert "pagamento pode liquidar uma despesa já registrada" in text
    assert len(result["excluidos"]) == 4
    assert result["excluidos"][0]["referencia"] == "L5"
    assert result["excluidos"][0]["motivo"] == "Histórico de pagamento/recebimento/baixa"
    assert all(step["objetivo"] for step in result["orientacoes"])
    assert "1252" in result["orientacoes"][1]["acao"]
    assert rows == original


def test_comparison_respects_side_signs_and_unproven_value_closure():
    from app.fiscal_ai_audit import comparison_reading
    item = {"conta":"408", "tipo":"SAÍDAS", "valores":{"fiscal":80, "contabil":80, "total_conta":80}}
    rows = [{"credito":100,"debito":0,"natureza":"CRÉDITO","classificacao":"FISCAL PROVÁVEL"},
            {"credito":-20,"debito":0,"natureza":"ESTORNO/REDUTOR (CRÉDITO)","classificacao":"FECHAMENTO POR VALOR - VALIDAR"},
            {"debito":999,"credito":0,"natureza":"DÉBITO","classificacao":"ALERTA - NÃO FISCAL"}]
    text = " ".join(comparison_reading(item, rows)["explicacoes"])
    assert "usa os créditos das saídas" in text
    assert "Dos 2 movimentos" in text and "1 entraram apenas por fechamento" in text
    assert "mesmo sem indício fiscal suficiente" in text
    assert not comparison_reading({"valores":{"diferenca":-20}}, rows)["explicacoes"]


def test_cached_analysis_gains_explanation_without_an_ai_call(monkeypatch):
    monkeypatch.setattr(fiscal_ai_sessions.fiscal_ai,"explain",lambda *a,**k: (_ for _ in ()).throw(AssertionError("No model call")))
    item = {"conta":"366","tipo":"ENTRADAS","explicacao":"Hipóteses: Causa indeterminada.",
        "valores":{"fiscal":100,"contabil":80,"total_conta":80},"provedor":"groq","evidencias":[],"verificar":"Conferir nota."}
    report = {"contas":[item],"lancamentos":[{"conta":"366","natureza":"DÉBITO","debito":80,"credito":0,"classificacao":"FISCAL PROVÁVEL"}]}
    refreshed = fiscal_ai_sessions._refresh_cached_review({"analises":[item]},report)
    text = " ".join(refreshed["analises"][0]["parecer"]["leitura_comparacao"]["explicacoes"])
    assert "R$ 20,00 abaixo" in text
    assert "Todos os movimentos" in text
    assert "leitura_comparacao" not in item

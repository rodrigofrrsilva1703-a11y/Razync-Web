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
    assert "não separou" in result["hipoteses"]
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

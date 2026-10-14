import copy
import json
from app.fiscal_ai_strategy import REVIEW_PROMPT, output_budget
from app import fiscal_ai, groq_fiscal


def test_adaptive_plan_shared_by_all_free_providers():
    assert len(REVIEW_PROMPT.split()) < 500
    assert "máximo 220" in REVIEW_PROMPT
    assert "máximo 120" in REVIEW_PROMPT
    assert "não preencha com hipóteses genéricas" in REVIEW_PROMPT
    assert "2 ou 3 passos" in REVIEW_PROMPT
    assert "sem introdução nem repetição dos totais" in REVIEW_PROMPT
    assert "a causa está indeterminada" in REVIEW_PROMPT
    assert "não no Razão" in REVIEW_PROMPT
    assert output_budget(2) == 2700
    assert output_budget([{"situacao":"REVISAR"}, {"situacao":"CONFERE COM ALERTAS"}]) == 2200
    assert output_budget([{"situacao":"CONFERE"}]) < output_budget([{"situacao":"CONFERE COM ALERTAS"}]) < output_budget([{"situacao":"REVISAR"}])
    assert output_budget(100) == 4096
    assert groq_fiscal.REVIEW_PROMPT == fiscal_ai.REVIEW_PROMPT == REVIEW_PROMPT


def test_compaction_preserves_every_record_and_full_history():
    history = "Compra de mercadoria NF 123 " + "Histórico completo. " * 100
    context = {"grupos": [{"grupo": "G1", "resumo": {"conta": "1", "tipo": "ENTRADAS", "fiscal": 100,
        "contabil": 80, "total_conta": 80, "diferenca": -20, "acumuladores": "12"},
        "valores_brl": {"fiscal": "R$ 100,00", "contabil": "R$ 80,00", "total_conta": "R$ 80,00", "diferenca": "-R$ 20,00"},
        "lancamentos": [{"referencia": f"L{i}", "conta": "1", "historico": history, "data": "2026-08-01",
        "contrapartida": "9", "debito": 80, "credito": 0, "debito_brl": "R$ 80,00", "credito_brl": "R$ 0,00"} for i in range(1,31)]}]}
    payload = {"contents": [{"parts": [{"text": json.dumps(context)}]}]}
    original = copy.deepcopy(payload)
    reduced = json.loads(fiscal_ai._compact_transport(payload)["contents"][0]["parts"][0]["text"])
    group = reduced["grupos"][0]
    assert len(group["lancamentos"]) == 30
    assert all(row["historico"] == history for row in group["lancamentos"])
    assert group["valores_brl"] == context["grupos"][0]["valores_brl"]
    assert "fiscal" not in group["resumo"]
    assert group["resumo"]["acumuladores"] == "12"
    assert group["lancamentos"][0]["contrapartida"] == "9"
    assert "debito" not in group["lancamentos"][0]
    assert payload == original
    assert len(json.dumps(reduced)) < len(json.dumps(context))


def test_local_cache_review_blocks_contradiction_without_new_ai_request(monkeypatch):
    from app import fiscal_ai_sessions
    monkeypatch.setattr(fiscal_ai, 'explain', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No AI call expected')))
    item = {'conta':'1','provedor':'openrouter','modelo_usado':'openrouter/free',
        'valores':{'fiscal':100,'contabil':80,'diferenca':-20},
        'explicacao':'Hipóteses: L1 não foi devidamente contabilizado no Razão. Limitação: Conferir documento.',
        'verificar':'1. Compare NF.\n2. Confira o período.',
        'evidencias':[{'referencia':'L1','conta':'1','debito':80,'credito':0}]}
    cached = {'analises':[item], 'provedor':'openrouter'}
    original = copy.deepcopy(cached)
    updated = fiscal_ai_sessions._refresh_cached_review(cached, {'lancamentos':[{'conta':'1'}]})['analises'][0]
    assert 'já constam no Razão' in updated['parecer']['hipoteses']
    assert any('já constam no Razão' in x for x in updated['auditoria']['alertas'])
    assert updated['explicacao'] == item['explicacao']
    assert updated['provedor'] == 'openrouter'
    assert cached == original


def test_detailed_reading_survives_validation_and_local_envelope():
    report = {"contas":[{"conta":"1", "tipo":"ENTRADAS", "situacao":"REVISAR",
        "fiscal":100, "contabil":80, "total_conta":80, "diferenca":-20}],
        "lancamentos":[{"conta":"1", "data":"2026-08-01", "historico":"Compra NF 123", "debito":80, "credito":0}]}
    record = {"conta":"1", "referencia":"L1", "data":"2026-08-01", "historico":"Compra NF 123", "debito":80, "credito":0}
    answer = {"analises":[{"grupo":"G1", "explicacao":
        "Fatos: L1 registra compra NF 123 em 01/08/2026.\nHipóteses: A causa está indeterminada; pode haver diferença de período, a confirmar pelos documentos.\nLimitações: Falta o detalhamento fiscal por nota.",
        "verificar":"1. Localize NF 123 no fiscal e compare o período com L1.\n2. Compare os documentos do acumulador com a conta para identificar a origem da diferença.",
        "evidencias":["L1"]}]}
    result = fiscal_ai._validar_resposta_ia(answer, report, {"G1":{"conta":"1", "tipo":"ENTRADAS"}}, {"L1":record})[0]
    assert result["parecer"]["observacoes"] == "L1 registra compra NF 123 em 01/08/2026."
    assert "indeterminada" in result["parecer"]["hipoteses"]
    assert "detalhamento fiscal" in " ".join(result["parecer"]["informacoes_faltantes"])
    assert result["valores"]["diferenca"] == -20
    assert result["evidencias"][0]["referencia"] == "L1"

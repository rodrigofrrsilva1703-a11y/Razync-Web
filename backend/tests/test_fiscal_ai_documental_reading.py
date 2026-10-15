"""Garantia de pareceres documentais concretos, sem mudar a conferência."""
from copy import deepcopy

from app.fiscal_ai_audit import structured_analysis
from app.fiscal_ai_documental_reading import documentary_reading


def sample_item(kind="CONTA_DIFERENTE"):
    return {
        "conta": "366", "tipo": "ENTRADAS", "acumuladores": "3082",
        "valores": {"fiscal": 1240, "contabil": 1230, "total_conta": 1240, "diferenca": -10},
        "explicacao": "Hipóteses: A causa ainda não está comprovada pelas evidências desta conta. "
                      "Limitações: confira os documentos e os vínculos apresentados pelo sistema antes de propor ajustes.",
        "verificar": "1. Confira a nota.\n2. Compare o Razão.",
        "parecer": {"comparacoes_documentais": [
            {"referencia": "E-21", "situacao": kind, "nota": "90702", "data": "03/08/2026",
             "acumulador": "3082", "valor_brl": "R$ 760,49", "conta_razao_candidato": "377",
             "valor_razao_candidato_brl": "R$ 760,49", "diferenca_candidato_brl": "R$ 0,00",
             "vinculo_confirmado": False},
            {"referencia": "E-30", "situacao": "VALOR_DIFERENTE", "nota": "93218",
             "acumulador": "3082", "data": "09/08/2026", "valor_brl": "R$ 275,00",
             "valor_razao_candidato_brl": "R$ 270,00",
             "diferenca_candidato_brl": "-R$ 5,00", "vinculo_confirmado": False},
        ]},
        "resumo_documental": {
            "documentos_lidos": 1240, "conciliados": 1229,
            "documentos_pendentes": 11, "movimentos_pendentes": 18,
            "situacoes": {
                "CONCILIADO": 1229, "CONTA_DIFERENTE": 7, "VALOR_DIFERENTE": 4,
            },
            "composicao": {"itens": [
                {"descricao": "Diferenças nos vínculos encontrados ou em análise", "valor": 760.49},
                {"descricao": "Movimentos separados na conferência inicial", "valor": -9.99},
            ]},
        },
        "cobertura_documental": {
            "documentos_enviados": 11, "documentos_pendentes": 11,
            "lancamentos_enviados": 18, "lancamentos_pendentes": 18, "amostra": False,
        }
    }


def test_1240_linhas_geram_diagnostico_por_tipo_e_nao_resumo_repetitivo():
    item = sample_item()
    snapshot = deepcopy(item)
    result = structured_analysis(item, [], documentary=True)
    reading = result["leitura_comparacao"]
    assert item == snapshot
    assert reading["documental_especifico"] is True
    assert "11 documento(s) fiscais e 18 movimento(s)" in reading["resultado"]
    assert "valor divergente (4)" in reading["resultado"].lower()
    assert not any("IA recebeu" in message or "O sistema cruzou" in message
                   for message in reading["observacoes"])
    assert len(reading["destaques"]) == 2
    assert reading["destaques"][0]["documento"].startswith("NF 93218")
    assert reading["destaques"][0]["diferenca_candidata"] == "-R$ 5,00"
    assert reading["destaques"][1]["conta_candidata"] == "377"
    assert "E-30" in reading["orientacoes"][0]["acao"]
    assert reading["orientacoes"][0]["objetivo"].startswith("Compare o total")
    assert reading["impactos"][0]["valor"] == "R$ 760,49"
    assert reading["impactos"][1]["valor"] == "-R$ 9,99"
    assert reading["resumo_conciliacao"]["conciliados"] == 1229


def test_mudanca_de_evidencias_muda_diagnostico_e_proximos_passos():
    left = sample_item()
    result_left = structured_analysis(left, [], documentary=True)["leitura_comparacao"]
    right = sample_item("DATA_DIFERENTE")
    right["resumo_documental"]["situacoes"] = {
        "CONCILIADO": 1229, "DATA_DIFERENTE": 11,
    }
    right["parecer"]["comparacoes_documentais"] = [
        d for d in right["parecer"]["comparacoes_documentais"]
        if d["situacao"] == "DATA_DIFERENTE"
    ]
    result_right = structured_analysis(right, [], documentary=True)["leitura_comparacao"]
    assert "data ou competência diferente" in result_right["resultado"].lower()
    assert "data de emissão" in result_right["orientacoes"][0]["objetivo"]
    assert result_left["resultado"] != result_right["resultado"]
    assert result_left["orientacoes"][0] != result_right["orientacoes"][0]


def test_sinaliza_amostra_e_nao_inventa_causa():
    item = sample_item()
    item["cobertura_documental"]["amostra"] = True
    item["cobertura_documental"]["documentos_enviados"] = 2
    r = structured_analysis(item, [], documentary=True)["leitura_comparacao"]
    assert "amostra" in r["criterio"]
    assert r["cobertura_documental"]["documentos_enviados"] == 2
    assert not any("comprovada" in x["tipo"].lower() for x in r["destaques"])
    assert all(x["vinculo_confirmado"] is False for x in r["destaques"])


def test_referencia_real_nao_funde_multiplas_notas():
    item = sample_item("CONTA_DIFERENTE")
    item["parecer"]["comparacoes_documentais"] = [
        item["parecer"]["comparacoes_documentais"][0],
        dict(item["parecer"]["comparacoes_documentais"][0],
             referencia="E-22", nota="99818"),
        dict(item["parecer"]["comparacoes_documentais"][0],
             referencia="E-22", nota="99818"),
    ]
    r = structured_analysis(item, [], documentary=True)["leitura_comparacao"]
    assert [x["referencia"] for x in r["destaques"]] == ["E-21", "E-22"]
    assert len(r["orientacoes"]) >= 1


def test_sem_docs_individuais_mantem_escopo_e_orienta_busca_local():
    item = sample_item()
    item["parecer"]["comparacoes_documentais"] = []
    reading = structured_analysis(item, [], documentary=True)["leitura_comparacao"]
    assert reading["destaques"] == []
    assert any("não há documentos individualizados" in x for x in reading["observacoes"])
    assert "Identifique as notas" in reading["orientacoes"][0]["acao"]


def test_sem_resumo_documental_preserva_leitura_original():
    item = {"conta": "200", "tipo": "ENTRADAS"}
    original = {"resultado": "Sem resumo documental", "orientacoes": []}
    assert documentary_reading(item, [], original) is original

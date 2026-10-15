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
    assert "11 documentos fiscais e 18 movimentos contábeis" in reading["resultado"]
    assert "valor divergente (4)" in reading["resultado"].lower()
    assert not any("IA recebeu" in message or "O sistema cruzou" in message
                   for message in reading["observacoes"])
    assert len(reading["destaques"]) == 2
    assert reading["destaques"][0]["documento"].startswith("NF 93218")
    assert reading["destaques"][0]["diferenca_candidata"] == "-R$ 5,00"
    assert reading["destaques"][1]["conta_candidata"] == "377"
    assert reading["orientacoes"][0]["documentos"][0]["referencia"] == "E-30"
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
    assert "Localize os documentos" in reading["orientacoes"][0]["acao"]


def test_sem_resumo_documental_preserva_leitura_original():
    item = {"conta": "200", "tipo": "ENTRADAS"}
    original = {"resultado": "Sem resumo documental", "orientacoes": []}
    assert documentary_reading(item, [], original) is original


def test_exportacao_excel_traz_notas_prioritarias_sem_texto_generico():
    import io
    from openpyxl import load_workbook
    from app.fiscal_ai import gerar_excel_analise

    item = sample_item()
    item["descricao"] = "Serviços de terceiros"
    item["situacao"] = "REVISAR"
    item["parecer"].update(structured_analysis(item, [], documentary=True))
    workbook = load_workbook(io.BytesIO(gerar_excel_analise({"analises": [item]})))
    explanation = workbook["Análises IA"]["J6"].value
    assert "NF 93218" in explanation
    assert "NF 90702" in explanation
    assert "R$ 760,49" in explanation
    assert "A causa ainda não está comprovada pelas evidências" not in explanation
    assert "E-30" in workbook["Análises IA"]["K6"].value


def test_tres_nfs_do_mesmo_problema_viram_uma_verificacao_com_dados_individuais():
    """Reproduz a estrutura das NFs 9080/11188018/6988 apresentada pelo usuário."""
    item = sample_item()
    item["resumo_documental"]["situacoes"] = {
        "CONCILIADO": 1229, "VALOR_DIFERENTE": 11,
    }
    item["parecer"]["comparacoes_documentais"] = [
        {"referencia": "E-13", "situacao": "VALOR_DIFERENTE", "nota": "9080",
         "acumulador": "1102", "data": "24/09/2026",
         "valor_brl": "R$ 860,00", "valor_razao_candidato_brl": "R$ 850,00",
         "diferenca_candidato_brl": "-R$ 10,00"},
        {"referencia": "E-122", "situacao": "VALOR_DIFERENTE", "nota": "11188018",
         "acumulador": "1403", "data": "19/08/2026",
         "valor_brl": "R$ 1.000,00", "valor_razao_candidato_brl": "R$ 995,00",
         "diferenca_candidato_brl": "-R$ 5,00"},
        {"referencia": "E-129", "situacao": "VALOR_DIFERENTE", "nota": "6988",
         "acumulador": "1403", "data": "26/08/2026",
         "valor_brl": "R$ 700,00", "valor_razao_candidato_brl": "R$ 680,00",
         "diferenca_candidato_brl": "-R$ 20,00"},
    ]
    reading = structured_analysis(item, [], documentary=True)["leitura_comparacao"]
    steps = reading["orientacoes"]
    value_steps = [step for step in steps if step.get("categoria") == "VALOR_DIFERENTE"]
    assert len(value_steps) == 1
    assert value_steps[0]["quantidade"] == 11
    examples = value_steps[0]["documentos"]
    assert [doc["referencia"] for doc in examples] == ["E-13", "E-122", "E-129"]
    assert "NF 9080" in examples[0]["titulo"]
    assert "Fiscal: R$ 860,00" in examples[0]["detalhes"]
    assert "Razão candidato: R$ 850,00" in examples[0]["detalhes"]
    assert "Diferença entre candidatos: -R$ 10,00" in examples[0]["detalhes"]
    assert "NF 11188018" in examples[1]["titulo"]
    assert "NF 6988" in examples[2]["titulo"]
    assert steps[0]["acao"] != steps[-1]["acao"]
    assert value_steps[0]["amostra"] is True


def test_sem_valor_candidato_nao_inventa_parcelas_ou_diferenca():
    item = sample_item()
    item["parecer"]["comparacoes_documentais"] = [
        {"referencia": "E-13", "situacao": "VALOR_DIFERENTE", "nota": "9080",
         "data": "24/09/2026", "acumulador": "1102", "valor_brl": "R$ 860,00"},
        {"referencia": "E-122", "situacao": "VALOR_DIFERENTE", "nota": "11188018",
         "data": "19/08/2026", "acumulador": "1403", "valor_brl": "R$ 1.000,00"},
    ]
    reading = structured_analysis(item, [], documentary=True)["leitura_comparacao"]
    step = next(x for x in reading["orientacoes"] if x.get("categoria") == "VALOR_DIFERENTE")
    assert "não contém o valor" in step["objetivo"]
    assert all("Diferença entre candidatos" not in doc["detalhes"]
               for doc in step["documentos"])
    assert len([x for x in reading["orientacoes"] if x.get("categoria") == "VALOR_DIFERENTE"]) == 1


def test_mesma_nota_duas_referencias_nao_funde_documentos_diferentes():
    item = sample_item()
    original = item["parecer"]["comparacoes_documentais"][0]
    item["parecer"]["comparacoes_documentais"] = [
        original,
        dict(original, referencia="E-22"),
    ]
    instructions = structured_analysis(item, [], documentary=True)["leitura_comparacao"]["orientacoes"]
    group = next(x for x in instructions if x.get("categoria") == "CONTA_DIFERENTE")
    assert len(group["documentos"]) == 2
    assert [x["referencia"] for x in group["documentos"]] == ["E-21", "E-22"]

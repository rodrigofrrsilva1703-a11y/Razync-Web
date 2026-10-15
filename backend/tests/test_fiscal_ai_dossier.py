"""Dossiê contábil: evidências por conta, limites e parecer revisado sem custos extras."""
from copy import deepcopy
import json

from app import fiscal_ai, groq_fiscal
from app.fiscal_ai_dossier import build_dossier
from app.fiscal_ai_audit import structured_analysis
from app.fiscal_ai_strategy import REVIEW_PROMPT


def report():
    return {
        "periodo_fiscal": {"inicio": "01/08/2026", "fim": "31/08/2026"},
        "contas": [
            {"conta": "366", "tipo": "ENTRADAS", "situacao": "REVISAR",
             "acumuladores": "3082", "detalhes_fiscais": [
                 {"codigo": "3082", "descricao": "Serviços", "valor": 2300}],
             "fiscal": 2300, "contabil": 1800, "total_conta": 2100,
             "diferenca": -500, "extras": 1},
            {"conta": "400", "tipo": "SAÍDAS", "situacao": "CONFERE",
             "fiscal": 100, "contabil": 100, "total_conta": 100, "diferenca": 0},
        ],
        "lancamentos": [
            {"conta": "366", "_tipo_ia": "ENTRADAS", "_referencia_ia": "L16",
             "data": "02/08/2026", "historico": "SERVICOS CF NF 90702", "contrapartida": "201",
             "debito": 1800, "credito": 0, "classificacao": "FISCAL PROVÁVEL"},
            {"conta": "366", "_tipo_ia": "ENTRADAS", "_referencia_ia": "L18",
             "data": "16/08/2026", "historico": "Pago: servicos", "contrapartida": "508",
             "debito": 300, "credito": 0, "classificacao": "ALERTA - NÃO FISCAL"},
            {"conta": "400", "_tipo_ia": "SAÍDAS", "_referencia_ia": "L20",
             "data": "05/08/2026", "historico": "VENDA", "contrapartida": "111",
             "debito": 0, "credito": 100, "classificacao": "FISCAL PROVÁVEL"},
        ],
        "documentos_pendentes": {"366:ENTRADAS": [{
            "referencia": "E-9", "situacao": "CONTA_DIFERENTE", "nota": "90702",
            "acumulador": "3082", "conta_razao_candidato": "377",
            "razao_id": "L30", "data": "03/08/2026",
        }]},
        "resumo_documental": {"366:ENTRADAS": {
            "documentos_lidos": 5, "conciliados": 4,
            "documentos_pendentes": 1, "movimentos_pendentes": 2,
            "composicao": {"confere_com_inicial": True, "itens": [
                {"codigo": "fiscal_sem_vinculo", "descricao": "Documento fiscal pendente", "valor": -500},
            ]}
        }},
        "cobertura_documental": {"366:ENTRADAS": {
            "documentos_enviados": 1, "documentos_pendentes": 1,
            "lancamentos_enviados": 2, "lancamentos_pendentes": 2,
            "amostra": False,
        }},
        "avisos": [],
    }


def test_dossie_de_conta_apenas_com_fontes_reais_e_prioridades_especificas():
    source = report()
    original = deepcopy(source)
    data, mapping, references, limits = fiscal_ai.detailed_context(source)
    assert source == original
    assert list(mapping) == ["G1"]
    group = data["grupos"][0]
    dossier = group["dossie_contabil"]
    assert dossier["conta"] == "366"
    assert dossier["tipo"] == "ENTRADAS"
    assert dossier["lado_contabil_comparado"] == "DÉBITO"
    assert dossier["razao"]["indicadores"]["separados_na_comparacao"] == 1
    assert dossier["documentos"]["resumo_do_cruzamento_local"]["conciliados"] == 4
    assert dossier["documentos"]["candidatos_a_verificar"][0]["referencia"] == "E-9"
    assert dossier["documentos"]["candidatos_a_verificar"][0]["conta_razao_candidato"] == "377"
    assert dossier["prioridades_de_investigacao"][0]["origem"] == "documento_pendente"
    assert dossier["prioridades_de_investigacao"][0]["referencia"] == "E-9"
    assert len(group["lancamentos"]) == 2
    assert "L16" in references and "L20" not in references


def test_sem_notas_nao_inventa_ausencia_nem_hipoteses_contabeis():
    source = report()["contas"][0]
    source["detalhes_fiscais"] = []
    row = {"conta": "366", "historico": "SERVICOS NF 90702", "debito": 100}
    dossier = build_dossier(source, [row])
    assert dossier["documentos"]["candidatos_a_verificar"] == []
    assert dossier["prioridades_de_investigacao"][0]["origem"] == "resumo_fiscal"
    assert "não fornece notas individuais" in dossier["limites_das_fontes"][0]
    assert "duplicidade" not in json.dumps(dossier).lower()


def test_lotes_de_groq_preservam_dossie_mas_informam_amostra():
    source = report()
    source["lancamentos"] = [dict(source["lancamentos"][0], _referencia_ia=f"L{i}")
                             for i in range(1, 16)]
    context, _, _, _ = fiscal_ai.detailed_context(source)
    reduced = groq_fiscal._compact_group(context["grupos"][0])
    assert reduced["dossie_contabil"]["conta"] == "366"
    assert reduced["amostra_nao_exaustiva"] is True
    assert len(reduced["lancamentos"]) <= 10
    assert reduced["dossie_contabil"]["razao"]["movimentos_recebidos"] == 15


def test_compact_transport_redige_cnpj_e_preserva_documentos_e_prioridades():
    context, _, _, _ = fiscal_ai.detailed_context(report())
    context["grupos"][0]["lancamentos"][0]["historico"] = "Cliente 12.345.678/0001-90 contato teste@exemplo.com"
    payload = {"contents": [{"parts": [{"text": json.dumps(context, ensure_ascii=False)}]}]}
    reduced = json.loads(fiscal_ai._compact_transport(payload)["contents"][0]["parts"][0]["text"])
    group = reduced["grupos"][0]
    assert "12.345.678/0001-90" not in group["lancamentos"][0]["historico"]
    assert "teste@exemplo.com" not in group["lancamentos"][0]["historico"]
    assert group["dossie_contabil"]["prioridades_de_investigacao"][0]["referencia"] == "E-9"
    assert len(group["lancamentos"]) == 2


def test_resposta_revisada_usa_verificacao_da_nota_em_outra_conta():
    report_data = report()
    context, mapping, refs, _ = fiscal_ai.detailed_context(report_data)
    raw = {"analises": [{
        "grupo": "G1",
        "explicacao": (
            "Hipóteses: A nota 90702 está entre os documentos pendentes e apresenta candidato "
            "na conta 377, que pode explicar a divergência de vínculo; a referência L16 "
            "já existe no Razão da conta 366 e não confirma esse vínculo. "
            "Limitações: é necessário verificar nota, série e contrapartida."
        ),
        "verificar": "1. Compare a nota 90702 entre as contas 366 e 377.\n"
                    "2. Confira L16 e a contrapartida do movimento.",
        "evidencias": ["L16"],
    }]}
    result = fiscal_ai._validar_resposta_ia(raw, report_data, mapping, refs)[0]
    assert result["valores"]["fiscal"] == 2300
    assert result["dossie_contabil"]["documentos"]["candidatos_a_verificar"][0]["nota"] == "90702"
    steps = result["parecer"]["leitura_comparacao"]["orientacoes"]
    assert steps[0]["documentos"][0]["referencia"] == "E-9"
    assert "outra conta" in steps[0]["objetivo"]
    assert "377" in result["parecer"]["analise_exibicao"]
    assert result["auditoria"]["situacao"] in {"conferencia_assistida", "revisao_necessaria"}


def test_prompt_exige_causa_ancorada_e_orientacoes_priorizadas():
    assert "dossie_contabil" in REVIEW_PROMPT
    assert "diferente" in REVIEW_PROMPT.lower()
    assert "240 palavras" in REVIEW_PROMPT
    assert "2 ou 3 passos" in REVIEW_PROMPT
    assert "não deduza ausência" in REVIEW_PROMPT
    assert len(REVIEW_PROMPT.split()) < 650

from decimal import Decimal
import pytest
from app.fiscal_review_outcomes import executive_summary, review_outcome
from app.fiscal_ai_audit import structured_analysis
from app.fiscal_investigation import case_context


@pytest.mark.parametrize("difference, direction", [(100,"acima"),(-100,"abaixo"),(0,"Não há diferença numérica")])
def test_resumo_preserva_sinal_e_nao_confunde_totais_com_conciliacao(difference,direction):
    item = {"valores":{"diferenca":difference}}
    summary = executive_summary(item,{"orientacoes":[{"acao":"Confira NF 100","objetivo":"Confirme a mesma operação","documentos":[{"titulo":"NF 100 (E-1)"}]}]})
    assert direction in summary["conclusao"]
    assert summary["foco"] == "Confira NF 100"
    assert summary["exemplos"] == ["NF 100 (E-1)"]
    if not difference:
        assert "não confirma" in summary["conclusao"]


@pytest.mark.parametrize("value", [None,"não numérico",float("inf"),Decimal("NaN")])
def test_resumo_nao_inventa_zero_quando_falta_valor(value):
    assert not executive_summary({"valores":{"diferenca":value}}, {})
    assert not executive_summary({}, {})


def test_amostragem_documental_e_groq_sao_indicadas_no_resumo():
    item = {"valores":{"diferenca":10},"cobertura_documental":{"amostra":True}}
    assert executive_summary(item,{})["parcial"]
    item["cobertura_documental"]["amostra"] = False
    assert executive_summary(item,{},partial=True)["cobertura"] == "Contexto parcial da IA"


@pytest.mark.parametrize("status", ["VALOR_DIFERENTE","CONTA_DIFERENTE","DATA_DIFERENTE","ESTORNO_EM_ANALISE","AMBIGUO","PROVAVEL","SEM_LANCAMENTO_IDENTIFICADO","MOVIMENTO_SEM_VINCULO"])
def test_criterios_trazem_confirmacao_e_reavaliacao_sem_declarar_erro(status):
    result = review_outcome(status)
    assert result["para_concluir"] and result["quando_reavaliar"]
    assert not review_outcome("CONCILIADO")


def test_criterios_e_resumo_chegam_a_apresentacao_sem_nova_chamada():
    item = {"conta":"470","tipo":"ENTRADAS","valores":{"fiscal":100,"contabil":110,"total_conta":110,"diferenca":10},
        "explicacao":"Hipóteses: causa a confirmar.","resumo_documental":{"documentos_lidos":1,"conciliados":0,"documentos_pendentes":1,"situacoes":{"VALOR_DIFERENTE":1}},
        "parecer":{"comparacoes_documentais":[{"referencia":"E-1","situacao":"VALOR_DIFERENTE","nota":"100","valor_brl":"R$ 100,00","valor_razao_candidato_brl":"R$ 110,00"}]}}
    result = structured_analysis(item,[],documentary=True)
    assert "acima" in result["resumo_executivo"]["conclusao"]
    step = result["leitura_comparacao"]["orientacoes"][0]
    assert "mesma operação" in step["para_concluir"]
    assert "descarte" in step["quando_reavaliar"]

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


def test_conferencia_local_identifica_a_origem_sem_atribuir_limitacoes_a_ia():
    item = {"provedor":"local", "valores":{"diferenca":0},
            "explicacao":"Hipóteses: confirme a origem. Limitações: confira o comprovante."}
    result = structured_analysis(item, [])
    assert result["resumo_executivo"]["cobertura"] == "Conferência local"
    assert not any("indicada pela IA" in text for text in result["informacoes_faltantes"])


@pytest.mark.parametrize("status", ["VALOR_DIFERENTE","CONTA_DIFERENTE","DATA_DIFERENTE","ESTORNO_EM_ANALISE","AMBIGUO","PROVAVEL","SEM_LANCAMENTO_IDENTIFICADO","MOVIMENTO_SEM_VINCULO"])
def test_criterios_trazem_confirmacao_e_reavaliacao_sem_declarar_erro(status):
    result = review_outcome(status)
    assert result["para_concluir"] and result["quando_reavaliar"]
    assert result["explicacao_simples"] and result["solucao_condicional"] and result["resultado_esperado"]
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
    assert step["solucao_condicional"] == review_outcome("VALOR_DIFERENTE")["solucao_condicional"]
    assert step["resultado_esperado"]


def test_orientacao_nao_confunde_falta_de_vinculo_com_falta_de_escrituracao():
    guide = review_outcome("SEM_LANCAMENTO_IDENTIFICADO")
    assert "ainda não significa" in guide["explicacao_simples"]
    assert "escrituração completa" in guide["solucao_condicional"]
    assert "sem lançar a operação outra vez" in guide["solucao_condicional"]


def test_resumo_sem_documentos_nao_sugere_lancamento_corretivo():
    guide = review_outcome("DETALHAMENTO_NECESSARIO")
    assert "ainda não há base" in guide["solucao_condicional"]
    assert review_outcome("DESCONHECIDO") == {}

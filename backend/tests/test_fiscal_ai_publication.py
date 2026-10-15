"""Regressões dos erros observados na empresa 242, sem APIs externas."""
import copy
import json
import pytest
from fastapi import HTTPException
from app import fiscal_ai, fiscal_ai_sessions as sessions
from app.fiscal_ai_audit import protect_publication, note_numbers, local_review_sufficient, ANALYSIS_VERSION


def item(text, **kwargs):
    return dict(conta="361", tipo="ENTRADAS", explicacao=text, verificar="1. Confira os documentos.",
                evidencias=[], **kwargs)


def test_nota_1887_de_outra_conta_nao_pode_ser_publicada():
    answer = item("Hipóteses: pode haver duplicidade; confira a nota fiscal 1887. Limitações: confirmar documento.")
    protect_publication(answer, [{"conta":"361", "referencia":"L236", "historico":"Pago: Fornecedor"}], [])
    assert answer["checagem_semantica"]["interpretacao_retirada"]
    assert "1887" not in answer["explicacao"] + answer["verificar"]


@pytest.mark.parametrize("text, expected", [
    ("notas 149830 e 149721", {"149830","149721"}),
    ("NF 0001887", {"1887"}), ("nota fiscal 1.887", {"1887"}),
    ("FRETE CTRC 62472446", {"62472446"}), ("CT-e nº 00100", {"100"}),
    ("conta 1887 e contrapartida 508", set()),
])
def test_reconhece_notas_sem_confundir_codigos_de_conta(text, expected):
    assert note_numbers(text) == expected


def test_nota_existente_da_propria_conta_preserva_interpretacao():
    answer = item("Fatos: L1 registra compra. Hipóteses: a nota 1887 pode corresponder a L1. Limitações: conferir a série.")
    protect_publication(answer, [{"conta":"361","referencia":"L1","historico":"COMPRA CF NF 1887"}], [])
    assert not answer["checagem_semantica"]["interpretacao_retirada"]
    assert "1887" in answer["explicacao"]
    assert "Fatos:" not in answer["explicacao"]


def test_soma_inventada_dos_pagamentos_361_nao_sobrevive():
    values = [1894,5739,239,5739]
    assert sum(values) == 13611
    answer = item("Fatos: L235, L236, L237 e L238 totalizam R$ 22.956,00. Hipóteses: conferir pagamentos. Limitações: falta documento.",
                  valores={"fiscal":22956,"contabil":22956,"diferenca":0})
    rows = [{"conta":"361","referencia":f"L{235+i}","historico":"Pagamento","debito":v,"credito":0} for i,v in enumerate(values)]
    protect_publication(answer, rows, [])
    assert "22.956" not in answer["explicacao"]
    assert answer["valores"]["fiscal"] == 22956
    assert answer["checagem_semantica"]["interpretacao_retirada"]


def test_conciliados_312_nao_podem_ser_negados_pela_ia():
    answer = item("Fatos: Nenhum documento foi conciliado. Hipóteses: conferir registros. Limitações: falta suporte.",
                  resumo_documental={"documentos_lidos":19,"conciliados":3,"documentos_pendentes":16})
    protect_publication(answer, [], [])
    assert answer["checagem_semantica"]["interpretacao_retirada"]
    assert "Nenhum documento" not in answer["explicacao"]


def test_documentos_359_ja_conciliados_nao_sao_tratados_como_faltantes():
    answer = item("Hipóteses: pode haver documentos fiscais ainda não vinculados. Limitações: confirmar.",
                  resumo_documental={"documentos_lidos":5,"conciliados":5,"documentos_pendentes":0})
    protect_publication(answer, [], [])
    assert answer["checagem_semantica"]["interpretacao_retirada"]
    assert "já foram conciliados" in " ".join(answer["checagem_semantica"]["motivos"])


def test_frete_precisa_de_indicio_na_propria_conta():
    answer = item("Hipóteses: pode ser frete em L1. Limitações: conferir origem.")
    protected = copy.deepcopy(answer)
    protect_publication(protected, [{"referencia":"L1","historico":"Compra"}], [])
    assert protected["checagem_semantica"]["interpretacao_retirada"]
    protect_publication(answer, [{"referencia":"L1","historico":"FRETE CONTRATADO CTRC 100"}], [])
    assert not answer["checagem_semantica"]["interpretacao_retirada"]


def test_pagamentos_iguais_em_datas_distintas_nao_comprovam_duplicidade():
    answer = item("Hipóteses: pode haver duplicidade de pagamentos L236 e L238. Limitações: conferir documentos.")
    rows = [{"referencia":ref,"data":date,"historico":"Pago: Fornecedor", "debito":5739,"credito":0,"contrapartida":"508"}
            for ref,date in (("L236","10/09/2026"),("L238","25/09/2026"))]
    protect_publication(answer,rows,[])
    assert answer["checagem_semantica"]["interpretacao_retirada"]


def test_aviso_semantico_permanece_no_cache():
    answer = item("Hipóteses: confira a nota 1887. Limitações: identificar vínculo.")
    protect_publication(answer,[],[])
    first = copy.deepcopy(answer)
    protect_publication(answer,[],[])
    assert answer == first


def test_cada_consulta_de_sessao_recebe_uma_conta_e_natureza(monkeypatch):
    source = {"empresa_nome":"Fictícia","contas":[{"conta":"1","tipo":"ENTRADAS"},{"conta":"1","tipo":"SAÍDAS"}],
        "lancamentos":[{"conta":"1","_tipo_ia":"ENTRADAS","historico":"NF 100"},
                       {"conta":"1","_tipo_ia":"SAÍDAS","historico":"NF 200"}],
        "documentos_pendentes":{"1:ENTRADAS":[{"nota":"100"}],"1:SAÍDAS":[{"nota":"200"}]}}
    monkeypatch.setattr(sessions,"_completed_cache",{})
    monkeypatch.setattr(sessions.ai_result_cache,"read",lambda _:None)
    seen = []
    def explain(report, **kwargs):
        row = report["contas"][0]
        assert len(report["contas"]) == len(report["lancamentos"]) == len(report["documentos_pendentes"]) == 1
        assert report["lancamentos"][0]["_tipo_ia"] == row["tipo"]
        seen.append(row["tipo"])
        return {"analises":[dict(row)],"provedor":"groq","gratuito":True}
    monkeypatch.setattr(fiscal_ai,"explain",explain)
    assert len(sessions._review_accounts(source,"groq")["analises"]) == 2
    assert seen == ["ENTRADAS","SAÍDAS"]


def test_sucesso_de_uma_conta_e_preservado_se_a_seguinte_falhar(monkeypatch):
    source = {"contas":[{"conta":c,"tipo":"ENTRADAS"} for c in ("417","470")],"lancamentos":[]}
    monkeypatch.setattr(sessions,"_completed_cache",{})
    monkeypatch.setattr(sessions.ai_result_cache,"read",lambda _:None)
    calls = []
    failing = True
    def explain(report, **kwargs):
        row = report["contas"][0]
        calls.append(row["conta"])
        if row["conta"] == "470" and failing:
            raise HTTPException(429,"Cota gratuita indisponível")
        return {"analises":[dict(row)],"provedor":"gemini","gratuito":True}
    monkeypatch.setattr(fiscal_ai,"explain",explain)
    with pytest.raises(HTTPException):
        sessions._review_accounts(source,"gemini")
    failing = False
    assert len(sessions._review_accounts(source,"gemini")["analises"]) == 2
    assert calls == ["417","470","470"]


def test_versao_do_cache_invalida_pareceres_antigos(monkeypatch):
    current = sessions._cache_digest({"contas":[]})
    monkeypatch.setattr(sessions,"ANALYSIS_VERSION","grounded-depth-v7")
    assert sessions._cache_digest({"contas":[]}) != current
    assert ANALYSIS_VERSION == "documentary-evidence-v12"


def test_endpoint_direto_tambem_isola_os_contextos(monkeypatch):
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED","1")
    monkeypatch.setenv("GEMINI_API_KEY","synthetic")
    source = {"contas":[dict(conta=c,tipo="ENTRADAS",situacao="REVISAR",fiscal=10,contabil=8,total_conta=8,diferenca=-2,extras=0)
                        for c in ("361","680")], "lancamentos":[]}
    seen = []
    def complete(payload, *args, **kwargs):
        ctx = json.loads(payload["contents"][0]["parts"][0]["text"])
        assert len(ctx["grupos"]) == 1
        seen.append(ctx["grupos"][0]["resumo"]["conta"])
        return {"analises":[{"grupo":"G1","explicacao":"Hipóteses: causa indeterminada. Limitações: conferir documentos.",
                             "verificar":"1. Confira os documentos.","evidencias":[]}]}, "free"
    monkeypatch.setattr(fiscal_ai,"_gemini_completion",complete)
    assert len(fiscal_ai.explain(source,only_provider="gemini")["analises"]) == 2
    assert seen == ["361","680"]


def objective_report():
    return {"contas":[dict(conta="359",tipo="ENTRADAS",situacao="CONFERE COM ALERTAS",
                         fiscal=100,contabil=100,total_conta=120,diferenca=0,extras=20)],
            "lancamentos":[dict(conta="359",_tipo_ia="ENTRADAS",historico="Pago: fornecedor",
                                data="10/09/2026",debito=20,credito=0,contrapartida="508")],
            "resumo_documental":{"359:ENTRADAS":dict(documentos_lidos=5,conciliados=5,documentos_pendentes=0,
                composicao=dict(confere_com_inicial=True,itens=[dict(codigo=k,descricao=k,valor=v) for k,v in
                    (("vinculados",0),("fiscal_sem_vinculo",0),("cobertura",0),("razao_sem_vinculo",20),("fora_inicial",-20))]))},
            "cobertura_documental":{"359:ENTRADAS":dict(amostra=False,lancamentos_enviados=1,lancamentos_pendentes=1)}}


def test_conferencia_objetiva_nao_consulta_provedores(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Caso objetivo não deve consultar provedores")
    monkeypatch.setattr(fiscal_ai,"_gemini_completion",forbidden)
    monkeypatch.setattr(fiscal_ai,"_gemini_free_key",forbidden)
    report = objective_report()
    result = fiscal_ai.explain(report)
    assert result["provedor"] == "local"
    assert result["analises"][0]["provedor"] == "local"
    assert result["analises"][0]["valores"]["diferenca"] == 0
    assert not result["analises"][0]["checagem_semantica"]["interpretacao_retirada"]


@pytest.mark.parametrize("change", ["amostra","pendente","diferenca","movimento","cobertura","composicao"])
def test_conferencia_incerta_ainda_precisa_de_revisao(change):
    report = objective_report()
    if change == "amostra":
        report["cobertura_documental"]["359:ENTRADAS"]["amostra"] = True
    elif change == "pendente":
        report["resumo_documental"]["359:ENTRADAS"]["documentos_pendentes"] = 1
    elif change == "diferenca":
        report["contas"][0]["diferenca"] = 1
    elif change == "movimento":
        report["lancamentos"][0]["historico"] = "Compra de mercadorias"
    elif change == "cobertura":
        report["cobertura_documental"]["359:ENTRADAS"]["lancamentos_pendentes"] = 2
    else:
        report["resumo_documental"]["359:ENTRADAS"]["composicao"]["itens"][-1]["valor"] = -19
    assert not local_review_sufficient(report)

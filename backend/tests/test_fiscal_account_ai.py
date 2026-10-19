import copy
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import fiscal_account_ai as account_ai, fiscal_ai_sessions as sessions
from app.fiscal_documentos import recortar_acumulador_ia


def report():
    return {"contas":[dict(conta=c,tipo=t,situacao="REVISAR",fiscal=100,contabil=90,total_conta=90,diferenca=-10,extras=0)
                      for c,t in [("470","ENTRADAS"),("470","SAÍDAS"),("312","ENTRADAS")]],
            "lancamentos":[dict(conta=c,natureza=n,debito=90 if n=="DÉBITO" else 0,credito=90 if n=="CRÉDITO" else 0,historico=c+n)
                           for c,n in [("470","DÉBITO"),("470","CRÉDITO"),("312","DÉBITO")]]}


def test_scope_isola_conta_e_tipo_sem_alterar_relatorio():
    original=report();scoped=account_ai.scope_account(original,"470","ENTRADAS")
    assert len(scoped["contas"])==len(scoped["lancamentos"])==1
    assert scoped["lancamentos"][0]["natureza"]=="DÉBITO"
    assert len(original["contas"])==3
    with pytest.raises(ValueError): account_ai.scope_account(original,"999","ENTRADAS")


def accumulator_item():
    docs=[dict(id="E1",acumulador="1403",situacao="VALOR_DIFERENTE",valor=100),dict(id="E2",acumulador="1102",situacao="CONCILIADO",valor=200)]
    moves=[dict(id="R1",conta="470",valor=90),dict(id="R2",conta="470",valor=200)]
    comparisons=[dict(id="C1",situacao="VALOR_DIFERENTE",linhas_fiscais=[docs[0]],lancamentos=[moves[0]]),dict(id="C2",situacao="CONCILIADO",linhas_fiscais=[docs[1]],lancamentos=[moves[1]])]
    return dict(conta="470",documentos=docs,comparacoes=comparisons,razao_pendente=moves,
                acumuladores=[dict(codigo="1403",valor_resumo=100,detalhamento_disponivel=True,descricao="Fretes"),dict(codigo="1102",valor_resumo=200,detalhamento_disponivel=True)])


def test_acumulador_recalcula_totais_e_exclui_outros_documentos_e_movimentos():
    item=accumulator_item();scoped,row=recortar_acumulador_ia(item,report()["contas"][0],"1403")
    assert [d["id"] for d in scoped["documentos"]]==["E1"]
    assert [d["id"] for d in scoped["razao_pendente"]]==["R1"]
    assert row["fiscal"]==100 and row["contabil"]==90 and row["diferenca"]==-10
    assert row["acumuladores"]=="1403" and len(item["documentos"])==2


def test_nao_rateia_parcelas_compartilhadas_ou_candidatos_ambiguos():
    item=accumulator_item();item["comparacoes"][1]["lancamentos"]=item["comparacoes"][0]["lancamentos"]
    with pytest.raises(ValueError,match="compartilhados"): recortar_acumulador_ia(item,report()["contas"][0],"1403")
    item=accumulator_item();item["comparacoes"][0]["situacao"]="AMBIGUO"
    with pytest.raises(ValueError,match="ambíguos"): recortar_acumulador_ia(item,report()["contas"][0],"1403")


def post(data):
    return TestClient(app).post('/api/v1/conferencia-fiscal/ia/conta',data=data,files={"acumuladores":("f.xls",b"test"),"razao":("r.xls",b"test")})


def test_endpoint_so_prepara_uma_conta_e_reaproveita_cache(monkeypatch):
    source=report();calls=[]
    monkeypatch.setattr(account_ai,"conferencia_fiscal_preview",lambda *a,**k:copy.deepcopy(source))
    monkeypatch.setattr(sessions,"free_providers",lambda:["groq"])
    monkeypatch.setattr(sessions,"provider_wait_seconds",lambda p:0)
    monkeypatch.setattr(sessions.fiscal_ai,"explain",lambda r,**k:calls.append(copy.deepcopy(r)) or {"analises":[{"conta":r["contas"][0]["conta"],"tipo":r["contas"][0]["tipo"]}],"provedor":"groq","gratuito":True})
    sessions._completed_cache.clear();data={"conta":"470","tipo":"ENTRADAS"}
    first=post(data);assert first.status_code==200,first.text
    again=post(data);assert again.status_code==200,again.text
    assert len(calls)==1 and len(calls[0]["contas"])==len(calls[0]["lancamentos"])==1
    assert first.json()["escopo"]==dict(data,origem="resumo",acumulador="")


def test_totais_iguais_sem_pendencias_nao_gastam_ia(monkeypatch):
    source=report();source["contas"][0]["situacao"]="CONFERE"
    monkeypatch.setattr(account_ai,"conferencia_fiscal_preview",lambda *a,**k:source)
    monkeypatch.setattr(sessions,"prepare",lambda r:pytest.fail("Não deve preparar chamada de IA"))
    response=post({"conta":"470","tipo":"ENTRADAS"})
    assert response.status_code==200 and response.json()["provedor"]=="local"


@pytest.mark.parametrize('data',[{"conta":"470","tipo":"SERVIÇOS"},{"conta":"470","tipo":"ENTRADAS","acumulador":"1403"},{"conta":"470","tipo":"ENTRADAS","origem":"documentos"}])
def test_rejeita_escopos_incompletos_sem_chamar_ia(data):
    assert post(data).status_code==422

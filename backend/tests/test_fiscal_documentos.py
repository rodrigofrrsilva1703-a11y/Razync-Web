"""Cruzamento opcional de entradas/saídas, sem atribuir causas por totais."""
import io

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


def book(rows):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, header=False, index=False, sheet_name="Dados")
    return out.getvalue()


def initial():
    fiscal = book([
        ["COMERCIAL DEMONSTRACAO LTDA"],
        ["Período:", "01/08/2026 a 31/08/2026"],
        ["ENTRADAS"],
        ["Código", "Descrição", "Valor Contábil", "Conta"],
        [1152, "Compras", 1800, 508],
        ["SAÍDAS"],
        ["Código", "Descrição", "Valor Contábil", "Conta"],
        [700, "Vendas", 1000, 408],
    ])
    ledger = book([
        ["Empresa:", "", "COMERCIAL DEMONSTRACAO LTDA"],
        ["Período:", "01/08/2026 - 31/08/2026"],
        ["Conta:", 508],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        ["03/08/2026", 1, "COMPRA DE MATERIAL CF NF 100", 800, 242, 1000, 0],
        ["04/08/2026", 2, "COMPRA DE MATERIAL CF NF 101", 800, 242, 250, 0],
        ["03/08/2026", 3, "COMPRA DE MATERIAL CF NF 100", 800, 1408, 1000, 0],
        ["Conta:", 408],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        ["07/08/2026", 3, "VENDA DE MATERIAL CF NF 900", 800, 242, 0, 700],
    ])
    return fiscal, ledger


def detail(tipo="ENTRADAS", *, company="COMERCIAL DEMONSTRACAO LTDA", period="01/08/2026 a 31/08/2026", repeated=False):
    rows = [
        [company],
        ["Período:", period],
        ["ACOMPANHAMENTO DE " + tipo],
        ["Código", "Nota", "Data", "CFOP", "Valor Contábil", "Tipo", "Fornecedor" if tipo == "ENTRADAS" else "Cliente"],
    ]
    if tipo == "ENTRADAS":
        rows += [
            [1152, 100, "03/08/2026", 1102, 1000, "", "Fornecedor Teste"],
            ["", "", "", "", 180, "ICMS", ""],
            [1152, 101, "04/08/2026", 1102, 200, "", "Fornecedor Teste"],
            [1152, 102, "05/08/2026", 1102, 600, "", "Fornecedor Teste"],
            ["Total Fornecedor", "", "", "", 1800],
        ]
        if repeated:
            rows += [[1152, 100, "03/08/2026", 1102, 1000, "", "Fornecedor Teste"]]
    else:
        rows += [
            [700, 900, "07/08/2026", 5102, 700, "", "Cliente Teste"],
            [700, 901, "08/08/2026", 5102, 300, "", "Cliente Teste"],
            ["Total Cliente!", "", "", "", 1000],
        ]
    return book(rows)


def post(*, entrada=True, saida=True, fiscal=None, razao=None, entrada_bytes=None, saida_bytes=None, filial="242"):
    f, r = initial()
    files = {
        "acumuladores": ("Resumo.xlsx", fiscal or f),
        "razao": ("Razao.xlsx", razao or r),
    }
    if entrada:
        files["entradas"] = ("Entradas.xlsx", entrada_bytes or detail())
    if saida:
        files["saidas"] = ("Saidas.xlsx", saida_bytes or detail("SAÍDAS"))
    return TestClient(app).post(
        "/api/v1/conferencia-fiscal/investigar", files=files, data={"filial": filial})


def test_entrega_duas_naturezas_e_nao_conta_tributos_ou_totais():
    res = post()
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["filial"] == "242"
    assert data["tipos_investigados"] == ["ENTRADAS", "SAÍDAS"]
    assert len(data["contas"]) == 2
    acc = next(r for r in data["contas"] if r["tipo"] == "ENTRADAS")
    assert acc["acumuladores"][0]["codigo"] == "1152"
    assert acc["acumuladores"][0]["quantidade_documentos"] == 3
    assert acc["acumuladores"][0]["valor_documentos"] == 1800
    status = {d["nota"]: d["situacao"] for d in acc["documentos"]}
    assert status == {
        "100": "CONCILIADO",
        "101": "VALOR_DIFERENTE",
        "102": "SEM_LANCAMENTO_IDENTIFICADO",
    }
    assert acc["resumo"]["conciliados"] == 1
    assert all(d["nota"] != "100" or d["razao_id"] for d in acc["documentos"])
    saida = next(r for r in data["contas"] if r["tipo"] == "SAÍDAS")
    assert saida["acumuladores"][0]["quantidade_documentos"] == 2
    assert saida["resumo"]["conciliados"] == 1


def test_apenas_entradas_nao_trata_saida_como_erro():
    res = post(saida=False)
    assert res.status_code == 200, res.text
    result = res.json()
    assert result["tipos_investigados"] == ["ENTRADAS"]
    assert all(r["tipo"] == "ENTRADAS" for r in result["contas"])


def test_arquivo_de_empresa_diferente_e_bloqueado():
    res = post(saida=False, entrada_bytes=detail(company="EMPRESA OUTRA LTDA"))
    assert res.status_code == 422
    assert "outra empresa" in res.json()["detail"]


def test_periodo_divergente_e_bloqueado():
    res = post(saida=False, entrada_bytes=detail(period="01/09/2026 a 30/09/2026"))
    assert res.status_code == 422
    assert "período" in res.json()["detail"].lower()


def test_exige_relatorio_adicional():
    res = post(entrada=False, saida=False)
    assert res.status_code == 422


def test_nao_concilia_em_caso_de_documento_repetido_com_mesma_nota_e_valor():
    res = post(saida=False, entrada_bytes=detail(repeated=True))
    assert res.status_code == 200, res.text
    rows = res.json()["contas"][0]["documentos"]
    same = [r for r in rows if r["nota"] == "100"]
    assert len(same) == 2
    assert all(item["situacao"] == "AMBIGUO" for item in same)


def test_nao_concilia_nota_sozinha_sem_valor_correspondente():
    res = post(saida=False)
    assert res.status_code == 200, res.text
    row = next(item for item in res.json()["contas"][0]["documentos"] if item["nota"] == "101")
    assert row["situacao"] != "CONCILIADO"



def test_ia_recebe_so_pendencias_sem_documentos_ja_conciliados(monkeypatch):
    from app import fiscal_ai
    captured = {}
    def fake_explain(report):
        captured.update(report)
        context, _, _, _ = fiscal_ai.detailed_context(report)
        for group in context["grupos"]:
            assert all(d["nota"] not in {"100", "900"} for d in group.get("pendencias_documentais", []))
            assert "pendencias_documentais" in group
        return {"analises": [], "provedor": "gemini", "gratuito": True}
    monkeypatch.setattr(fiscal_ai, "explain", fake_explain)
    fiscal, ledger = initial()
    res = TestClient(app).post("/api/v1/conferencia-fiscal/investigar/ia", files={
        "acumuladores": ("Resumo.xlsx", fiscal),
        "razao": ("Razao.xlsx", ledger),
        "entradas": ("Entradas.xlsx", detail()),
        "saidas": ("Saidas.xlsx", detail("SAÍDAS")),
    }, data={"filial": "242"})
    assert res.status_code == 200, res.text
    assert res.json()["provedor"] == "gemini"
    assert all("100" not in str(d.get("nota", "")) for items in captured["documentos_pendentes"].values() for d in items)
    assert captured["lancamentos"]
    assert not any("CF NF 100" in mov["historico"] or "CF NF 900" in mov["historico"]
                   for mov in captured["lancamentos"])


def test_falha_de_cota_da_ia_nao_apaga_resultado_deterministico(monkeypatch):
    from app import fiscal_ai
    from fastapi import HTTPException
    monkeypatch.setattr(fiscal_ai, "explain", lambda report: (_ for _ in ()).throw(HTTPException(
        429, "Cota gratuita indisponível.")))
    f, r = initial()
    files = {
        "acumuladores": ("Resumo.xlsx", f),
        "razao": ("Razao.xlsx", r),
        "entradas": ("Entradas.xlsx", detail())
    }
    client = TestClient(app)
    failed = client.post("/api/v1/conferencia-fiscal/investigar/ia", files=files, data={"filial":"242"})
    assert failed.status_code == 429
    success = client.post("/api/v1/conferencia-fiscal/investigar", files=files, data={"filial":"242"})
    assert success.status_code == 200
    assert success.json()["contas"][0]["documentos_total"] == 3

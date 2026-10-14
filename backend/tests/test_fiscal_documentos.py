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
    from app import fiscal_ai_sessions
    monkeypatch.setattr(fiscal_ai_sessions, "free_providers", lambda: ["gemini"])
    def fake_explain(report, **kwargs):
        assert kwargs["only_provider"] == "gemini"
        captured.update(report)
        context, _, _, _ = fiscal_ai.detailed_context(report)
        for group in context["grupos"]:
            assert all(d["nota"] not in {"100", "900"} for d in group.get("pendencias_documentais", []))
            assert "pendencias_documentais" in group
        return {"analises": [{"conta": row["conta"]} for row in report["contas"] if row["situacao"] != "CONFERE"], "provedor": "gemini", "gratuito": True}
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
    from app import fiscal_ai_sessions
    monkeypatch.setattr(fiscal_ai_sessions, "free_providers", lambda: ["gemini"])
    monkeypatch.setattr(fiscal_ai, "explain", lambda report, **kwargs: (_ for _ in ()).throw(HTTPException(
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



def test_layout_real_dominio_usa_ac_e_nao_codigo_da_linha():
    from app.fiscal_documentos import ler_acompanhamento
    sample = book([
        ["COMERCIAL DEMONSTRACAO LTDA"],
        ["Período:", "01/08/2026 até 31/08/2026"],
        ["Código", "Data", "Nota", "Série", "Código", "Fornecedor",
         "CFOP", "AC.", "Valor Contábil", "Tipo", "Base Cálculo"],
        [2935403, "03/08/2026", 100, 1, 19573, "Fornecedor Teste",
         1102, 1152, 1234.56, "ICMS", 1000.0],
        ["", "", "", "", "", "", "", "", "", "IPI", 34.56],
        ["Total Fornecedor", "", "", "", "", "", "", "", 1234.56, "ICMS"],
    ])
    result = ler_acompanhamento(sample, "entradas.xlsx", "ENTRADAS", {"1152"})
    assert len(result["documentos"]) == 1
    assert result["documentos"][0]["acumulador"] == "1152"
    assert result["documentos"][0]["nota"] == "100"
    assert result["documentos"][0]["valor"] == 1234.56


def test_cnpj_incompativel_impede_cruzamento_de_filial():
    fiscal, ledger = initial()
    # Modelo com CNPJ no resumo, como na exportação real Domínio.
    fiscal = book([
        ["COMERCIAL DEMONSTRACAO LTDA"],
        ["CNPJ:", "", "08299944000113"],
        ["Período:", "01/08/2026 a 31/08/2026"],
        ["ENTRADAS"],
        ["Código", "Descrição", "Valor Contábil", "Conta"],
        [1152, "Compras", 1800, 508],
    ])
    wrong = book([
        ["COMERCIAL DEMONSTRACAO LTDA"],
        ["CNPJ:", "", "08299944000202"],
        ["Período:", "01/08/2026 a 31/08/2026"],
        ["Código", "Nota", "Data", "CFOP", "Valor Contábil"],
        [1152, 100, "03/08/2026", 1102, 1000],
    ])
    res = post(saida=False, fiscal=fiscal, razao=ledger, entrada_bytes=wrong)
    assert res.status_code == 422
    assert "CNPJ" in res.json()["detail"]


def test_mesma_nota_e_valor_com_data_diferente_permanece_pendente():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][0] = "20/08/2026"
    res = post(saida=False, fiscal=f, razao=book(table))
    group = res.json()["contas"][0]
    doc = next(d for d in group["documentos"] if d["nota"] == "100")
    assert doc["situacao"] == "DATA_DIFERENTE"
    assert "20/08/2026" in doc["criterio"]
    assert any(m["id"] == doc["razao_id"] for m in group["razao_pendente"])


def test_documento_transporte_explicito_sem_confundir_texto_comum():
    from app.fiscal_documentos import _nota_historico
    for text in ("FRETE CONTRATADO CF CTRC 263553 - TRANSPORTADORA",
                 "FRETE CT-e nº 263553", "FRETE CTE 263553"):
        assert _nota_historico(text) == "263553"
    assert _nota_historico("PACOTE 263553") == ""
    f, r = initial()
    rows = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    rows[4][2] = "FRETE CONTRATADO CF CTRC 100 - Fornecedor Teste"
    result = post(saida=False, fiscal=f, razao=book(rows)).json()
    assert next(d for d in result["contas"][0]["documentos"] if d["nota"] == "100")["situacao"] == "CONCILIADO"


def bulk_files(matched=350, pending=40):
    fiscal = book([
        ["COMERCIAL DEMONSTRACAO LTDA"], ["Período:", "01/08/2026 a 31/08/2026"],
        ["ENTRADAS"], ["Código", "Descrição", "Valor Contábil", "Conta"],
        [1152, "Compras", (matched + pending) * 100, 508],
    ])
    ledger = book([
        ["Empresa:", "", "COMERCIAL DEMONSTRACAO LTDA"],
        ["Período:", "01/08/2026 - 31/08/2026"], ["Conta:", 508],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        *[["03/08/2026", i, f"COMPRA CF NF {i}", 800, 242, 100, 0]
          for i in range(1, matched + 1)],
    ])
    docs = book([
        ["COMERCIAL DEMONSTRACAO LTDA"], ["Período:", "01/08/2026 a 31/08/2026"],
        ["Código", "Nota", "Data", "CFOP", "Valor Contábil"],
        *[[1152, i, "03/08/2026", 1102, 100] for i in range(1, matched + pending + 1)],
    ])
    return fiscal, ledger, docs


def test_pendencias_apos_300_conciliados_nao_somem_e_amostra_e_explicita(monkeypatch):
    from app import fiscal_documentos as module, fiscal_ai
    f, r, d = bulk_files()
    args = (f, "Resumo.xlsx", r, "Razao.xlsx", (d, "Entradas.xlsx"))
    result = module.investigar_documentos(*args, filial="242")
    assert result["contas"][0]["documentos"][0]["nota"] == "351"
    calls = []
    original = module.conferencia_fiscal_preview
    def preview(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "conferencia_fiscal_preview", preview)
    report = module.preparar_relatorio_pendencias_para_ia(*args, filial="242")
    assert len(calls) == 1
    assert len(report["documentos_pendentes"]["508:ENTRADAS"]) == 30
    assert report["cobertura_documental"]["508:ENTRADAS"]["documentos_pendentes"] == 40
    assert report["cobertura_documental"]["508:ENTRADAS"]["amostra"] is True
    context, _, _, coverage = fiscal_ai.detailed_context(report)
    assert context["grupos"][0]["cobertura_documental"]["documentos_enviados"] == 30
    assert "amostra" in coverage
    assert "Sem corte" not in coverage


def test_sessao_documental_reutiliza_resultado_e_referencias(monkeypatch):
    from app import fiscal_ai, fiscal_ai_sessions as sessions
    monkeypatch.setattr(sessions, "free_providers", lambda: ["gemini"])
    calls = []
    def explain(report, **kwargs):
        assert kwargs["only_provider"] == "gemini"
        # A conferência ordena o Razão por conta: NF 101 mantém a referência
        # global L3 mesmo após remover os registros já conciliados.
        assert report["lancamentos"][0]["_referencia_ia"] == "L3"
        assert report["documentos_pendentes"]["508:ENTRADAS"][0]["razao_id"] == "L3"
        calls.append(1)
        return {"analises": [{"conta": "508", "tipo": "ENTRADAS"}], "provedor": "gemini", "gratuito": True}
    monkeypatch.setattr(fiscal_ai, "explain", explain)
    f, r = initial()
    client = TestClient(app)
    res = client.post("/api/v1/conferencia-fiscal/investigar/ia/sessoes", files={
        "acumuladores": ("Resumo.xlsx", f), "razao": ("Razao.xlsx", r),
        "entradas": ("Entradas.xlsx", detail()),
    }, data={"filial": "242"})
    assert res.status_code == 200, res.text
    manifest = res.json()
    assert manifest["cobertura_documental"]["508:ENTRADAS"]["documentos_pendentes"] == 2
    url = f"/api/v1/conferencia-fiscal/ia/sessoes/{manifest['sessao']}"
    first = client.post(url + "/lotes/0")
    assert first.status_code == 200, first.text
    assert client.post(url + "/lotes/0").json() == first.json()
    assert calls == [1]
    assert client.delete(url).status_code == 200
    assert client.post(url + "/lotes/0").status_code == 410


def test_diferenca_documental_e_calculada_localmente_e_nao_confirma_vinculo():
    from app.fiscal_documentos import preparar_relatorio_pendencias_para_ia
    f, r = initial()
    result = preparar_relatorio_pendencias_para_ia(f,"Resumo.xlsx",r,"Razao.xlsx",(detail(),"Entradas.xlsx"),filial="242")
    d = result["documentos_pendentes"]["508:ENTRADAS"][0]
    assert d["nota"] == "101"
    assert d["valor_brl"] == "R$ 200,00"
    assert d["valor_razao_candidato_brl"] == "R$ 250,00"
    assert d["diferenca_candidato_brl"] == "R$ 50,00"
    assert d["vinculo_confirmado"] is False
    group = post(saida=False).json()["contas"][0]
    doc = next(d for d in group["documentos"] if d["nota"] == "101")
    assert doc["diferenca_candidato"] == 50


def test_referencia_documental_inventada_ou_de_outra_conta_e_rejeitada():
    import pytest
    from app import fiscal_ai, fiscal_documentos
    f, r = initial()
    report = fiscal_documentos.preparar_relatorio_pendencias_para_ia(f,"Resumo.xlsx",r,"Razao.xlsx",
        (detail(),"Entradas.xlsx"),(detail("SAÍDAS"),"Saidas.xlsx"),filial="242")
    _, mapping, refs, _ = fiscal_ai.detailed_context(report)
    ident = next(k for k,v in mapping.items() if v["conta"] == "508")
    def answer(ref):
        return {"analises":[{"grupo":k,"explicacao": f"Hipóteses: conferir {ref}." if k == ident else "Conferir documento.",
                             "verificar":"1. Conferir origem.","evidencias":[]} for k in mapping]}
    for invalid in ("E-999999","S-2"):
        with pytest.raises(ValueError,match="Invalid evidence reference"):
            fiscal_ai._validar_resposta_ia(answer(invalid),report,mapping,refs)
    validated = fiscal_ai._validar_resposta_ia(answer("E-2"),report,mapping,refs)
    item = next(i for i in validated if i["conta"] == "508")
    assert item["documentos_evidencias"][0]["referencia"] == "E-2"
    assert item["parecer"]["comparacoes_documentais"][0]["diferenca_candidato_brl"] == "R$ 50,00"


def test_parcelas_da_mesma_nf_sao_somadas_sem_falsa_divergencia():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][2] = "COMPRA CF NF 100 - Fornecedor Teste"
    table[4][5] = 900
    table.insert(5, ["03/08/2026", 5, "FRETE CF NF 100 - Fornecedor Teste", 800, 242, 100, 0])
    group = post(saida=False, fiscal=f, razao=book(table)).json()["contas"][0]
    d = next(d for d in group["documentos"] if d["nota"] == "100")
    assert d["situacao"] == "CONCILIADO"
    pair = next(c for c in group["comparacoes"] if c["nota"] == "100")
    assert pair["valor_fiscal"] == pair["valor_razao"] == 1000
    assert pair["diferenca"] == 0
    assert len(pair["lancamentos"]) == 2
    assert not any(m["nota"] == "100" for m in group["razao_sem_vinculo"])


def test_mesma_nf_dividida_por_cfop_e_parcelas_preserva_linhas_de_origem():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][2] = "COMPRA CF NF 100 - Fornecedor Teste"
    table[4][5] = 900
    table.insert(5, ["03/08/2026", 5, "FRETE CF NF 100 - Fornecedor Teste", 800, 242, 100, 0])
    rows = pd.read_excel(io.BytesIO(detail()), header=None).values.tolist()
    rows[4][4] = 600
    rows.insert(5, [1152, 100, "03/08/2026", 1403, 400, "", "Fornecedor Teste"])
    group = post(saida=False, fiscal=f, razao=book(table), entrada_bytes=book(rows)).json()["contas"][0]
    pair = next(c for c in group["comparacoes"] if c["nota"] == "100")
    assert len(pair["linhas_fiscais"]) == 2
    assert pair["valor_fiscal"] == pair["valor_razao"] == 1000
    assert all(d["situacao"] == "CONCILIADO" for d in group["documentos"] if d["nota"] == "100")


def test_parcelas_divergentes_mostram_diferenca_conjunta_uma_vez():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][2] = "COMPRA CF NF 100 - Fornecedor Teste"
    table[4][5] = 850
    table.insert(5, ["03/08/2026", 5, "FRETE CF NF 100 - Fornecedor Teste", 800, 242, 100, 0])
    pair = next(c for c in post(saida=False, fiscal=f, razao=book(table)).json()["contas"][0]["comparacoes"] if c["nota"] == "100")
    assert pair["situacao"] == "VALOR_DIFERENTE"
    assert pair["valor_razao"] == 950
    assert pair["diferenca"] == -50


def test_parceiro_diferente_nao_vincula_mesma_nota_valor_e_data():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][2] = "COMPRA CF NF 100 - Outro Fornecedor"
    group = post(saida=False, fiscal=f, razao=book(table)).json()["contas"][0]
    assert next(d for d in group["documentos"] if d["nota"] == "100")["situacao"] == "SEM_LANCAMENTO_IDENTIFICADO"


def test_relatorio_grande_retorna_todos_os_registros_e_comparacoes():
    f, r, d = bulk_files(matched=1250, pending=350)
    group = post(saida=False, fiscal=f, razao=r, entrada_bytes=d).json()["contas"][0]
    assert group["documentos_total"] == len(group["documentos"]) == 1600
    assert len(group["comparacoes"]) == 1600
    assert group["resumo"]["conciliados"] == 1250
    assert group["resumo"]["pendentes"] == 350
    assert group["documentos"][0]["nota"] == "1251"
    assert any(d["nota"] == "1600" for d in group["documentos"])


def test_indicio_em_outra_conta_nao_e_ausencia_ou_conciliacao():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][2] = "COMPRA CF NF 100 - Fornecedor Teste"
    table[2][1] = 509
    table.insert(5, table[3].copy())
    table.insert(5, ["Conta:", 508])
    fiscal_rows = pd.read_excel(io.BytesIO(f), header=None).values.tolist()
    fiscal_rows.insert(5, [1153, "Outra conta de compras", 1000, 509])
    group = next(g for g in post(saida=False, fiscal=book(fiscal_rows), razao=book(table)).json()["contas"] if g["conta"] == "508")
    pair = next(c for c in group["comparacoes"] if c["nota"] == "100")
    assert pair["situacao"] == "CONTA_DIFERENTE"
    assert pair["lancamentos"][0]["conta"] == "509"
    assert pair["diferenca"] == 0
    assert group["resumo"]["conciliados"] == 0


def test_numero_repetido_em_datas_diferentes_prefere_data_exata():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table.insert(5, ["05/08/2026", 5, "COMPRA CF NF 100", 800, 242, 1000, 0])
    rows = pd.read_excel(io.BytesIO(detail()), header=None).values.tolist()
    rows.insert(5, [1152, 100, "05/08/2026", 1102, 1000, "", "Fornecedor Teste"])
    group = post(saida=False, fiscal=f, razao=book(table), entrada_bytes=book(rows)).json()["contas"][0]
    docs = [d for d in group["documentos"] if d["nota"] == "100"]
    assert len(docs) == 2
    assert all(d["situacao"] == "CONCILIADO" for d in docs)
    assert len({d["razao_id"] for d in docs}) == 2


def test_parcelas_indistinguiveis_nao_conciliam_por_soma():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][2] = "COMPRA CF NF 100 - Fornecedor Teste"
    table[4][5] = 500
    table.insert(5, table[4].copy())
    group = post(saida=False, fiscal=f, razao=book(table)).json()["contas"][0]
    d = next(d for d in group["documentos"] if d["nota"] == "100")
    assert d["situacao"] == "AMBIGUO"
    assert next(c for c in group["comparacoes"] if c["nota"] == "100")["diferenca"] is None


def test_mesmo_valor_e_data_com_outra_nf_nao_cria_indicio_falso():
    f, r = initial()
    table = pd.read_excel(io.BytesIO(r), header=None).values.tolist()
    table[4][2] = "COMPRA CF NF 999"
    d = next(d for d in post(saida=False, fiscal=f, razao=book(table)).json()["contas"][0]["documentos"] if d["nota"] == "100")
    assert d["situacao"] == "SEM_LANCAMENTO_IDENTIFICADO"

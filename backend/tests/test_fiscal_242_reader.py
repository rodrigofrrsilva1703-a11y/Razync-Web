import io
import struct

import pandas as pd
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from razync import conferencia_fiscal, dominio_ledger


def workbook(sheets):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, header=False, index=False)
    return out.getvalue()


def reports():
    fiscal = workbook({"Fiscal": [
        ["ENTRADAS"], ["Codigo", "Descrição", "Valor Contabil", "Conta"],
        [1152, "Mercadorias", 1234.56, 22643],
    ]})
    ledger = workbook({"Razão": [
        ["Período:", "01/08/2026 - 31/08/2026"],
        ["Conta:", 22643.0, "", "", "", "ESTOQUE"],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        [46237, 10, "COMPRA DE MERCADORIA CF NF 1", 22644.0, 242, 1234.56, 0],
        [46237, 11, "COMPRA DE MERCADORIA CF NF 2", 22644.0, 1408, 999, 0],
        ["Saldo anterior", "", "", "", "", 99999, 0],
    ]})
    return fiscal, ledger


def test_fiscal_242_preview_and_excel_same_values():
    fiscal, ledger = reports()
    client = TestClient(app)
    files = {"acumuladores": ("fiscal.xlsx", fiscal), "razao": ("razao.xlsx", ledger)}
    preview = client.post("/api/v1/conferencia-fiscal/242/preview", files=files)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["filial_aplicada"] == "242"
    assert len(data["lancamentos"]) == 1
    assert data["lancamentos"][0]["data"] == "03/08/2026"
    assert data["lancamentos"][0]["contrapartida"] == "22644"
    assert data["contas"][0]["contabil"] == 1234.56
    assert data["contas"][0]["situacao"] == "CONFERE"
    response = client.post("/api/v1/conferencia-fiscal/242", files=files)
    assert response.status_code == 200, response.text
    book = load_workbook(io.BytesIO(response.content), data_only=True)
    resumo = pd.read_excel(io.BytesIO(response.content), sheet_name=book.sheetnames[0])
    assert resumo.iloc[0]["CONTÁBIL COMPATÍVEL"] == 1234.56
    assert resumo.iloc[0]["SITUAÇÃO"] == "CONFERE"
    filial = client.post("/api/v1/conferencia-fiscal/1408/preview", files=files)
    assert filial.status_code == 200, filial.text
    assert filial.json()["filial_aplicada"] == "1408"
    assert filial.json()["contas"][0]["contabil"] == 999.0


def test_fiscal_uses_shared_biff_recovery_preserving_all_sheets(monkeypatch):
    recovered = pd.ExcelFile(io.BytesIO(reports()[1]))
    original = conferencia_fiscal.pd.ExcelFile
    def open_excel(source, *args, **kwargs):
        if source.getvalue() == b"irregular":
            raise ValueError("invalid BOUNDSHEET")
        return original(source, *args, **kwargs)
    monkeypatch.setattr(conferencia_fiscal.pd, "ExcelFile", open_excel)
    calls = []
    def recover(content, *, workbook=False):
        calls.append((content, workbook))
        return recovered
    monkeypatch.setattr(dominio_ledger, "_recuperar_xls_biff_irregular", recover)
    movements, _ = conferencia_fiscal.ler_razao(b"irregular", "Domínio.xls")
    assert calls == [(b"irregular", True)]
    assert movements["DÉBITO"].tolist() == [1234.56, 999]


def test_html_xls_brazilian_values_and_all_tables():
    table = '''<table><tr><td>Conta:</td><td>22643</td></tr>
    <tr><td>Data</td><td>Lote</td><td>Histórico</td><td>Cta.C.Part.</td><td>Débito</td><td>Crédito</td></tr>
    <tr><td>03/08/2026</td><td>1</td><td>COMPRA CF NF 1</td><td>22644</td><td>1.234,56</td><td>0,00</td></tr></table>'''
    movements, _ = conferencia_fiscal.ler_razao((table + table).encode(), "razao.xls")
    assert len(movements) == 2
    assert movements["DÉBITO"].tolist() == [1234.56, 1234.56]


def test_new_sheet_does_not_inherit_previous_account():
    content = workbook({
        "Conta": [["Conta:", 22643], ["Data", "Lote", "Histórico", "Cta.C.Part.", "Débito", "Crédito"],
                  ["03/08/2026", 1, "COMPRA CF NF 1", 22644, 100, 0]],
        "Sem conta": [["Data", "Lote", "Histórico", "Cta.C.Part.", "Débito", "Crédito"],
                      ["03/08/2026", 2, "FORA DA CONTA", 1, 500, 0]],
    })
    movements, _ = conferencia_fiscal.ler_razao(content, "razao.xlsx")
    assert movements["DÉBITO"].tolist() == [100]


def test_biff_recovery_keeps_multiple_sheets_and_legacy_dataframe(monkeypatch):
    def record(code, content=b""):
        return struct.pack("<HH", code, len(content)) + content
    def bof(kind):
        return record(0x809, struct.pack("<HHHHII", 0x600, kind, 0x0DBB, 1996, 0x41, 6))
    def sheet(number):
        return (bof(0x10) + record(0x200, struct.pack("<IIHHH", 0, 1, 0, 1, 0))
                + record(0x203, struct.pack("<HHHd", 0, 0, 0, number)) + record(0xA))
    stream = bof(5)
    for name in (b"One", b"Two"):
        stream += record(0x85, struct.pack("<IBBBB", 0, 0, 0, len(name), 0) + name)
    stream += record(0xA) + sheet(123) + sheet(456)
    class Document:
        def __init__(self, *args, **kwargs): pass
        def get_named_stream(self, name): return stream
    monkeypatch.setattr("xlrd.compdoc.CompDoc", Document)
    book = dominio_ledger._recuperar_xls_biff_irregular(b"synthetic-container", workbook=True)
    assert book.sheet_names == ["One", "Two"]
    assert pd.read_excel(book, sheet_name="Two", header=None).iloc[0, 0] == 456
    first = dominio_ledger._recuperar_xls_biff_irregular(b"synthetic-container")
    assert first.iloc[0, 0] == 123


def test_dois_acumuladores_mesma_conta_aparecem_no_preview():
    """O Razão é por conta, mas a apresentação precisa preservar cada acumulador fiscal."""
    _, ledger = reports()
    fiscal = workbook({"Fiscal": [
        ["ENTRADAS"], ["Codigo", "Descrição", "Valor Contabil", "Conta"],
        [1152, "Compras para revenda", 1000.00, 22643],
        [1153, "Outras compras", 234.56, 22643],
    ]})
    response = TestClient(app).post("/api/v1/conferencia-fiscal/242/preview", files={
        "acumuladores": ("fiscal.xlsx", fiscal),
        "razao": ("razao.xlsx", ledger),
    })
    assert response.status_code == 200, response.text
    rows = response.json()["contas"]
    assert len(rows) == 1
    assert rows[0]["conta"] == "22643"
    assert rows[0]["acumuladores"] == "1152, 1153"
    assert rows[0]["detalhes_fiscais"] == [
        {"codigo": "1152", "descricao": "Compras para revenda", "valor": 1000.00},
        {"codigo": "1153", "descricao": "Outras compras", "valor": 234.56},
    ]
    assert rows[0]["fiscal"] == 1234.56


def test_conferencia_universal_exige_filial_quando_razao_tem_multiplas():
    fiscal, ledger = reports()
    arquivos = {"acumuladores": ("fiscal.xlsx", fiscal), "razao": ("razao.xlsx", ledger)}
    client = TestClient(app)
    indefinida = client.post("/api/v1/conferencia-fiscal/preview", files=arquivos)
    assert indefinida.status_code == 422
    assert "várias filiais" in indefinida.json()["detail"]
    escolhida = client.post(
        "/api/v1/conferencia-fiscal/preview", files=arquivos,
        data={"filial": "242", "empresa_codigo": "987"},
    )
    assert escolhida.status_code == 200, escolhida.text
    assert escolhida.json()["empresa"] == 987
    assert escolhida.json()["filial_aplicada"] == "242"
    assert escolhida.json()["contas"][0]["fiscal"] == 1234.56
    assert escolhida.json()["contas"][0]["contabil"] == 1234.56
    export = client.post(
        "/api/v1/conferencia-fiscal/exportar", files=arquivos,
        data={"filial": "242", "empresa_codigo": "987"},
    )
    assert export.status_code == 200, export.text
    assert "987_CONFERENCIA_FISCAL" in export.headers.get("content-disposition", "")
    sem_empresa = client.post(
        "/api/v1/conferencia-fiscal/preview", files=arquivos,
        data={"filial": "1408"},
    )
    assert sem_empresa.status_code == 200, sem_empresa.text
    assert sem_empresa.json()["contas"][0]["contabil"] == 999


def test_universal_ignora_codigo_informativo_no_filtro_de_filiais():
    fiscal, ledger = reports()
    response = TestClient(app).post(
        "/api/v1/conferencia-fiscal/preview",
        files={"acumuladores": ("fiscal.xlsx", fiscal), "razao": ("razao.xlsx", ledger)},
        data={"empresa_codigo": "9999"},
    )
    assert response.status_code == 422
    assert "várias filiais" in response.json()["detail"]


def test_universal_identifica_filial_quando_ha_apenas_uma():
    fiscal, ledger = reports()
    import pandas as pd
    workbook_ledger = pd.ExcelFile(io.BytesIO(ledger))
    linhas = pd.read_excel(workbook_ledger, sheet_name="Razão", header=None)
    linhas = linhas[~linhas.astype(str).apply(
        lambda row: row.str.contains("COMPRA DE MERCADORIA CF NF 2", regex=False).any(), axis=1
    )]
    arquivo = workbook({"Razão": linhas.fillna("").values.tolist()})
    response = TestClient(app).post(
        "/api/v1/conferencia-fiscal/preview",
        files={"acumuladores": ("fiscal.xlsx", fiscal), "razao": ("razao.xlsx", arquivo)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["filial_aplicada"] == "242"
    assert response.json()["contas"][0]["contabil"] == 1234.56



def _relatorios_empresa(nome_fiscal, nome_razao, razao_csv=False):
    fiscal = workbook({"Fiscal": [
        ["Empresa:", "", nome_fiscal] if nome_fiscal else ["Relatório fiscal"],
        ["ENTRADAS"], ["Codigo", "Descrição", "Valor Contabil", "Conta"],
        [1152, "Mercadorias", 1234.56, 22643],
    ]})
    if razao_csv:
        linhas = [
            f"Empresa:;;{nome_razao}",
            "Conta;Data;Lote;Histórico;Contrapartida;Débito;Crédito;Filial",
            "22643;03/08/2026;10;COMPRA DE MERCADORIA CF NF;22644;1234,56;0;242",
        ]
        return fiscal, ("\n".join(linhas)).encode("cp1252"), "Razão.csv"
    razao = workbook({"Razão": [
        ["Empresa:", "", nome_razao] if nome_razao else ["Relatório contábil"],
        ["Período:", "01/08/2026 - 31/08/2026"],
        ["Conta:", 22643.0, "", "", "", "ESTOQUE"],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        [46237, 10, "COMPRA DE MERCADORIA CF NF", 22644.0, 242, 1234.56, 0],
    ]})
    return fiscal, razao, "Razão.xlsx"


def test_empresa_reconhecida_automaticamente_em_ambos_os_relatorios():
    fiscal, razao, nome_razao = _relatorios_empresa(
        "COMERCIAL EXEMPLO LTDA", "Comercial Exemplo Ltda.",
    )
    response = TestClient(app).post("/api/v1/conferencia-fiscal/preview", files={
        "acumuladores": ("fiscal.xlsx", fiscal), "razao": (nome_razao, razao),
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["empresa_nome"] == "COMERCIAL EXEMPLO LTDA"
    assert data["empresa_fiscal"] == "COMERCIAL EXEMPLO LTDA"
    assert data["empresa_razao"] == "Comercial Exemplo Ltda."
    assert data["contas"][0]["fiscal"] == 1234.56
    assert not any("Não foi possível identificar" in aviso for aviso in data["avisos"])
    export = TestClient(app).post("/api/v1/conferencia-fiscal/exportar", files={
        "acumuladores": ("fiscal.xlsx", fiscal), "razao": (nome_razao, razao),
    })
    assert export.status_code == 200, export.text
    assert "COMERCIAL_EXEMPLO_LTDA" in export.headers["content-disposition"]


def test_empresa_reconhecida_no_razao_csv_tabular_apos_conversao():
    fiscal, razao, nome_razao = _relatorios_empresa(
        "COMERCIAL EXEMPLO LTDA", "COMERCIAL EXEMPLO LTDA", razao_csv=True,
    )
    response = TestClient(app).post("/api/v1/conferencia-fiscal/preview", files={
        "acumuladores": ("fiscal.xlsx", fiscal), "razao": (nome_razao, razao),
    })
    assert response.status_code == 200, response.text
    assert response.json()["empresa_nome"] == "COMERCIAL EXEMPLO LTDA"
    assert response.json()["contas"][0]["contabil"] == 1234.56


def test_relatorios_de_empresas_diferentes_nao_sao_comparados():
    fiscal, razao, nome_razao = _relatorios_empresa(
        "COMERCIAL ALFA LTDA", "COMERCIAL BETA LTDA",
    )
    response = TestClient(app).post("/api/v1/conferencia-fiscal/preview", files={
        "acumuladores": ("fiscal.xlsx", fiscal), "razao": (nome_razao, razao),
    })
    assert response.status_code == 422
    assert "empresas diferentes" in response.json()["detail"]
    assert "COMERCIAL ALFA" in response.json()["detail"]
    assert "COMERCIAL BETA" in response.json()["detail"]


def test_sem_nome_em_um_arquivo_exibe_origem_da_identificacao():
    fiscal, razao, nome_razao = _relatorios_empresa(
        "", "COMERCIAL EXEMPLO LTDA",
    )
    response = TestClient(app).post("/api/v1/conferencia-fiscal/preview", files={
        "acumuladores": ("fiscal.xlsx", fiscal), "razao": (nome_razao, razao),
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["empresa_nome"] == "COMERCIAL EXEMPLO LTDA"
    assert data["empresa_fiscal"] == ""
    assert data["empresa_razao"] == "COMERCIAL EXEMPLO LTDA"
    assert any("identificada pelo Razão" in aviso for aviso in data["avisos"])


def test_codigo_ou_razao_social_em_celula_empresa_e_identificado():
    from razync.conferencia_fiscal import _empresa_no_cabecalho
    assert _empresa_no_cabecalho(
        ["Empresa: 242 - COMERCIAL EXEMPLO LTDA", "", ""]
    ) == "COMERCIAL EXEMPLO LTDA"
    assert _empresa_no_cabecalho(
        ["Empresa:", "242", "", "COMERCIAL EXEMPLO LTDA"]
    ) == "COMERCIAL EXEMPLO LTDA"



def test_cabecalhos_reais_dominio_empresa_em_a1_e_razao_rotulado():
    """Formato do Resumo: razão social em A1; formato do Razão: Empresa: em A1, nome em C1."""
    nome = "COMERCIAL EXEMPLO IMPORTADORA LTDA EPP"
    fiscal = workbook({"Resumo por Acumulador": [
        [nome, None, None, None, "Página:", "1/1"],
        ["CNPJ:", None, "00000000000000"],
        ["Período:"],
        [],
        ["RESUMO POR ACUMULADOR"],
        ["ENTRADAS"],
        ["Código", "Descrição", "Vlr Contábil", "Conta"],
        [1152, "Compras mercadorias", 1234.56, 22643],
    ]})
    razao = workbook({"Razão": [
        ["Empresa:", None, nome, None, "Folha:", 1],
        ["C.N.P.J.:"],
        ["Período:", "01/08/2026 - 31/08/2026"],
        ["RAZÃO"],
        ["Conta:", 22643, "", "", "", "ESTOQUE"],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        [46237, 10, "COMPRA DE MERCADORIA CF NF", 22644, 242, 1234.56, 0],
    ]})
    response = TestClient(app).post(
        "/api/v1/conferencia-fiscal/preview",
        files={"acumuladores": ("resumo.xls.xlsx", fiscal), "razao": ("razao.xlsx", razao)},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["empresa_nome"] == nome
    assert data["empresa_fiscal"] == nome
    assert data["empresa_razao"] == nome
    assert data["contas"][0]["fiscal"] == 1234.56
    assert data["contas"][0]["contabil"] == 1234.56


def test_empresa_em_a1_diferente_do_razao_bloqueia_conferencia():
    fiscal = workbook({"Fiscal": [
        ["COMERCIAL ALFA LTDA EPP"],
        ["ENTRADAS"], ["Código", "Descrição", "Vlr Contábil", "Conta"],
        [1152, "Compras", 100, 22643],
    ]})
    razao = workbook({"Razão": [
        ["Empresa:", None, "COMERCIAL BETA LTDA EPP"],
        ["Conta:", 22643, "", "", "", "ESTOQUE"],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        [46237, 10, "COMPRA DE MERCADORIA CF NF", 22644, 242, 100, 0],
    ]})
    response = TestClient(app).post("/api/v1/conferencia-fiscal/preview", files={
        "acumuladores": ("fiscal.xlsx", fiscal), "razao": ("razao.xlsx", razao),
    })
    assert response.status_code == 422
    assert "empresas diferentes" in response.json()["detail"]


def _relatorios_com_periodo(periodo_fiscal):
    fiscal = workbook({"Resumo": [
        ["COMERCIAL PERIODO TESTE LTDA"],
        periodo_fiscal,
        ["ENTRADAS"],
        ["Código", "Descrição", "Vlr Contábil", "Conta"],
        [1152, "Mercadorias do mês", 100.0, 22643],
    ]})
    razao = workbook({"Razão": [
        ["Empresa:", "", "COMERCIAL PERIODO TESTE LTDA"],
        ["Período:", "01/07/2026 - 30/09/2026"],
        ["Conta:", 22643, "", "", "", "ESTOQUE"],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        ["30/07/2026", 1, "COMPRA DE MERCADORIA CF NF JULHO", 22644, 242, 900.0, 0],
        ["03/08/2026", 2, "COMPRA DE MERCADORIA CF NF AGOSTO", 22644, 242, 100.0, 0],
        ["02/09/2026", 3, "COMPRA DE MERCADORIA CF NF SETEMBRO", 22644, 242, 700.0, 0],
    ]})
    return {"acumuladores": ("resumo.xlsx", fiscal), "razao": ("razao.xlsx", razao)}


def test_periodo_resumo_filtra_razao_de_varios_meses_e_exportacao():
    """Somente agosto entra no total, nos detalhes, na IA e no Excel."""
    client = TestClient(app)
    files = _relatorios_com_periodo(["Período:", "01/08/2026 a 31/08/2026"])
    response = client.post("/api/v1/conferencia-fiscal/preview", files=files)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["periodo_fiscal"] == {"inicio": "01/08/2026", "fim": "31/08/2026"}
    assert result["periodo_razao"] == {"inicio": "01/07/2026", "fim": "30/09/2026"}
    assert result["periodo_aplicado"] is True
    assert result["movimentos_fora_periodo"] == 2
    assert result["contas"][0]["contabil"] == 100.0
    assert result["contas"][0]["total_conta"] == 100.0
    assert result["contas"][0]["situacao"] == "CONFERE"
    assert len(result["lancamentos"]) == 1
    assert result["lancamentos"][0]["data"] == "03/08/2026"
    assert any("2 lançamento(s)" in aviso for aviso in result["avisos"])

    export = client.post("/api/v1/conferencia-fiscal/exportar", files=files)
    assert export.status_code == 200, export.text
    movimentos = pd.read_excel(io.BytesIO(export.content), sheet_name="Todos os lançamentos")
    assert len(movimentos) == 1
    assert movimentos["DÉBITO"].sum() == 100.0


def test_periodo_resumo_na_mesma_celula_ou_colunas_distintas():
    client = TestClient(app)
    for linha in [
        ["Período: 01/08/2026 - 31/08/2026"],
        ["Período:", "01/08/2026", "31/08/2026"],
        ["Período:", pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31")],
        ["Período:", "08/2026"],
    ]:
        response = client.post(
            "/api/v1/conferencia-fiscal/preview",
            files=_relatorios_com_periodo(linha),
        )
        assert response.status_code == 200, (linha, response.text)
        report = response.json()
        assert report["periodo_fiscal"] == {"inicio": "01/08/2026", "fim": "31/08/2026"}
        assert report["contas"][0]["contabil"] == 100.0
        assert report["movimentos_fora_periodo"] == 2


def test_outra_filial_fora_do_periodo_nao_exige_escolha():
    fiscal, _ = _relatorios_com_periodo(["Período:", "01/08/2026 - 31/08/2026"]).values()
    razao = workbook({"Razão": [
        ["Período:", "01/07/2026 - 30/09/2026"],
        ["Conta:", 22643, "", "", "", "ESTOQUE"],
        ["Data", "Lote", "Histórico", "Cta.C.Part.", "Filial", "Débito", "Crédito"],
        ["30/07/2026", 1, "COMPRA DE JULHO", 22644, 1408, 900, 0],
        ["03/08/2026", 2, "COMPRA DE AGOSTO CF NF", 22644, 242, 100, 0],
    ]})
    response = TestClient(app).post(
        "/api/v1/conferencia-fiscal/preview",
        files={"acumuladores": ("fiscal.xlsx", fiscal), "razao": ("razao.xlsx", razao)},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["filial_aplicada"] == "242"
    assert report["filiais_encontradas"] == ["242"]
    assert report["contas"][0]["contabil"] == 100.0


def test_razao_sem_lancamentos_no_periodo_exibe_ausencia_sem_somar_outros_meses():
    fiscal, ledger = _relatorios_com_periodo(["Período:", "01/10/2026 - 31/10/2026"]).values()
    response = TestClient(app).post(
        "/api/v1/conferencia-fiscal/preview",
        files={"acumuladores": ("fiscal.xlsx", fiscal), "razao": ("razao.xlsx", ledger)},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["contas"][0]["situacao"] == "AUSENTE NO CONTÁBIL"
    assert report["contas"][0]["contabil"] == 0
    assert report["lancamentos"] == []
    assert report["movimentos_fora_periodo"] == 3


def test_sem_periodo_fiscal_explica_que_filtragem_nao_pode_ser_aplicada():
    response = TestClient(app).post(
        "/api/v1/conferencia-fiscal/preview",
        files=_relatorios_com_periodo(["Período:"]),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["periodo_aplicado"] is False
    assert result["movimentos_fora_periodo"] == 0
    assert any("não foi filtrado por data" in aviso for aviso in result["avisos"])

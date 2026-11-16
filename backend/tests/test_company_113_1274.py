"""Regressões para empresas 113 (Leravi) e 1274 (Auguri)."""
from unittest.mock import patch
import pandas as pd
import pytest
from app.registry import CAPABILITIES
from app import migration_services as services
from app import company_113 as leravi
from app import company_1274 as auguri

def sample(bank,account):
    return pd.DataFrame([
        {"DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-08-03"),"VALOR":-286.60,
         "DÉBITO":"","CRÉDITO":account,"HISTÓRICO":"Pago: SANDRE SOLDA"},
        {"DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-08-05"),"VALOR":949.88,
         "DÉBITO":account,"CRÉDITO":"","HISTÓRICO":"Recebido: TRANSFERENCIA"},
    ],columns=leravi.COLS)

def test_configuration_and_three_tools():
    assert CAPABILITIES[113]["banks"]=={"bradesco":"9","santander":"513"}
    assert CAPABILITIES[1274]["banks"]=={"banco_brasil":"8","itau":"508","santander":"513"}
    assert set(CAPABILITIES[113]["tools"])==set(CAPABILITIES[1274]["tools"])=={
        "modelo_dominio","conferencia_extrato","base_inteligente"}
    assert services.accounts(113)["bradesco"]=="9"
    assert services.accounts(1274)["banco_brasil"]=="8"

def test_financial_enrichment_only_unique_date_value_nature():
    finance=pd.DataFrame([
        {"Tipo":"Pagar","Nome Fantasia":"SANDRE SOLDA","Nota Fiscal":18729,
         "Valor Pago":286.60,"Data Pagto.":pd.Timestamp("2026-08-03")},
        {"Tipo":"Receber","Nome Fantasia":"IND. E COM. DE COS.","Nota Fiscal":2396,
         "Valor Pago":949.88,"Data Pagto.":pd.Timestamp("2026-08-05")},
    ])
    with patch("pandas.read_excel",return_value=finance):
        result=leravi.enrich_financial(sample("BANCO BRADESCO","9"),b"fake")
    assert "NF: 18729" in result.iloc[0]["HISTÓRICO"]
    assert "NF: 2396" in result.iloc[1]["HISTÓRICO"]
    assert result["VALOR"].tolist()==[-286.60,949.88]
    finance.loc[2]=dict(finance.iloc[0])
    with patch("pandas.read_excel",return_value=finance):
        result=leravi.enrich_financial(sample("BANCO BRADESCO","9"),b"fake")
    assert "NF:" not in result.iloc[0]["HISTÓRICO"]
    # Uma mesma movimentação bancária repetida não pode absorver a NF
    # apenas na primeira ocorrência de data e valor iguais.
    with patch("pandas.read_excel",return_value=finance.iloc[:2]):
        doubled=pd.concat([sample("BANCO BRADESCO","9").iloc[[0]]]*2,ignore_index=True)
        result=leravi.enrich_financial(doubled,b"fake")
    assert all("NF:" not in text for text in result["HISTÓRICO"])

def test_113_workflow_isolates_banks():
    with patch.dict(leravi.READERS,{"bradesco":lambda _:sample("BANCO BRADESCO","9")}),\
         patch("app.excel.gerar_modelo_abas",return_value=b"book") as exporter:
        out,name=leravi.workflow_113({"bradesco":[("aug.pdf",b"%PDF")]},{})
    assert out==b"book" and "113" in name
    assert list(exporter.call_args.args[0])==["Bradesco"]

def test_1274_workflow_preserves_each_bank():
    with patch.dict(auguri.READERS,{
        "banco_brasil":lambda _:sample("BANCO DO BRASIL","8"),
        "itau":lambda _:sample("BANCO ITAÚ","508"),
        "santander":lambda _:sample("BANCO SANTANDER","513")}),\
        patch("app.excel.gerar_modelo_abas",return_value=b"book") as exporter:
        files={key:[("ago.pdf",b"%PDF")] for key in auguri.READERS}
        out,name=auguri.workflow_1274(files,{})
    assert out==b"book" and "1274" in name
    sheets=exporter.call_args.args[0]
    assert list(sheets)==["Banco do Brasil","Itaú","Santander"]
    assert sheets["Itaú"]["CRÉDITO"].iloc[0]=="508"
    assert sheets["Santander"]["DÉBITO"].iloc[1]=="513"

def test_invalid_file_type_rejected():
    with pytest.raises(ValueError,match="PDF"):
        services.statement(113,"bradesco",b"hi","falso.xlsx")
    with pytest.raises(ValueError,match="PDF"):
        services.statement(1274,"itau",b"hi","falso.xlsx")


@pytest.mark.parametrize("heading", [
    "DOC/TED INTERNET",
    "CONTA DE TELEFONE",
    "TITULO DE CAPITALIZACAO",
    "TRANSF.AUTORIZ.ENTRE C/C",
    "PAGTO ELETRON COBRANCA",
    "RENTAB.INVEST FACILCRED*",
])
def test_leravi_bradesco_bank_headings(heading):
    assert leravi.is_bank_history_heading(heading)


@pytest.mark.parametrize("description", [
    "SANDRE SOLDA GASES INDUSTRIAIS",
    "CLARO S/A - MOVEL-163817823",
    "CAPITALIZACAO 1236 0050039329-7",
])
def test_leravi_beneficiaries_are_not_transaction_headings(description):
    assert not leravi.is_bank_history_heading(description)


def test_bb_auguri_pix_at_page_break_is_not_discarded():
    """Regressão do PDF de agosto: PIX de 100 mil no fim da página 1."""
    import fitz

    heading = (
        "Extrato de Conta Corrente",
        "Cliente AUGURI S SAUDE LTDA",
        "Agência: 3131-3    Conta: 24073-7",
        "Lançamentos", "Dia", "Lote", "Documento", "Histórico", "Valor",
    )
    pages = (
        (
            "0,00 (+)", "31/07/2026", "Saldo Anterior",
            "100.000,00 (-)", "06/08/2026", "13105", "80602",
            "Pix - Enviado", "06/08 08:42 Auguri Solucoes Em Saude",
        ),
        (
            "100.000,00 (+)", "06/08/2026", "9903",
            "BB Rende Fácil", "Rende Facil",
            "0,00 (+)", "00/00/0000", "13105", "Saldo do dia",
            "0,00 (+)", "31/08/2026", "S A L D O",
        ),
    )
    document = fitz.open()
    for body in pages:
        page = document.new_page()
        page.insert_text((55, 55), "\n".join(heading + body), fontsize=9)
    pdf = document.tobytes()
    document.close()

    records = auguri.read_banco_brasil(pdf)
    assert len(records) == 2
    assert records["VALOR"].tolist() == [-100000.0, 100000.0]
    assert "Pix - Enviado" in records.iloc[0]["HISTÓRICO"]
    assert "BB Rende Fácil" in records.iloc[1]["HISTÓRICO"]
    assert records["CRÉDITO"].tolist() == ["8", ""]
    assert records["DÉBITO"].tolist() == ["", "8"]


def test_leravi_bradesco_header_extracted_from_original_pdf_layout():
    """O PDF Bradesco separa os rótulos dos valores e repete o par no resumo."""
    header = (
        "Extrato de: Ag: \n | CC: \n"
        "01/08/2026 01/09/2026\n1154\n0165499-3 | Entre\ne\n"
        "Agência | Conta\n01154 | 0165499-3\n"
        "Data Lançamento Dcto. Crédito (R$) Débito (R$) Saldo (R$)"
    )
    assert leravi.verify_bradesco_account(header)
    assert leravi.verify_bradesco_account(
        "Extrato de: Ag: | CC: 1154 0165499-3 | Entre agosto"
    )
    assert not leravi.verify_bradesco_account(
        header.replace("0165499-3", "0165499-4")
    )
    assert not leravi.verify_bradesco_account(
        header.replace("01154", "01155").replace("1154", "1155")
    )
    assert not leravi.verify_bradesco_account(
        "Documento diverso, agência 1154 e conta 0165499-3"
    )

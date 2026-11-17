"""Regressões do extrato financeiro Itaú da empresa 1328."""
from unittest.mock import patch

import pandas as pd
import pytest

from app.company_1328 import read_statement, workflow_1328, OLE_MAGIC, ZIP_MAGIC
from app.registry import CAPABILITIES
from app.migration_services import accounts, statement


def _sheet():
    return pd.DataFrame([
        ["ICROI - Extrato Financeiro", None, None, None, None, None, None],
        ["A&Z INDUSTRIA, COMERCIO E SERVICOS LTDA",None,None,None,None,None,None],
        ["Periodo de 01/10/2026 ate 31/10/2026 - Banco 341 - BANCO ITAU",None,None,None,None,None,None],
        ["Data","Histórico",None,None,"Nº Documento","CNPJ",None,"Débito","Crédito","Saldo"],
        [None,None,None,None,None,None,None,None,"Saldo Anterior :",490357.64],
        [46296.0,None,52.0,"PAGAMENTO FORNECEDOR","00001234-1","",None,1234.56,0,489123.08],
        [46297.0,None,73.0,"RECEBIMENTO CLIENTE","0000789","",None,0,2000.12,491123.20],
        [None,None,None,None,None,None,None,None,None,"491123,20"],
    ])


def test_roles_bank_and_account():
    assert accounts(1328)=={"itau":"508"}
    assert set(CAPABILITIES[1328]["tools"])=={
        "modelo_dominio","conferencia_extrato","base_inteligente"}
    assert CAPABILITIES[1328]["roles"][0]["accept"]==".xls,.xlsx"


@pytest.mark.parametrize("magic", [OLE_MAGIC, ZIP_MAGIC])
def test_statement_reads_real_file_magic_not_extension(magic):
    with patch("pandas.read_excel",return_value={"Extrato":_sheet()}) as loader:
        df=read_statement(magic+b"fixture")
    assert df["DATA"].dt.strftime("%d/%m/%Y").tolist()==["01/10/2026","02/10/2026"]
    assert df["VALOR"].tolist()==[-1234.56,2000.12]
    assert df["DÉBITO"].tolist()==["","508"]
    assert df["CRÉDITO"].tolist()==["508",""]
    assert df["HISTÓRICO"].tolist()==[
        "Pago: PAGAMENTO FORNECEDOR | Doc: 00001234-1",
        "Recebido: RECEBIMENTO CLIENTE | Doc: 0000789",
    ]
    engine=loader.call_args.kwargs["engine"]
    assert engine==("xlrd" if magic==OLE_MAGIC else "openpyxl")


def test_excel_com_extension_xlsx_mas_formato_xls():
    with patch("pandas.read_excel",return_value={"Extrato":_sheet()}):
        parsed=statement(1328,"itau",OLE_MAGIC+b"fixture","extrato.xlsx")
    assert len(parsed)==2


def test_debit_credit_same_row_invalid():
    sheet=_sheet()
    sheet.iloc[5,8]="2,00"
    with patch("pandas.read_excel",return_value={"Extrato":sheet}):
        with pytest.raises(ValueError,match="Débito e Crédito"):
            read_statement(OLE_MAGIC+b"fixture")


def test_real_dates_and_multiple_competences():
    sheet=_sheet()
    sheet.iloc[5,0]=46300  # Excel serial
    with patch("pandas.read_excel",return_value={"Extrato":sheet}):
        df=read_statement(OLE_MAGIC+b"fixture")
    assert df.iloc[0]["DATA"]==pd.Timestamp("1899-12-30")+pd.Timedelta(days=46300)


def test_workflow_exports_one_sheet_and_prevents_duplicate_month():
    with patch("pandas.read_excel",return_value={"Extrato":_sheet()}),\
         patch("app.excel.gerar_modelo_abas",return_value=b"workbook") as generator:
        result,name=workflow_1328({"itau":[("outubro.xlsx",OLE_MAGIC+b"fixture")]},{})
        assert result==b"workbook" and "1328" in name
        sheets=generator.call_args.args[0]
        assert list(sheets)==["Itaú"]
        assert sheets["Itaú"]["VALOR"].tolist()==[-1234.56,2000.12]
        with pytest.raises(ValueError,match="competência repetida"):
            workflow_1328({"itau":[("a.xls",OLE_MAGIC+b"fixture"),
                                   ("b.xlsx",OLE_MAGIC+b"fixture")]},{})


def test_original_file_has_saldo_anterior_in_credit_column():
    """A linha 10 não é crédito; o nome do lançamento está em D, não em B."""
    with patch("pandas.read_excel",return_value={"Extrato":_sheet()}):
        result=read_statement(OLE_MAGIC+b"fixture")
    assert len(result)==2
    assert "Saldo Anterior" not in " ".join(result["HISTÓRICO"])
    assert result.iloc[0]["HISTÓRICO"]=="Pago: PAGAMENTO FORNECEDOR | Doc: 00001234-1"
    assert result.iloc[1]["HISTÓRICO"]=="Recebido: RECEBIMENTO CLIENTE | Doc: 0000789"


def test_saldo_e_apenas_conferencia_nao_lancamento():
    sheet=_sheet()
    with patch("pandas.read_excel",return_value={"Extrato":sheet}):
        df=read_statement(OLE_MAGIC+b"fixture")
    assert len(df)==2
    assert round(df["VALOR"].sum(),2)==765.56
    assert all("Saldo" not in h for h in df["HISTÓRICO"])


def test_divergencia_de_saldo_impede_exportacao_incompleta():
    sheet=_sheet()
    sheet.iloc[5,9]=489124.08  # R$ 1 a mais do que o saldo correto.
    with patch("pandas.read_excel",return_value={"Extrato":sheet}):
        with pytest.raises(ValueError,match="saldo divergente na linha 6"):
            read_statement(OLE_MAGIC+b"fixture")

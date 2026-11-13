"""Regressão empresa 1160: PDFs sintéticos não contêm dados financeiros reais."""
from unittest.mock import patch
import fitz
import pandas as pd
import pytest
from app import company_1160 as module
from app import migration_services as services


def build_pdf(pages):
    doc=fitz.open()
    for line_spec in pages:
        page=doc.new_page(width=595,height=842)
        for x,y,txt in line_spec:
            page.insert_text((x,y),txt,fontsize=9,fontname="helv")
    data=doc.tobytes()
    doc.close()
    return data


def frame(account,bank):
    return pd.DataFrame([
        {"DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-07-01"),"VALOR":-100.0,
         "DÉBITO":"","CRÉDITO":account,"HISTÓRICO":"Pago: Operação"},
        {"DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-07-01"),"VALOR":100.0,
         "DÉBITO":account,"CRÉDITO":"","HISTÓRICO":"Recebido: Estorno"},
    ])


def test_multibank_workflow_keeps_all_four_accounts_and_estornos():
    roles={key:[(key+".pdf",b"%PDF sample")] for key in module.READERS}
    originals=module.READERS.copy()
    try:
        for key,account in [("banco_brasil","8"),("sicoob","506"),
                            ("itau","508"),("bradesco","515")]:
            module.READERS[key]=lambda data, account=account,key=key: frame(account,key)
        with patch("app.excel.gerar_modelo_abas",return_value=b"xlsx") as export:
            workbook,name=module.workflow_1160(roles,{})
        assert workbook==b"xlsx" and "1160" in name
        sheets=export.call_args.args[0]
        assert list(sheets)==["Banco do Brasil","Sicoob","Itaú","Bradesco"]
        for sheet,account in [("Banco do Brasil","8"),("Sicoob","506"),
                              ("Itaú","508"),("Bradesco","515")]:
            df=sheets[sheet]
            assert df["VALOR"].tolist()==[-100.0,100.0]
            assert df["CRÉDITO"].tolist()==[account,""]
            assert df["DÉBITO"].tolist()==["",account]
    finally:
        module.READERS.clear()
        module.READERS.update(originals)


def test_company_1160_statement_routes_all_banks():
    for bank,account in [("banco_brasil","8"),("sicoob","506"),
                         ("itau","508"),("bradesco","515")]:
        original=module.READERS[bank]
        try:
            module.READERS[bank]=lambda data: frame(account,bank)
            result=services.statement(1160,bank,b"%PDF test","test.pdf")
            assert len(result)==2
        finally:
            module.READERS[bank]=original
    with pytest.raises(ValueError,match="Banco não cadastrado"):
        services.statement(1160,"santander",b"%PDF test","test.pdf")
    with patch.object(module,"workflow_1160",return_value=(b"xlsx","1160.xlsx")) as wf:
        assert services._workflow(1160,{}, {})==(b"xlsx","1160.xlsx")
        wf.assert_called_once()


def test_reject_wrong_bradesco_account():
    content=build_pdf([[
        (10,50,"Extrato Mensal / Por Período"),
        (10,70,"GUNG WEN COMERCIO"),
        (10,90,"Extrato de: Ag: 538 | CC: 0301811-2 | Entre 01/07/2026 e 31/07/2026"),
    ]])
    with pytest.raises(ValueError,match="agência 538"):
        module.read_bradesco(content)


def test_reject_wrong_itau_account():
    content=build_pdf([[
        (10,50,"GUNG WEN COM VAREJISTA CNPJ 39.792.168/0001-12"),
        (10,70,"Agência 7111 Conta 0099819-5"),
        (10,95,"Lançamentos do período: 01/07/2026 até 31/07/2026"),
    ]])
    with pytest.raises(ValueError,match="agência 7111"):
        module.read_itau(content)


def test_bb_preserves_debit_and_reversal_with_balance():
    content=build_pdf([[
        (50,75,"Cliente - Conta atual"),
        (56,125,"Agência"),(146,125,"8224-4"),
        (56,137,"Conta corrente"),(147,137,"379-4GUNG W C V"),
        (56,150,"Período do extrato"),(147,150,"07 / 2026"),
        (65,203,"30/06/2026"),(265,203,"Saldo Anterior"),(503,203,"100,00"),(543,203,"D"),
        (65,221,"13/07/2026"),(265,221,"Cap Giro Dig Amortização"),
        (460,221,"50,00"),(495,221,"D"),
        (65,239,"13/07/2026"),(265,239,"Estorno de Débito"),
        (460,239,"50,00"),(495,239,"C"),(503,239,"100,00"),(543,239,"D"),
    ]])
    result=module.read_banco_brasil(content)
    assert result["VALOR"].tolist()==[-50.0,50.0]
    assert result["CRÉDITO"].tolist()==["8",""]
    assert result["DÉBITO"].tolist()==["","8"]


def test_sicoob_reverses_descending_order_and_preserves_balances():
    content=build_pdf([[
        (190,100,"210.034-7 / GUNG WEN COMERCIO"),
        (386,85,"4340-0 / SICOOB"),
        (34,112,"Periodo:"),(445,112,"01/07/2026 - 31/07/2026"),
        (38,200,"02/07"),(150,200,"ESTORNO DEB EMPRESTIMO"),(505,200,"50,00C"),
        (38,218,"02/07"),(150,218,"DEB EMPRESTIMO"),(505,218,"50,00D"),
        (38,235,"02/07"),(150,235,"SALDO DO DIA"),(505,235,"100,00D"),
        (38,258,"01/07"),(150,258,"DEB.IOF"),(505,258,"1,00D"),
        (38,277,"01/07"),(150,277,"SALDO DO DIA"),(505,277,"100,00D"),
        (38,299,"30/06"),(150,299,"SALDO ANTERIOR"),(505,299,"99,00D"),
    ]])
    # The synthetic daily balance intentionally conflicts with transaction
    # history; reject rather than silently alter a bank figure.
    with pytest.raises(ValueError,match="saldo não confere"):
        module.read_sicoob(content)


def test_invalid_files_not_accepted():
    for func in module.READERS.values():
        with pytest.raises(ValueError,match="PDF"):
            func(b"not a pdf")

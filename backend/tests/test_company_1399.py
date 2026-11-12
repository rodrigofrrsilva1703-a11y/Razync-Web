"""Empresa 1399: testes sintéticos; não incluir extratos de clientes no repositório."""
from io import BytesIO
from unittest.mock import patch
import fitz
import pandas as pd
import pytest

from app.company_1399 import workflow_1399
from app import migration_services as services
from app.itau_1399 import read_statement as read_itau
from app.bradesco_1399 import read_statement as read_bradesco


def pdf_lines(lines):
    doc=fitz.open()
    page=doc.new_page(width=595,height=842)
    for x,y,text in lines:
        page.insert_text((x,y),text,fontsize=9,fontname="helv")
    data=doc.tobytes()
    doc.close()
    return data


def test_itau_1399_synthetic_checks_daily_balances_and_repeated_values():
    pdf=pdf_lines([
        (35,50,"JETMAQ COMERCIAL DE MAQUINAS  CNPJ 27.514.567/0001-32"),
        (430,65,"7111 Conta 0097478-3"),
        (35,90,"Lançamentos do período: 01/08/2026 até 31/08/2026"),
        (35,125,"31/07/2026"),(89,125,"SALDO ANTERIOR"),(520,125,"100,00"),
        (35,145,"03/08/2026"),(89,145,"PIX ENVIADO"),(225,145,"FORNECEDOR TESTE"),
        (470,145,"-25,00"),
        (35,160,"03/08/2026"),(89,160,"SAQUE DIN ATM"),(470,160,"-10,00"),
        (35,175,"03/08/2026"),(89,175,"SAQUE DIN ATM"),(470,175,"-10,00"),
        (35,190,"03/08/2026"),(89,190,"SALDO TOTAL DISPONIVEL DIA"),(520,190,"55,00"),
    ])
    frame=read_itau(pdf)
    assert len(frame)==3
    assert frame["VALOR"].tolist()==[-25,-10,-10]
    assert frame["CRÉDITO"].tolist()==["508"]*3
    assert "FORNECEDOR TESTE" in frame.iloc[0]["HISTÓRICO"]


def test_itau_1399_rejects_inconsistent_balance():
    pdf=pdf_lines([
        (35,50,"JETMAQ COMERCIAL DE MAQUINAS  CNPJ 27.514.567/0001-32"),
        (430,65,"7111 Conta 0097478-3"),
        (35,90,"Lançamentos do período: 01/08/2026 até 31/08/2026"),
        (35,125,"31/07/2026"),(89,125,"SALDO ANTERIOR"),(520,125,"100,00"),
        (35,145,"03/08/2026"),(89,145,"PIX ENVIADO"),(470,145,"-25,00"),
        (35,160,"03/08/2026"),(89,160,"SALDO TOTAL DISPONIVEL DIA"),(520,160,"76,00"),
    ])
    with pytest.raises(ValueError,match="Saldo"):
        read_itau(pdf)


def test_bradesco_1399_rejects_another_account():
    pdf=pdf_lines([
        (40,70,"Extrato de: Ag: 1795 | CC: 0338388-2 | Entre 01/08/2026 e 31/08/2026"),
        (40,100,"Data Lançamento Dcto. Crédito (R$) Débito (R$) Saldo (R$)"),
    ])
    with pytest.raises(ValueError,match="Agência ou conta"):
        read_bradesco(pdf)


def fake_rows(account,bank):
    return pd.DataFrame([
        {"DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-08-03"),"VALOR":-100.0,
         "DÉBITO":"","CRÉDITO":account,"HISTÓRICO":"Pago: PAGAMENTO TESTE"},
        {"DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-08-03"),"VALOR":-100.0,
         "DÉBITO":"","CRÉDITO":account,"HISTÓRICO":"Pago: PAGAMENTO TESTE"},
    ])


def test_1399_organizes_banks_separately_and_keeps_duplicates():
    from app import company_1399
    with patch.object(company_1399,"read_itau",return_value=fake_rows("508","BANCO ITAÚ")), \
         patch.object(company_1399,"read_bradesco",return_value=fake_rows("9","BANCO BRADESCO")), \
         patch("app.excel.gerar_modelo_abas",return_value=b"workbook") as export:
        book,name=workflow_1399({
            "itau":[("itau.pdf",b"%PDF ita")],
            "bradesco":[("bradesco.PDF",b"%PDF bra")]},{})
    assert book==b"workbook"
    assert "1399" in name
    sheets=export.call_args.args[0]
    assert list(sheets)==["Itaú","Bradesco"]
    assert len(sheets["Itaú"])==2
    assert len(sheets["Bradesco"])==2
    assert sheets["Itaú"]["CRÉDITO"].tolist()==["508","508"]
    assert sheets["Bradesco"]["CRÉDITO"].tolist()==["9","9"]


def test_1399_statement_dispatch_and_filter_account():
    from app import itau_1399,bradesco_1399
    with patch.object(itau_1399,"read_statement",return_value=fake_rows("508","BANCO ITAÚ")) as reader:
        services.statement(1399,"itau",b"%PDF","itau.pdf")
        reader.assert_called_once()
    with patch.object(bradesco_1399,"read_statement",return_value=fake_rows("9","BANCO BRADESCO")) as reader:
        services.statement(1399,"bradesco",b"%PDF","bra.pdf")
        reader.assert_called_once()
    with pytest.raises(ValueError,match="Banco não cadastrado"):
        services.statement(1399,"caixa",b"%PDF","caixa.pdf")
    with patch.object(company_1399,"workflow_1399",return_value=(b"xlsx","1399.xlsx")):
        assert services._workflow(1399,{}, {})==(b"xlsx","1399.xlsx")

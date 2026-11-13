"""Empresa 1187: testes sintéticos; documentos de clientes não entram no GitHub."""
from datetime import date
from unittest.mock import patch
import pandas as pd
import pytest
from app import company_1187 as company


def frame(rows):
    return pd.DataFrame([{
        "DESCRIÇÃO":"BANCO INTER","DATA":pd.Timestamp(day),"VALOR":value,
        "DÉBITO":"505" if value>0 else "","CRÉDITO":"505" if value<0 else "",
        "HISTÓRICO":("Recebido: " if value>0 else "Pago: ")+name,
    } for day,value,name in rows],columns=company.COLUNAS)


def test_ocr_text_recognizes_daily_totals_and_keeps_date():
    text="""Banco Inter CPF/CNPJ 41.571.777/0001-93 Conta: 13060608-1
Período: 01/08/2026 a 31/08/2026
Saldo total Saldo disponível
3 de Agosto de 2026 Saldo do dia: R$ 1.200,00
Pix enviado: "FORNECEDOR" -R$ 100,00 R$ 1.200,00
7 de Agosto de 2026 Saldo do dia: R$ 1.210,00
Resgate: "CDB" R$ 10,00 R$ 1.210,00
"""
    parsed=company.parse_text(text)
    assert len(parsed)==2
    assert [r["CENTAVOS"] for r in parsed]==[-10000,1000]
    assert parsed[-1]["SALDO"]==121000
    assert parsed[0]["DATA"]==date(2026,8,3)


def test_ocr_must_reject_bad_balance():
    text="""Banco Inter CPF/CNPJ 41.571.777/0001-93 Conta: 13060608-1
Período: 01/08/2026 a 31/08/2026
Saldo total Saldo disponível
3 de Agosto de 2026 Saldo do dia: R$ 1.200,00
Pix enviado: "FORNECEDOR" -R$ 100,00 R$ 1.200,00
7 de Agosto de 2026 Saldo do dia: R$ 1.215,00
Resgate: "CDB" R$ 10,00 R$ 1.215,00
"""
    with pytest.raises(ValueError,match="Saldo"):
        company.parse_text(text)


def test_enrichment_unique_same_day_and_one_day_and_no_duplicates():
    entries=[
        {"DATA":date(2026,8,3),"CENTAVOS":-5000000,"SALDO":3744987,"HISTÓRICO":"PIX enviado"},
        {"DATA":date(2026,8,19),"CENTAVOS":-1050000,"SALDO":2694987,"HISTÓRICO":"Aplicação"},
    ]
    ledger=[
        {"DATA":date(2026,8,3),"CENTAVOS":-5000000,"HISTÓRICO":"Retirada Pn","LINHA":4},
        {"DATA":date(2026,8,18),"CENTAVOS":-1050000,"HISTÓRICO":"Investimento","LINHA":8},
    ]
    with patch.object(company,"extract_text",return_value="text"),\
         patch.object(company,"parse_text",return_value=entries),\
         patch.object(company,"read_auxiliary",return_value=(ledger,8745020)):
        result,audit,opening_sheet,opening_bank=company.enrich(b"%PDF",b"xlsx")
    assert len(result)==2
    assert result["HISTÓRICO"].tolist()==["Pago: Retirada Pn","Pago: Investimento"]
    assert result["DATA"].dt.strftime("%d/%m/%Y").tolist()==["03/08/2026","19/08/2026"]
    assert opening_sheet-opening_bank==33
    assert (audit["STATUS"].str.contains("Identificado")).all()


def test_workflow_requires_two_documents_and_routes_1187():
    from app.migration_services import _workflow,statement
    with pytest.raises(ValueError,match="extrato Banco Inter PDF e a planilha"):
        company.workflow_1187({"extrato":[("a.pdf",b"%PDF")]},{})
    with patch.object(company,"workflow_1187",return_value=(b"excel","result.xlsx")) as processor:
        assert _workflow(1187,{"extrato":[],"planilha":[]},{})==(b"excel","result.xlsx")
        processor.assert_called_once()
    with patch.object(company,"read_statement",return_value=frame([
        ("2026-08-03",-50000.0,"Retirada")])) as reader:
        statement(1187,"inter",b"PDF","extrato.pdf")
        reader.assert_called_once()
    with pytest.raises(ValueError,match="extrato Banco Inter"):
        statement(1187,"itau",b"PDF","extrato.pdf")

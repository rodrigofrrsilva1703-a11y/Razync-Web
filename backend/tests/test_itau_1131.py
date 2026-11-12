"""1131 — documentos artificiais de teste; nenhuma informação de clientes é gravada no Git."""
from datetime import date
from io import BytesIO
from unittest.mock import patch

import fitz
import pandas as pd
import pytest

from app.itau_1131 import read_auxiliary, read_bank, enrich
from app.migration_services import _workflow, statement


def synthetic_pdf(lines, width=595, height=842):
    doc = fitz.open()
    page = doc.new_page(width=width,height=height)
    for x,y,text in lines:
        page.insert_text((x,y),text,fontname="helv",fontsize=9)
    payload = doc.tobytes()
    doc.close()
    return payload


def bank_frame(records):
    return pd.DataFrame([{
        "DESCRIÇÃO":"BANCO ITAÚ","DATA":pd.Timestamp(day),"VALOR":amount,
        "DÉBITO":"508" if amount>0 else "","CRÉDITO":"508" if amount<0 else "",
        "HISTÓRICO":("Recebido: " if amount>0 else "Pago: ")+history,
    } for day,amount,history in records])


def test_bank_extracts_movements_and_balances_without_saldo_rows():
    pdf=synthetic_pdf([
        (35,40,"COTAS PREMIADAS CNPJ TESTE Agência 0074 Conta 0099705-7"),
        (35,75,"Lançamentos do período: 01/08/2026 até 31/08/2026"),
        (35,130,"31/07/2026"),(91,130,"SALDO ANTERIOR"),(477,130,"-100,00"),
        (35,147,"03/08/2026"),(91,147,"PAGAMENTOS"),(477,147,"-65,00"),
        (35,164,"03/08/2026"),(91,164,"SALDO TOTAL DISPONÍVEL DIA"),(477,164,"-165,00"),
        (35,184,"31/08/2026"),(91,184,"SALDO EM CONTA CORRENTE"),(477,184,"-165,00"),
    ])
    result,period=read_bank(pdf)
    assert period==(2026,8)
    assert result["VALOR"].tolist()==[-65.0]
    assert result.iloc[0]["CRÉDITO"]=="508"


def test_bank_rejects_wrong_account_and_missing_balance():
    pdf=synthetic_pdf([(35,40,"COTAS PREMIADAS Agência 0074 Conta 000000-0")])
    with pytest.raises(ValueError,match="agência 0074"):
        read_bank(pdf)


def test_auxiliary_ignores_header_balance_and_reads_debit_credit():
    aux=synthetic_pdf([
        (63,95,"01/ago"),(210,95,"Saldo Reiscon"),
        (424,95,"111.152,63"),(530,95,"410,77"),
        (68,125,"Data"),(213,125,"Descrição"),(420,125,"Debito"),(520,125,"Credito"),
        (63,162,"05/ago"),(210,162,"IPTU"),(425,162,"1.167,91"),(529,162,"0,00"),
        (63,181,"27/ago"),(210,181,"APORTES"),(425,181,"0,00"),(529,181,"22.700,00"),
    ],width=842,height=596)
    rows=read_auxiliary(aux,(2026,8))
    assert len(rows)==2
    assert rows[0]["cents"]==-116791
    assert rows[1]["cents"]==2270000


def test_enrich_replaces_unique_exact_and_one_day_difference_only():
    b=bank_frame([
        ("2026-08-03",-165.0,"TAR CONTR/RENOV CTA GAR"),
        ("2026-08-04",-114.56,"IOF"),
        ("2026-08-05",-1167.91,"PAGAMENTOS PM SAO PAULO"),
        ("2026-08-17",-81.24,"PAGAMENTOS SABESP"),
        ("2026-08-17",-51.53,"PAGAMENTOS ENEL"),
        ("2026-08-27",22700.0,"RECEBIMENTOS R E"),
    ])
    a=[
        {"date":date(2026,8,3),"cents":-16500,"history":"taxa bancaria"},
        {"date":date(2026,8,3),"cents":-11456,"history":"iof"},
        {"date":date(2026,8,5),"cents":-116791,"history":"IPTU S BERNARDO"},
        {"date":date(2026,8,17),"cents":-8124,"history":"pgto agua apto 04"},
        {"date":date(2026,8,17),"cents":-5224,"history":"pgto ENEL"},
        {"date":date(2026,8,27),"cents":2270000,"history":"APORTES"},
        {"date":date(2026,8,27),"cents":2270000,"history":"APORTES"},
    ]
    with patch("app.itau_1131.read_bank",return_value=(b,(2026,8))), \
         patch("app.itau_1131.read_auxiliary",return_value=a):
        enriched,audit=enrich(b"statement",b"aux")
    assert len(enriched)==len(b)
    assert enriched["VALOR"].tolist()==b["VALOR"].tolist()
    assert enriched["DATA"].tolist()==b["DATA"].tolist()
    assert enriched["HISTÓRICO"].tolist()==[
        "Pago: taxa bancaria","Pago: iof","Pago: IPTU S BERNARDO",
        "Pago: pgto agua apto 04","Pago: PAGAMENTOS ENEL","Recebido: RECEBIMENTOS R E"
    ]
    assert (audit["STATUS"]=="Correspondência exata").sum()==3
    assert (audit["STATUS"]=="Data auxiliar ±1 dia; valor único").sum()==1
    assert (audit["STATUS"].str.contains("revisão")).sum()==2


def test_company_1131_routes_to_specialized_processing():
    with patch("app.itau_1131.workflow_1131",return_value=(b"xlsx","result.xlsx")) as processor:
        assert _workflow(1131,{"extrato":[],"auxiliar":[]},{})==(b"xlsx","result.xlsx")
        processor.assert_called_once()
    with patch("app.itau_1131.read_bank",return_value=(bank_frame([
        ("2026-08-05",-100,"PAGAMENTO")]),(2026,8))) as parser:
        statement(1131,"itau",b"pdf","extrato.pdf")
        parser.assert_called_once()


def test_company_1131_requires_two_pdf_files():
    from app.itau_1131 import workflow_1131
    with pytest.raises(ValueError,match="um extrato Itaú PDF e um documento auxiliar"):
        workflow_1131({"extrato":[("a.pdf",b"pdf")]},{})

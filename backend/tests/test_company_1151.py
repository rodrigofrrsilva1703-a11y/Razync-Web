"""MRI Service 1151: regression tests without storing customer PDFs in the repo."""
from unittest.mock import patch

import pandas as pd
import pytest

from app.company_1151 import workflow_1151, read_itau, read_nubank
from app.migration_services import _workflow, statement


def bank_rows(account, bank, rows):
    return pd.DataFrame([{
        "DESCRIÇÃO":bank,"DATA":pd.Timestamp(day),"VALOR":val,
        "DÉBITO":account if val>0 else "", "CRÉDITO":account if val<0 else "",
        "HISTÓRICO":("Recebido: " if val>0 else "Pago: ")+history,
    } for day,val,history in rows])


def test_workflow_uses_two_banks_and_excludes_september_by_default():
    itau=bank_rows("508","BANCO ITAÚ",[
        ("2026-08-04",-2.25,"IOF"),("2026-08-10",5000,"BOLETOS RECEBIDOS")])
    nubank=bank_rows("506","NUBANK",[
        ("2026-08-06",234.69,"Crédito"),("2026-08-21",-1400,"Transferência"),
        ("2026-09-03",-56.47,"ENEL")])
    with patch("app.company_1151.read_itau",return_value=itau) as i, \
         patch("app.company_1151.read_nubank",return_value=nubank) as n, \
         patch("app.excel.gerar_modelo_abas",return_value=b"excel") as export:
        output, filename=workflow_1151(
            {"itau":[("itau.pdf",b"%PDF i")],"nubank":[("nu.pdf",b"%PDF n")]},{})
    assert output==b"excel"
    assert "1151" in filename
    pages=export.call_args.args[0]
    assert list(pages)==["Itaú","Nubank"]
    assert pages["Itaú"]["VALOR"].tolist()==[-2.25,5000]
    assert pages["Nubank"]["VALOR"].tolist()==[234.69,-1400]
    i.assert_called_once_with(b"%PDF i")
    n.assert_called_once_with(b"%PDF n")


def test_workflow_explicit_period_can_select_september():
    nubank=bank_rows("506","NUBANK",[
        ("2026-08-31",-10,"Mercado Pago"),("2026-09-03",-56.47,"ENEL")])
    with patch("app.company_1151.read_nubank",return_value=nubank), \
         patch("app.excel.gerar_modelo_abas",return_value=b"excel") as export:
        workflow_1151({"nubank":[("nu.pdf",b"%PDF n")]},
                      {"data_inicial":"2026-09-01","data_final":"2026-09-30"})
    result=export.call_args.args[0]["Nubank"]
    assert result["VALOR"].tolist()==[-56.47]


def test_workflow_rejects_duplicate_or_wrong_formats():
    with pytest.raises(ValueError,match="PDF por competência"):
        workflow_1151({"itau":[("a.pdf",b"pdf"),("b.pdf",b"pdf")]},{})
    with pytest.raises(ValueError,match="extrato PDF completo"):
        workflow_1151({"nubank":[("nu.xlsx",b"spreadsheet")]},{})


def test_specialized_statement_dispatch():
    bank=bank_rows("508","BANCO ITAÚ",[("2026-08-04",-2.25,"IOF")])
    with patch("app.company_1151.read_itau",return_value=bank) as parser:
        statement(1151,"itau",b"%PDF file","itau.pdf")
        parser.assert_called_once()
    with patch("app.company_1151.read_nubank",return_value=bank) as parser:
        statement(1151,"nubank",b"%PDF file","nu.pdf")
        parser.assert_called_once()
    with pytest.raises(ValueError,match="Banco não configurado"):
        statement(1151,"bradesco",b"%PDF file","file.pdf")


def test_advanced_workflow_routes_to_1151():
    with patch("app.company_1151.workflow_1151",return_value=(b"file","1151.xlsx")) as wf:
        assert _workflow(1151,{"itau":[]}, {})==(b"file","1151.xlsx")
    wf.assert_called_once()


def test_reconciliation_nubank_uses_model_month_without_extra_september():
    from app import migration_services as services
    from app import engine
    main=bank_rows("506","NUBANK",[("2026-08-06",234.69,"Pix no Crédito")])
    statement_all=bank_rows("506","NUBANK",[
        ("2026-08-06",234.69,"Pix no Crédito"),
        ("2026-09-03",-56.47,"ENEL")])
    with patch.object(engine,"ler_planilha_organizada_conferencia",
                      return_value=(main,main.iloc[0:0].copy(),None)), \
         patch.object(services,"statement",return_value=statement_all), \
         patch.object(engine,"conciliar_empresa_com_extrato") as compare:
        compare.return_value=(
            pd.DataFrame([{"ENTRADAS PLANILHA":234.69,"SAÍDAS PLANILHA":0,
                           "ENTRADAS EXTRATO":234.69,"SAÍDAS EXTRATO":0}]),
            pd.DataFrame(),pd.DataFrame(),pd.DataFrame())
        summary,_=services.reconcile(1151,"nubank",b"modelo",[("nu.pdf",b"%PDF")])
    compared=compare.call_args.args[1]
    assert compared["VALOR"].tolist()==[234.69]
    assert summary["extrato"]==1

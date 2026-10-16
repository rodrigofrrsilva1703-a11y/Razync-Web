"""Empresa 734: duas contas bancárias independentes e PDFs."""
import io
from unittest.mock import patch

import pandas as pd
import pytest
from openpyxl import load_workbook

from app.bank_734 import BANKS, read_bank_pdf, workflow_734
from app.registry import CAPABILITIES
from app.migration_services import _workflow


def fake_pdf() -> bytes:
    from reportlab.pdfgen import canvas
    buff = io.BytesIO()
    pdf = canvas.Canvas(buff)
    pdf.drawString(40, 700, "Extrato bancario de teste")
    pdf.save()
    return buff.getvalue()


def records():
    return [
        {"DESCRIÇÃO": "BANCO", "DATA": "02/09/2026", "VALOR": 100.25,
         "DÉBITO": "", "CRÉDITO": "", "HISTÓRICO": "Recebimento teste"},
        {"DESCRIÇÃO": "BANCO", "DATA": "03/09/2026", "VALOR": -45.50,
         "DÉBITO": "", "CRÉDITO": "", "HISTÓRICO": "Pagamento teste"},
    ]


def test_capabilities_for_734_and_no_cross_company_change():
    cap = CAPABILITIES[734]
    assert cap["workflow"] == "advanced"
    assert cap["banks"] == {"btg": "510", "bradesco": "2721"}
    assert [role["name"] for role in cap["roles"]] == ["btg", "bradesco"]
    assert all(role["accept"] == ".pdf" and role["multiple"]
               and role["optional"] for role in cap["roles"])
    assert CAPABILITIES[1402]["banks"]["btg"] == "510"
    assert CAPABILITIES[266]["banks"]["bradesco"] == "9"


@pytest.mark.parametrize("bank,account,description", [
    ("btg", "510", "BANCO BTG"),
    ("bradesco", "2721", "BANCO BRADESCO"),
])
def test_pdf_mapping_and_account_sign(bank, account, description):
    with patch("app.bank_734.engine.processar_extrato_conferencia_empresa",
               return_value=records()) as parser:
        df = read_bank_pdf(bank, fake_pdf(), "extrato.pdf")
    assert parser.call_args.args[2] == bank
    assert df["DESCRIÇÃO"].tolist() == [description, description]
    assert df["VALOR"].tolist() == [100.25, -45.50]
    assert df["DÉBITO"].tolist() == [account, ""]
    assert df["CRÉDITO"].tolist() == ["", account]
    assert list(df.columns) == ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]


def test_invalid_pdf_or_unreadable_layout_does_not_succeed_silently():
    with pytest.raises(ValueError, match="PDF"):
        read_bank_pdf("btg", b"bad", "extrato.xlsx")
    with patch("app.bank_734.engine.processar_extrato_conferencia_empresa", return_value=[]):
        with pytest.raises(ValueError, match="layout"):
            read_bank_pdf("bradesco", fake_pdf(), "extrato.pdf")


def test_two_banks_create_separate_sheets_and_period():
    pdf = fake_pdf()
    with patch("app.bank_734.engine.processar_extrato_conferencia_empresa",
               return_value=records()):
        content, filename = _workflow(734, {
            "btg": [("btg.pdf", pdf)],
            "bradesco": [("bradesco.pdf", pdf)],
        }, {"data_inicial": "2026-09-01", "data_final": "2026-09-30"})
    assert filename == "RAZYNC_734_MODELO_DOMINIO.xlsx"
    wb = load_workbook(io.BytesIO(content), data_only=True)
    assert any("BTG 510" in name for name in wb.sheetnames)
    assert any("Bradesco 2721" in name for name in wb.sheetnames)


def test_only_one_bank_is_enough_and_period_without_movements_fails():
    pdf = fake_pdf()
    with patch("app.bank_734.engine.processar_extrato_conferencia_empresa",
               return_value=records()):
        result, _ = workflow_734({"btg": [("btg.pdf", pdf)]}, {})
    wb = load_workbook(io.BytesIO(result))
    assert any("BTG" in sheet for sheet in wb.sheetnames)
    assert not any("Bradesco" in sheet for sheet in wb.sheetnames)
    with patch("app.bank_734.engine.processar_extrato_conferencia_empresa",
               return_value=records()):
        with pytest.raises(ValueError, match="período"):
            workflow_734({"btg": [("btg.pdf", pdf)]}, {
                "data_inicial": "2026-08-01", "data_final": "2026-08-31"
            })

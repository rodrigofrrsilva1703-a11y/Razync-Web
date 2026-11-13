"""Empresa 1050 — testes sintéticos para extrato Itaú mensal."""
from unittest.mock import patch
import fitz
import pandas as pd
import pytest
from app.company_1050 import read_statement, workflow_1050
from app.migration_services import accounts, statement, slug
from app.registry import CAPABILITIES

def _pdf(final="80,26", debit="495,83-", titular="F2R EXCELENCIA"):
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((350, 30), "extrato mensal ag 0735 cc 14341-4 fev 2026 001|002", fontsize=8)
    p.insert_text((60, 110), titular + " E P C C E L", fontsize=8)
    p.insert_text((65, 175), "01. Conta Corrente e Aplicacoes Automaticas\nR$ 576,01\nR$ " + final, fontsize=9)
    p.insert_text((60, 310), "total entradas\ntotal saidas\n(creditos)\n(debitos)\nR$ 0,08\nR$ 495,83", fontsize=8)
    p.insert_text((60, 375), "Conta Corrente | Movimentacao", fontsize=8)
    p.insert_text((152, 415), "25/02", fontsize=9)
    p.insert_text((210, 415), "BOLETO PAGO JAGUAR SERVI", fontsize=9)
    p.insert_text((438, 415), debit, fontsize=9)
    p.insert_text((210, 433), "Res Aplic Aut Mais", fontsize=9)
    p.insert_text((377, 433), "495,75", fontsize=9)
    p.insert_text((210, 451), "Rend Pago Aplic Aut Mais", fontsize=9)
    p.insert_text((385, 451), "0,08", fontsize=9)
    p.insert_text((210, 469), "SALDO APLIC AUT MAIS", fontsize=9)
    p.insert_text((535, 469), "79,26", fontsize=9)
    p.insert_text((60, 500), "totalizador de aplicacoes automaticas", fontsize=9)
    data=doc.tobytes()
    doc.close()
    return data

def test_registration():
    assert accounts(1050) == {"itau": "508"}
    assert slug(1050) == "f2r_excelencia_1050"
    assert set(CAPABILITIES[1050]["tools"]) == {
        "modelo_dominio", "conferencia_extrato", "base_inteligente"}

def test_read_realistic_monthly_layout():
    frame=read_statement(_pdf())
    assert frame["VALOR"].tolist() == [-495.83, 0.08]
    assert frame["DATA"].dt.strftime("%Y-%m-%d").tolist() == ["2026-02-25"] * 2
    assert frame["CRÉDITO"].tolist() == ["508", ""]
    assert frame["DÉBITO"].tolist() == ["", "508"]
    assert all("495,75" not in h for h in frame["HISTÓRICO"])
    via_route=statement(1050, "itau", _pdf(), "extrato.pdf")
    assert via_route["VALOR"].tolist() == [-495.83, 0.08]

def test_totals_mismatch_rejected():
    with pytest.raises(ValueError, match="saldo final"):
        read_statement(_pdf(final="90,26"))

def test_wrong_bank_account_rejected():
    with pytest.raises(ValueError, match="titular"):
        read_statement(_pdf(titular="OUTRA EMPRESA"))

def test_workflow_and_duplicate_month():
    with patch("app.excel.gerar_modelo_abas", return_value=b"excel") as exporter:
        book, filename=workflow_1050({"itau":[("fevereiro.pdf",_pdf())]}, {})
    assert book==b"excel"
    assert "1050" in filename
    sheets=exporter.call_args.args[0]
    assert list(sheets)==["Itaú"]
    assert sheets["Itaú"]["VALOR"].tolist()==[-495.83, 0.08]
    with pytest.raises(ValueError, match="repetido"):
        workflow_1050({"itau":[("fev1.pdf",_pdf()),("fev2.pdf",_pdf())]}, {})

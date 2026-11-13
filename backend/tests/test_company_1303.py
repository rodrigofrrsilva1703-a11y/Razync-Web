"""Regressões da empresa 1303: apenas dados sintéticos, sem extratos reais."""
from datetime import date
from unittest.mock import patch
import pandas as pd
import pytest
from app import company_1303 as company
from app import migration_services as services
from app.registry import CAPABILITIES

def fake_frame(account, bank):
    return pd.DataFrame([
        {"DESCRIÇÃO": bank, "DATA": pd.Timestamp("2026-06-01"),
         "VALOR": -10.23, "DÉBITO": "", "CRÉDITO": account,
         "HISTÓRICO": "Pago: Cobrança de IOF"},
        {"DESCRIÇÃO": bank, "DATA": pd.Timestamp("2026-06-10"),
         "VALOR": -611.60, "DÉBITO": "", "CRÉDITO": account,
         "HISTÓRICO": "Pago: Prestação"},
        {"DESCRIÇÃO": bank, "DATA": pd.Timestamp("2026-06-10"),
         "VALOR": 611.60, "DÉBITO": account, "CRÉDITO": "",
         "HISTÓRICO": "Recebido: Estorno"},
    ], columns=company.COLUMNS)

def test_registration_and_accounts():
    assert CAPABILITIES[1303]["banks"] == {"itau": "508", "banco_brasil": "8"}
    assert set(CAPABILITIES[1303]["tools"]) == {
        "modelo_dominio", "conferencia_extrato", "base_inteligente"}
    assert services.accounts(1303) == {"itau": "508", "banco_brasil": "8"}
    assert services.slug(1303) == "bmz_moto_1303"

def test_movement_sign_and_identifier_redaction():
    records = [
        (date(2026, 6, 10), -61160, "Pagamento 123.456.789-09"),
        (date(2026, 6, 10), 61160, "Estorno 123.456.789-09"),
    ]
    result = company._frame(records, "BANCO DO BRASIL", "8")
    assert result["VALOR"].tolist() == [-611.60, 611.60]
    assert result["CRÉDITO"].tolist() == ["8", ""]
    assert result["DÉBITO"].tolist() == ["", "8"]
    assert all("123.456.789" not in s for s in result["HISTÓRICO"])

def test_two_bank_workflow_preserves_estornos_and_separates_sheets():
    roles = {"itau": [("junho.pdf", b"%PDF mock")],
             "banco_brasil": [("junho.pdf", b"%PDF mock")]}
    readers = {"itau": lambda _: fake_frame("508", "BANCO ITAÚ"),
               "banco_brasil": lambda _: fake_frame("8", "BANCO DO BRASIL")}
    with patch.dict(company.READERS, readers), \
         patch("app.excel.gerar_modelo_abas", return_value=b"excel") as exporter:
        result, filename = company.workflow_1303(roles, {})
    assert result == b"excel" and "1303" in filename
    sheets = exporter.call_args.args[0]
    assert list(sheets) == ["Itaú", "Banco do Brasil"]
    assert sheets["Itaú"]["CRÉDITO"].tolist() == ["508", "508", ""]
    assert sheets["Banco do Brasil"]["DÉBITO"].tolist() == ["", "", "8"]

def test_duplicate_month_is_rejected():
    with patch.dict(company.READERS, {"itau": lambda _: fake_frame("508", "BANCO ITAÚ")}):
        with pytest.raises(ValueError, match="período repetido"):
            company.workflow_1303({"itau": [("a.pdf", b"%PDF"), ("b.pdf", b"%PDF")]}, {})

def test_bank_route_isolated_and_invalid_rejected():
    for bank, account in (("itau", "508"), ("banco_brasil", "8")):
        with patch.dict(company.READERS, {bank: lambda _, acc=account: fake_frame(acc, "BANK")}):
            output = services.statement(1303, bank, b"%PDF fixture", "junho.pdf")
            assert output["VALOR"].tolist() == [-10.23, -611.60, 611.60]
    with pytest.raises(ValueError, match="banco não cadastrado"):
        services.statement(1303, "santander", b"%PDF fixture", "junho.pdf")
    with pytest.raises(ValueError, match="PDF"):
        services.statement(1303, "itau", b"invalid", "junho.xlsx")

"""Regressões da Conferência com Extrato PDF da empresa 1328."""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from app import migration_services as services
from app import company_1328_itau_pdf as itau_pdf


def _event(day, kind, amount, label="BOLETO PAGO"):
    return {"date": day, "label": label, "type": kind, "values": [amount]}


def test_ocr_alternativo_so_quando_fecha_saldo_sem_ambiguidade():
    day = date(2026, 10, 13)
    # A primeira leitura perdeu um milhar; a segunda reconheceu os dígitos.
    bank = [{"values": [-90628, -190628]}]
    assert itau_pdf._resolve_day(bank, 0, 190628, day) == [-190628]
    with pytest.raises(ValueError, match="não fecham"):
        itau_pdf._resolve_day(bank, 0, 200628, day)
    same_delta = [{"values": [-90628, -190628]},
                  {"values": [-90628, -190628]}]
    with pytest.raises(ValueError, match="mais de uma interpretação"):
        itau_pdf._resolve_day(same_delta, -281256, 0, day)


def test_pdf_reader_preserva_movimentos_e_saldos_por_dia():
    day = date(2026, 10, 1)
    events = [
        _event(date(2026, 9, 30), "opening", 49035764, "SALDO ANTERIOR"),
        _event(day, "movement", -67251),
        _event(day, "movement", 1129553, "RECEBIMENTOS"),
        _event(day, "balance", 50098066, "SALDO TOTAL DISPONÍVEL DIA"),
    ]
    with patch.object(itau_pdf, "_extract_pages", return_value=iter(events)):
        frame = itau_pdf.read_statement(b"%PDF fake")
    assert frame["VALOR"].tolist() == [-672.51, 11295.53]
    assert frame["DÉBITO"].tolist() == ["", "508"]
    assert frame["CRÉDITO"].tolist() == ["508", ""]
    assert frame.attrs["opening_balance_cents"] == 49035764
    assert frame.attrs["closing_balance_cents"] == 50098066
    assert len(frame.attrs["daily_balances"]) == 1


def test_pdf_reader_rejects_missing_daily_balance():
    day = date(2026, 10, 1)
    events = [
        _event(date(2026, 9, 30), "opening", 0),
        _event(day, "movement", -100),
    ]
    with patch.object(itau_pdf, "_extract_pages", return_value=iter(events)):
        with pytest.raises(ValueError, match="sem saldo diário"):
            itau_pdf.read_statement(b"%PDF fake")


def test_conferencia_1328_aceita_pdf_mas_nao_a_planilha_financeira():
    with pytest.raises(ValueError, match="PDF"):
        services.statement(1328, "itau", b"fake", "extrato_financeiro.xlsx")
    with patch.object(itau_pdf, "read_statement", return_value=pd.DataFrame(
        [{"DATA": pd.Timestamp("2026-10-01"), "VALOR": -1.0}]
    )):
        result = services.statement(1328, "itau", b"%PDF", "itau.pdf")
    assert result.iloc[0]["VALOR"] == -1.0


def _frame(values):
    return pd.DataFrame([
        {
            "DESCRIÇÃO": "BANCO ITAÚ",
            "DATA": pd.Timestamp("2026-10-01"),
            "VALOR": amount,
            "DÉBITO": "508" if amount > 0 else "",
            "CRÉDITO": "508" if amount < 0 else "",
            "HISTÓRICO": "Pago: exemplo",
        } for amount in values
    ])


def test_conferencia_diaria_distingue_agrupamento_de_divergencia():
    bank = _frame([-20.0, -30.0])
    bank.attrs["daily_balances"] = [
        {"DATA": pd.Timestamp("2026-10-01"),
         "SALDO BANCO": 450.0, "QUANTIDADE": 2}
    ]
    model = _frame([-50.0])
    empty = model.iloc[0:0].copy()
    daily = pd.DataFrame([{
        "ENTRADAS PLANILHA": 0.0, "SAÍDAS PLANILHA": 50.0,
        "ENTRADAS EXTRATO": 0.0, "SAÍDAS EXTRATO": 50.0,
    }])
    with patch.object(services.engine, "ler_planilha_organizada_conferencia",
                      return_value=(model, empty, {})), \
         patch.object(services, "statement", return_value=bank), \
         patch.object(services.engine, "conciliar_empresa_com_extrato",
                      return_value=(daily, bank, model, empty)):
        summary, reports = services.reconcile(
            1328, "itau", b"modelo", [("itau.pdf", b"%PDF")], {}
        )
    assert summary["conferencia_valores_por_dia"] is True
    assert summary["movimentos_agrupados_ou_distintos"] is True
    assert summary["dias_pdf_validados"] == 1
    assert summary["dias_com_divergencia"] == 0
    assert reports["Valores por dia Itaú"].iloc[0]["SITUAÇÃO"] == "OK"
    assert reports["Valores por dia Itaú"].iloc[0]["MODELO QTDE"] == 1
    assert reports["Valores por dia Itaú"].iloc[0]["PDF QTDE"] == 2

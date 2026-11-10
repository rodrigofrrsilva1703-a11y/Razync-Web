"""Conciliação global: vários extratos para um Razão com várias competências.

Fixtures sintéticas, sem informações reais de clientes ou acesso externo.
"""
import io

import pandas as pd
import pytest

from app.global_tools import processar_razao, conciliar_razao
from app.ledger_periods import recortar_razao


def _razao_multiplas_abas():
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as book:
        pd.DataFrame([
            {"DATA": "15/01/2026", "HISTÓRICO": "Recebimento janeiro",
             "DÉBITO": "1.500,00", "CRÉDITO": ""},
            {"DATA": "15/01/2026", "HISTÓRICO": "Pagamento janeiro",
             "DÉBITO": "", "CRÉDITO": "350,00"},
        ]).to_excel(book, sheet_name="Janeiro", index=False)
        pd.DataFrame([
            {"DATA": "12/02/2026", "HISTÓRICO": "Recebimento fevereiro",
             "DÉBITO": "125,00", "CRÉDITO": ""},
        ]).to_excel(book, sheet_name="Fevereiro", index=False)
        pd.DataFrame([
            {"DATA": "10/03/2026", "HISTÓRICO": "Pagamento março",
             "DÉBITO": "", "CRÉDITO": "210,00"},
        ]).to_excel(book, sheet_name="Março", index=False)
    return stream.getvalue()


def _extratos_jan_mar():
    return pd.DataFrame([
        {"DATA": "15/01/2026", "VALOR": 1500, "HISTÓRICO": "Cliente A"},
        {"DATA": "15/01/2026", "VALOR": -350, "HISTÓRICO": "Fornecedor B"},
        {"DATA": "10/03/2026", "VALOR": -210, "HISTÓRICO": "Pagamento C"},
    ])


def test_le_todas_as_abas_de_razao_multicompetencia():
    frame = processar_razao(_razao_multiplas_abas(), "Razao_2026.xlsx")
    assert len(frame) == 4
    assert set(frame["DATA"].dt.strftime("%Y-%m")) == {"2026-01", "2026-02", "2026-03"}
    assert set(frame["ABA_RAZAO"]) == {"Janeiro", "Fevereiro", "Março"}
    assert frame["ENTRADAS_RAZAO"].sum() == 1625
    assert frame["SAIDAS_RAZAO"].sum() == 560


def test_vários_extratos_e_razao_anual_ignoram_competencia_sem_extrato():
    full = processar_razao(_razao_multiplas_abas(), "Razao_2026.xlsx")
    ext, raz, meta = recortar_razao(_extratos_jan_mar(), full)
    assert meta["periodo_automatico"] is True
    assert meta["meses_extratos"] == "2026-01, 2026-03"
    assert meta["meses_razao_desconsiderados"] == "2026-02"
    assert len(raz) == 3
    diario, summary = conciliar_razao(ext, raz)
    assert summary["dias"] == 2
    assert summary["dias_conferidos"] == 2
    assert summary["dias_revisar"] == 0
    assert set(diario["SITUAÇÃO"]) == {"CONFERE"}


def test_periodo_explicito_pode_incluir_mes_sem_extrato_para_conferencia():
    full = processar_razao(_razao_multiplas_abas(), "Razao_2026.xlsx")
    ext, raz, meta = recortar_razao(_extratos_jan_mar(), full, "2026-01-01", "2026-03-31")
    assert meta["periodo_automatico"] is False
    assert len(raz) == 4
    diario, summary = conciliar_razao(ext, raz)
    assert summary["dias_revisar"] == 1
    fevereiro = diario[diario["DATA"].dt.month == 2]
    assert len(fevereiro) == 1
    assert fevereiro.iloc[0]["SITUAÇÃO"] == "REVISAR"


def test_mes_sem_movimentos_nao_e_confundido_com_arquivo_invalido():
    full = processar_razao(_razao_multiplas_abas(), "Razao_2026.xlsx")
    with pytest.raises(ValueError, match="não possuem movimentações"):
        recortar_razao(_extratos_jan_mar(), full, "2026-05-01", "2026-05-31")


def test_filtro_por_competencia_preserva_divergencia_no_mes_selecionado():
    full = processar_razao(_razao_multiplas_abas(), "Razao_2026.xlsx")
    ext = _extratos_jan_mar()
    ext.loc[len(ext)] = {"DATA": "10/03/2026", "VALOR": -50, "HISTÓRICO": "Taxa extra"}
    ext, raz, meta = recortar_razao(ext, full)
    diario, summary = conciliar_razao(ext, raz)
    assert summary["dias_revisar"] == 1
    assert meta["meses_razao_desconsiderados"] == "2026-02"


def test_filtros_incompletos_sao_rejeitados():
    full = processar_razao(_razao_multiplas_abas(), "Razao_2026.xlsx")
    with pytest.raises(ValueError, match="datas"):
        recortar_razao(_extratos_jan_mar(), full, "2026-01-01", "")

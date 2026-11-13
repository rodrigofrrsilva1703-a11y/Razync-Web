"""Conciliação global: vários extratos para um Razão com várias competências.

Fixtures sintéticas, sem informações reais de clientes ou acesso externo.
"""
import io

import pandas as pd
import pytest

from app.global_tools import processar_razao, conciliar_razao, processar_arquivo
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



def test_extrato_excel_com_data_tipificada_como_datetime():
    stream = io.BytesIO()
    pd.DataFrame([
        {"DATA": pd.Timestamp("2026-01-15"), "HISTÓRICO": "Pagamento fornecedor",
         "DÉBITO": 350, "CRÉDITO": None},
        {"DATA": pd.Timestamp("2026-01-15"), "HISTÓRICO": "Recebimento cliente",
         "DÉBITO": None, "CRÉDITO": 1500},
    ]).to_excel(stream, index=False)
    result = processar_arquivo(stream.getvalue(), "Itau_Janeiro.xlsx")
    assert len(result) == 2
    assert sorted(result["VALOR"].tolist()) == [-350, 1500]
    assert set(pd.to_datetime(result["DATA"], dayfirst=True).dt.strftime("%Y-%m")) == {"2026-01"}


def test_extrato_excel_multiplas_abas_e_datas_reais():
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        pd.DataFrame({"INFO": ["Resumo"], "VALOR": [0]}).to_excel(
            writer, sheet_name="Capa", index=False)
        pd.DataFrame([
            {"DATA": pd.Timestamp("2026-01-15"), "HISTÓRICO": "Recebimento",
             "CRÉDITO": 1500, "DÉBITO": None},
        ]).to_excel(writer, sheet_name="Janeiro", index=False)
        pd.DataFrame([
            {"DATA": pd.Timestamp("2026-03-10"), "HISTÓRICO": "Pagamento",
             "CRÉDITO": None, "DÉBITO": 210},
        ]).to_excel(writer, sheet_name="Marco", index=False)
    result = processar_arquivo(stream.getvalue(), "Itau_Extratos.xlsx")
    assert len(result) == 2
    assert sorted(result["VALOR"].tolist()) == [-210, 1500]
    assert set(pd.to_datetime(result["DATA"], dayfirst=True).dt.strftime("%Y-%m")) == {"2026-01", "2026-03"}


def test_uploads_de_dois_extratos_e_um_razao_multicompetencia():
    import asyncio
    from starlette.datastructures import UploadFile
    from app.main import _parse_upload_frames
    from app.global_tools import processar_arquivo

    jan = b"DATA;HISTORICO;ENTRADA;SAIDA\n15/01/2026;Recebimento;1500,00;\n15/01/2026;Fornecedor;;350,00\n"
    mar = b"DATA;HISTORICO;ENTRADA;SAIDA\n10/03/2026;Pagamento;;210,00\n"
    files = [
        UploadFile(io.BytesIO(jan), filename="Itau_Janeiro.csv"),
        UploadFile(io.BytesIO(mar), filename="Itau_Marco.csv"),
    ]
    extrato = asyncio.run(_parse_upload_frames(files, processar_arquivo))
    assert len(extrato) == 3
    assert set(pd.to_datetime(extrato["DATA"], dayfirst=True).dt.strftime("%Y-%m")) == {"2026-01", "2026-03"}
    razao = processar_razao(_razao_multiplas_abas(), "Razao_2026.xlsx")
    ext, raz, _ = recortar_razao(extrato, razao)
    diario, summary = conciliar_razao(ext, raz)
    assert summary["dias_conferidos"] == 2
    assert summary["dias_revisar"] == 0



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


def test_datas_iso_e_brasileiras_sao_preservadas_no_recorte_e_no_cruzamento():
    extrato = pd.DataFrame({
        "DATA": ["2026-02-08", "09/02/2026"],
        "VALOR": [150, -35],
    })
    razao = pd.DataFrame({
        "DATA": ["08/02/2026", "2026-02-09"],
        "ENTRADAS_RAZAO": [150, 0],
        "SAIDAS_RAZAO": [0, 35],
    })
    for inicio, fim in [("", ""), ("2026-02-01", "2026-02-28")]:
        ext, raz, info = recortar_razao(extrato, razao, inicio, fim)
        diario, resumo = conciliar_razao(ext, raz)
        assert info["meses_extratos"] == "2026-02"
        assert diario["DATA"].dt.day.tolist() == [8, 9]
        assert resumo["dias_conferidos"] == 2


def test_modelo_dominio_usa_valor_do_movimento_e_nao_codigo_contabil():
    data = io.BytesIO()
    pd.DataFrame([
        ["SICREDI", "08/02/2026", 150, 505, 412, "Recebimento"],
        ["SICREDI", "09/02/2026", -35, "", "", "Tarifa"],
    ], columns=["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]).to_excel(data, index=False)
    result = processar_arquivo(data.getvalue(), "Modelo.xlsx")
    assert result["VALOR"].tolist() == [150, -35]
    with pytest.raises(ValueError, match="Modelo Domínio.*campo Razão"):
        processar_razao(data.getvalue(), "Modelo.xlsx")

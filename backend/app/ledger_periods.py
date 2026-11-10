"""Recorte conservador de extratos bancários x Razão Domínio.

Quando não há datas informadas, considerar somente as competências que
aparecem nos extratos. Um Razão anual não gera divergência artificial em
meses sem qualquer extrato enviado. O usuário pode escolher um intervalo
explícito para incluir os dias correspondentes, inclusive sem extrato.
"""
from __future__ import annotations

import pandas as pd

from app.report_helpers import _filter_period_frame, _period_bounds


def _datas(frame):
    if "DATA" not in frame.columns:
        raise ValueError("Um dos arquivos processados não possui DATA.")
    return pd.to_datetime(frame["DATA"], format="mixed", dayfirst=True, errors="coerce")


def _periodos(frame):
    if frame.empty:
        return []
    return sorted(_datas(frame).dropna().dt.to_period("M").astype(str).unique().tolist())


def recortar_razao(extrato, razao, inicio="", fim=""):
    if extrato is None or extrato.empty:
        raise ValueError("Nenhum movimento bancário foi reconhecido nos extratos.")
    if razao is None or razao.empty:
        raise ValueError("Nenhum lançamento contábil foi reconhecido no Razão.")

    # Sempre validar os dois limites juntos, mesmo que o extrato esteja vazio
    # no período; não esconder filtros inválidos.
    _period_bounds(inicio, fim)
    extrato = extrato.assign(DATA=_datas(extrato))
    razao = razao.assign(DATA=_datas(razao))
    meses_raz_original = _periodos(razao)
    meses_ext_original = _periodos(extrato)

    if inicio:
        df_ext = _filter_period_frame(extrato, inicio, fim)
        df_raz = _filter_period_frame(razao, inicio, fim)
        filtro = "informado"
    else:
        df_ext = extrato.copy()
        selecionados = set(meses_ext_original)
        df_raz = razao.loc[_datas(razao).dt.to_period("M").astype(str).isin(selecionados)].copy()
        filtro = "meses_dos_extratos"

    if df_ext.empty:
        raise ValueError("Os extratos não possuem movimentações nas datas selecionadas.")
    meses = _periodos(df_ext)
    meses_ignorados = sorted(set(meses_raz_original) - set(_periodos(df_raz)))
    metadata = {
        "criterio_periodo": filtro,
        "meses_extratos": ", ".join(meses),
        "meses_razao_importado": ", ".join(meses_raz_original),
        "meses_razao_desconsiderados": ", ".join(meses_ignorados),
        "periodos_extratos_contados": len(meses),
        "periodo_automatico": not bool(inicio),
    }
    return df_ext, df_raz, metadata

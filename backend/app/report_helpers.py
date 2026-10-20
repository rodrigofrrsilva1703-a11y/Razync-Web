"""Conversões de relatórios e períodos compartilhadas pelas rotas.

Preserva formatos de Excel, datas, arredondamentos e respostas existentes.
Não aplica limites de upload e não contém regras específicas de empresas.
"""
from __future__ import annotations

import io
import pandas as pd
from fastapi.responses import StreamingResponse

def _excel_report(sheets: dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in sheets.items():
            frame = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
            frame.to_excel(writer, sheet_name=str(name)[:31], index=False)
    return out.getvalue()


def _download(data: bytes, filename: str):
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _period_bounds(data_inicial: str = "", data_final: str = ""):
    if bool(data_inicial) != bool(data_final):
        raise ValueError("Informe as duas datas do período.")
    if not data_inicial:
        return None, None
    inicio = pd.Timestamp(data_inicial).normalize()
    fim = pd.Timestamp(data_final).normalize()
    if fim < inicio:
        raise ValueError("A Data Final não pode ser anterior à Data Inicial.")
    return inicio, fim


def _filter_period_frame(frame: pd.DataFrame, data_inicial: str = "", data_final: str = ""):
    inicio, fim = _period_bounds(data_inicial, data_final)
    if inicio is None or frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else frame
    if "DATA" not in frame.columns:
        raise ValueError("O arquivo não possui coluna DATA para aplicar o período.")
    datas = pd.to_datetime(frame["DATA"], dayfirst=True, errors="coerce")
    return frame.loc[datas.between(inicio, fim, inclusive="both")].copy()


def _preview_records(frame: pd.DataFrame):
    """Convert a reconciliation dataframe to compact JSON-safe rows."""
    rows = []
    for record in frame.to_dict("records"):
        item = {}
        for key, value in record.items():
            if value is None or (not isinstance(value, str) and pd.isna(value)):
                item[str(key)] = None
            elif isinstance(value, pd.Timestamp):
                item[str(key)] = value.strftime("%Y-%m-%d")
            elif hasattr(value, "item"):
                scalar = value.item()
                item[str(key)] = round(scalar, 2) if isinstance(scalar, float) else scalar
            elif isinstance(value, float):
                item[str(key)] = round(value, 2)
            else:
                item[str(key)] = value
        rows.append(item)
    return rows



"""Resumo de cobertura da Base Inteligente, sem alterar regras de classificação.

Uma linha com histórico é considerada classificada quando possui contas de
DÉBITO e CRÉDITO utilizáveis. Nas modalidades da Eletro Forte, as contas
provisórias da coluna de contrapartida são tratadas como pendentes.
"""
from __future__ import annotations

import io

from openpyxl import load_workbook

from app import engine


def _cell_text(value):
    return engine.texto_celula_seguro(value).strip()


def _normalized_header(ws):
    for row in range(1, min(ws.max_row, 30) + 1):
        columns = {
            engine.normalizar_texto(_cell_text(ws.cell(row, col).value)).strip(): col
            for col in range(1, ws.max_column + 1)
        }
        if all(key in columns for key in ("historico", "debito", "credito")):
            return row, columns
    return None, None


def _needs_replacement(row, cols, company_slug, options):
    """A coluna de contrapartida e seus placeholders conforme o modo vigente."""
    column = engine.normalizar_texto(str(options.get("coluna_substituir") or "")).strip()
    placeholders = {_cell_text(value) for value in options.get("valores_substituiveis", [])}

    if bool(options.get("modo_consolidado", False)) and company_slug.startswith("eletro_forte"):
        value_col = cols.get("valor")
        value = (
            engine.limpar_valor_monetario(row[value_col - 1].value)
            if value_col is not None else 0.0
        )
        if value < 0:
            column = "debito"
            placeholders = (
                {"", "0"} if company_slug == "eletro_forte_filial_1408"
                else {"", "0", "166"}
            )
        elif value > 0:
            column = "credito"
            placeholders = (
                {"", "0"} if company_slug == "eletro_forte_filial_1408"
                else {"", "0", "14", "16", "166"}
            )
        else:
            return None, set()
    return column, placeholders


def _classified(row, cols, company_slug, options):
    debit = _cell_text(row[cols["debito"] - 1].value)
    credit = _cell_text(row[cols["credito"] - 1].value)
    if debit in {"", "0"} or credit in {"", "0"}:
        return False
    column, invalid = _needs_replacement(row, cols, company_slug, options)
    if column == "debito" and debit in invalid:
        return False
    if column == "credito" and credit in invalid:
        return False
    return True


def coverage(original_bytes: bytes, classified_bytes: bytes, company_slug: str,
             options: dict | None = None) -> dict:
    """Indicadores apenas das abas elegíveis; exclui Principal e Retirados."""
    options = options or {}
    original = load_workbook(io.BytesIO(original_bytes), read_only=True, data_only=False)
    result = load_workbook(io.BytesIO(classified_bytes), read_only=True, data_only=False)
    total = previous = classified = new = 0
    try:
        for ws in result.worksheets:
            normalized = engine.normalizar_texto(ws.title)
            if "retir" in normalized:
                continue
            if company_slug.startswith("eletro_forte") and normalized.strip() == "principal":
                continue
            if ws.title not in original.sheetnames:
                continue
            source = original[ws.title]
            header, columns = _normalized_header(ws)
            if header is None:
                continue
            original_header, source_columns = _normalized_header(source)
            if original_header is None:
                continue
            for n in range(header + 1, ws.max_row + 1):
                row = [ws.cell(n, c) for c in range(1, ws.max_column + 1)]
                if not _cell_text(row[columns["historico"] - 1].value):
                    continue
                total += 1
                complete = _classified(row, columns, company_slug, options)
                source_row = [
                    source.cell(n, c) for c in range(1, source.max_column + 1)
                ]
                was_complete = _classified(source_row, source_columns, company_slug, options)
                if complete:
                    classified += 1
                if was_complete:
                    previous += 1
                if complete and not was_complete:
                    new += 1
    finally:
        original.close()
        result.close()
    return {
        "total": total,
        "classificadas": classified,
        "pendentes": total - classified,
        "ja_classificadas": previous,
        "novas_classificadas": new,
        "percentual": round(100 * classified / total, 1) if total else None,
    }

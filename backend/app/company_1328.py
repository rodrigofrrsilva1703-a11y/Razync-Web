"""Empresa 1328 — Extrato financeiro Itaú em Excel legado renomeado .xlsx.

Fonte dos lançamentos: Data, Histórico, N Documento, Débito, Crédito.
Débito = pagamento negativo; Crédito = recebimento positivo.
Não usa colunas de saldo como movimentação.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
import unicodedata

import pandas as pd

COLUMNS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
ZIP_MAGIC = b"PK\x03\x04"


def _norm(value):
    chars = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]", "", "".join(
        c for c in chars if not unicodedata.combining(c)
    ).casefold())


def _column(header, *choices):
    for i, value in enumerate(header):
        name = _norm(value)
        if any(name == choice for choice in choices):
            return i
    return None


def _money(value, row):
    if value is None or (isinstance(value, str) and not value.strip()):
        return 0
    if pd.isna(value):
        return 0
    if isinstance(value, bool):
        raise ValueError(f"Empresa 1328: valor inválido na linha {row}.")
    if isinstance(value, str):
        raw = value.strip().replace("R$", "").replace("\u00a0", "").replace(" ", "")
        if not raw or raw in {"-", "--"}:
            return 0
        negative = raw.startswith("-") or raw.endswith("-") or (raw.startswith("(") and raw.endswith(")"))
        raw = raw.strip("-()")
        raw = raw.replace(".", "").replace(",", ".") if "," in raw else raw
        try:
            result = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError(f"Empresa 1328: valor ilegível na linha {row}.") from exc
        if negative:
            result = -abs(result)
    else:
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"Empresa 1328: valor inválido na linha {row}.") from exc
    pennies = result * 100
    if not pennies.is_finite() or pennies != pennies.to_integral_value():
        raise ValueError(f"Empresa 1328: valor com fração de centavo na linha {row}.")
    return abs(int(pennies))


def _saldo_centavos(value, row):
    """Saldo é usado somente para conferir o extrato, nunca para lançar."""
    if value is None or pd.isna(value) or (
        isinstance(value, str) and not value.strip()
    ):
        return None
    if isinstance(value, bool):
        raise ValueError(f"Empresa 1328: saldo inválido na linha {row}.")
    raw = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        number = Decimal(raw) * 100
    except InvalidOperation as exc:
        raise ValueError(f"Empresa 1328: saldo ilegível na linha {row}.") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"Empresa 1328: saldo inválido na linha {row}.")
    return int(number)


def _date(value, row):
    if isinstance(value, (pd.Timestamp, datetime, date)):
        parsed = pd.Timestamp(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(value))
    else:
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed) or not 2000 <= parsed.year <= 2100:
        raise ValueError(f"Empresa 1328: data inválida na linha {row}.")
    return pd.Timestamp(parsed.date())


def _document(value):
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            return str(int(value))
    text = str(value).strip()
    return "" if text.casefold() in ("nan", "none") else text


def _read_sheets(content):
    if not isinstance(content, bytes) or len(content) > 30 * 1024 * 1024:
        raise ValueError("Empresa 1328: arquivo Excel inválido ou acima de 30 MB.")
    if content.startswith(OLE_MAGIC):
        engine = "xlrd"  # Excel .xls antigo, mesmo quando chamado .xlsx
    elif content.startswith(ZIP_MAGIC):
        engine = "openpyxl"
    else:
        raise ValueError("Empresa 1328: envie um arquivo Excel XLS ou XLSX válido.")
    try:
        return pd.read_excel(BytesIO(content), sheet_name=None,
                             header=None, engine=engine, dtype=object)
    except Exception as exc:
        raise ValueError(
            "Empresa 1328: não foi possível ler a planilha financeira Excel."
        ) from exc


def read_statement(content):
    sheets = _read_sheets(content)
    rows = []
    seen_periods = set()
    for sheet_name, data in sheets.items():
        if data.empty:
            continue
        # O relatório contém título, empresa, período e dados bancários
        # antes dos cabeçalhos reais. Detectar a linha, não assumir A1.
        header_row = None
        columns = None
        for i in range(min(45, len(data))):
            values = data.iloc[i].tolist()
            positions = {
                "date": _column(values, "data"),
                "history": _column(values, "historico", "lancamento", "descricao"),
                "document": _column(values, "ndocumento", "numerodocumento",
                                    "documento", "nrodocumento", "nodocumento"),
                "debit": _column(values, "debito"),
                "credit": _column(values, "credito"),
            }
            if all(v is not None for v in positions.values()) and len(set(positions.values())) == 5:
                header_row, columns = i, positions
                break
        if header_row is None:
            # Ignorar abas auxiliares sem tabela; não aceitar arquivo vazio.
            continue
        balance_index = _column(data.iloc[header_row].tolist(), "saldo")
        running_balance = None
        validated_balances = 0
        for i in range(header_row + 1, len(data)):
            line = data.iloc[i].tolist()
            source_line = i + 1

            # O relatório A&Z tem "Saldo Anterior :" na coluna CRÉDITO,
            # mas SEM data nem lançamento (linha 10 do arquivo original).
            # Reconhecer cabeçalhos/saldos antes de interpretar moeda.
            day_cell = line[columns["date"]]
            explicit_history = _document(line[columns["history"]])
            # Neste formato "Histórico" está no cabeçalho da coluna B,
            # enquanto o nome efetivo do lançamento aparece na coluna D,
            # imediatamente antes da coluna "Nº Documento" (E).
            detail_column = columns["document"] - 1
            detail_history = (
                _document(line[detail_column])
                if detail_column != columns["history"] and detail_column >= 0
                else ""
            )
            history = detail_history or explicit_history
            if pd.isna(day_cell) or str(day_cell).strip() == "":
                # Linhas sem data podem ser apenas saldo anterior / total.
                if not history or _norm(history).startswith(
                    ("saldo", "total", "resumo")
                ):
                    # No arquivo original o texto "Saldo Anterior :" está
                    # na coluna Crédito (I) e o valor na coluna Saldo (J).
                    if (balance_index is not None and not rows
                        and _norm(line[columns["credit"]]).startswith("saldoanterior")):
                        running_balance = _saldo_centavos(
                            line[balance_index], source_line
                        )
                    continue
                raise ValueError(
                    f"Empresa 1328: lançamento sem data na linha {source_line}."
                )
            # Rodapé real do ERP (linha 326): a coluna Data recebe
            # "Financeiro\\Extrato Financeiro (102)" e as colunas
            # Débito/Crédito não contêm movimentação. Não interpretar
            # metadados do relatório como lançamento com data inválida.
            if not history and all(
                pd.isna(value) or str(value).strip() in {"", "0", "0.0", "0,00", "0.00"}
                for value in (line[columns["debit"]], line[columns["credit"]])
            ):
                continue
            day = _date(day_cell, source_line)
            if not history or _norm(history).startswith(("saldoanterior", "saldofinal")):
                raise ValueError(
                    f"Empresa 1328: histórico do lançamento ausente na linha {source_line}."
                )
            deb = _money(line[columns["debit"]], source_line)
            cred = _money(line[columns["credit"]], source_line)
            if not deb and not cred:
                continue  # Linha informativa, sem movimentação bancária
            if deb and cred:
                raise ValueError(
                    f"Empresa 1328: Débito e Crédito preenchidos na linha {source_line}."
                )
            document = _document(line[columns["document"]])
            value = cred if cred else -deb
            if running_balance is not None and balance_index is not None:
                reported = _saldo_centavos(line[balance_index], source_line)
                if reported is not None:
                    if running_balance + value != reported:
                        raise ValueError(
                            f"Empresa 1328: saldo divergente na linha {source_line}."
                        )
                    running_balance = reported
                    validated_balances += 1
                else:
                    running_balance += value
            description = history if not document else f"{history} | Doc: {document}"
            rows.append({
                "DESCRIÇÃO": "BANCO ITAÚ",
                "DATA": day,
                "VALOR": value / 100,
                "DÉBITO": "508" if value > 0 else "",
                "CRÉDITO": "508" if value < 0 else "",
                "HISTÓRICO": ("Recebido: " if value > 0 else "Pago: ") + description,
            })
            seen_periods.add(day.strftime("%Y-%m"))
    if not rows:
        raise ValueError(
            "Empresa 1328: não foram encontrados lançamentos nas colunas "
            "Data, Histórico, N Documento, Débito e Crédito."
        )
    # Separar por período no fluxo externo; nenhuma competência fixa.
    return pd.DataFrame(rows, columns=COLUMNS)


def workflow_1328(roles, options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame

    uploads = roles.get("itau") or []
    if not uploads:
        raise ValueError("Empresa 1328: envie o extrato financeiro do Itaú.")
    seen_months = set()
    frames = []
    for filename, content in uploads:
        if not filename.lower().endswith((".xls", ".xlsx")):
            raise ValueError("Empresa 1328: envie uma planilha Excel XLS ou XLSX.")
        frame = read_statement(content)
        periods = set(frame["DATA"].dt.to_period("M").astype(str))
        if seen_months & periods:
            raise ValueError("Empresa 1328: competência repetida entre os arquivos.")
        seen_months.update(periods)
        frames.append(frame)
    result = filter_frame(pd.concat(frames, ignore_index=True), options)
    if result.empty:
        raise ValueError("Empresa 1328: não há lançamentos no período selecionado.")
    result = result.sort_values("DATA", kind="stable")
    return (gerar_modelo_abas({"Itaú": result}, date_format="dd/mm/yyyy"),
            "EMPRESA_1328_ITAU_MODELO_DOMINIO.xlsx")

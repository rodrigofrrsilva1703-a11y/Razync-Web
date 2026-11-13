"""Empresa 1024: BB Consultas, enriquecido somente por correspondência segura."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re
import unicodedata

import pandas as pd
from pypdf import PdfReader

from app.bb_consultas import ler_extrato_bb_consultas


def _cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal("1")))


def _normal(text):
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in value if not unicodedata.combining(c)).casefold()


def _ledger(content):
    if len(content) > 15 * 1024 * 1024:
        raise ValueError("A planilha auxiliar deve ter até 15 MB.")
    source = pd.read_excel(BytesIO(content), sheet_name=0)
    columns = {_normal(c).strip(): c for c in source.columns}
    required = {"data", "historico", "entrada", "saida"}
    if not required <= columns.keys():
        raise ValueError("A planilha deve ter Data, Historico, Entrada e Saida.")
    rows = []
    for position, line in source.iterrows():
        history = line[columns["historico"]]
        if pd.isna(history) or not str(history).strip():
            continue
        raw_day = line[columns["data"]]
        day = (pd.to_datetime(raw_day, unit="D", origin="1899-12-30", errors="coerce")
               if isinstance(raw_day, (int, float)) else
               pd.to_datetime(raw_day, dayfirst=True, errors="coerce"))
        if pd.isna(day):
            continue
        incoming = line[columns["entrada"]]
        outgoing = line[columns["saida"]]
        incoming = 0 if pd.isna(incoming) else _cents(incoming)
        outgoing = 0 if pd.isna(outgoing) else _cents(outgoing)
        if incoming < 0 or outgoing < 0 or (incoming and outgoing) or not (incoming or outgoing):
            raise ValueError(f"Entrada/Saida inválida na linha {position+2} da planilha.")
        rows.append({"date": day.date(), "cents": incoming - outgoing,
                     "history": str(history).strip(), "row": position + 2})
    if not rows:
        raise ValueError("Nenhuma movimentação válida na planilha auxiliar.")
    return rows


def _statement(content):
    reader = PdfReader(BytesIO(content), strict=False)
    first = reader.pages[0].extract_text() or ""
    if not re.search(r"Conta corrente\s+29347-4\s*TELES\s*V\s*S\s*ADVOGADOS", first, re.I):
        raise ValueError("O extrato não corresponde à conta corrente 29347-4 da empresa 1024.")
    period = re.search(r"Per[ií]odo do extrato\s+(\d{2})\s*/\s*(\d{4})", first, re.I)
    if not period:
        raise ValueError("Competência do extrato BB não identificada.")
    month, year = map(int, period.groups())
    records = ler_extrato_bb_consultas(content, preserve_columns=True)
    frame = pd.DataFrame(records)
    if any((pd.Timestamp(day).month, pd.Timestamp(day).year) != (month, year) for day in frame["DATA"]):
        raise ValueError("O PDF contém lançamentos de outra competência.")
    return frame, (year, month)


def enrich(statement_pdf, spreadsheet):
    frame, period = _statement(statement_pdf)
    ledger = [x for x in _ledger(spreadsheet) if (x["date"].year, x["date"].month) == period]
    if not ledger:
        raise ValueError("A planilha não contém lançamentos na competência do extrato.")
    original = frame.copy(deep=True)
    bank_values = [_cents(v) for v in frame["VALOR"]]
    freq_bank, freq_sheet = Counter(bank_values), Counter(r["cents"] for r in ledger)
    ledger_by_value = defaultdict(list)
    for row in ledger:
        ledger_by_value[row["cents"]].append(row)
    used = set()
    matched = []
    for index, row in frame.iterrows():
        value = bank_values[index]
        if freq_bank[value] != 1 or freq_sheet[value] != 1:
            continue
        candidate = ledger_by_value[value][0]
        date = pd.Timestamp(row["DATA"]).date()
        if abs((date - candidate["date"]).days) > 4:
            continue
        if not candidate["history"].strip():
            continue
        used.add(candidate["row"])
        matched.append((index, candidate["row"], candidate["history"], "valor único e data próxima"))
        frame.at[index, "HISTÓRICO"] = candidate["history"]
    # Um PIX pode corresponder a vários componentes identificados na planilha.
    # Preserva o valor consolidado; só acrescenta detalhamento com beneficiário inequívoco.
    for index, row in frame.iterrows():
        value = bank_values[index]
        if any(i == index for i, *_ in matched) or value >= 0:
            continue
        date = pd.Timestamp(row["DATA"]).date()
        candidates = [r for r in ledger if r["row"] not in used and r["date"] == date
                      and r["cents"] < 0 and "mayara" in _normal(r["history"])]
        if (len(candidates) == 3 and sum(r["cents"] for r in candidates) == value
                and "mayara" in _normal(row["HISTÓRICO"])
                and freq_bank[value] == 1):
            history = " / ".join(r["history"] for r in candidates)
            frame.at[index, "HISTÓRICO"] = history
            for candidate in candidates:
                used.add(candidate["row"])
                matched.append((index, candidate["row"], candidate["history"], "componentes do PIX"))
    # Nunca alterar quantidade, data, valores ou somatório do extrato.
    assert len(frame) == len(original)
    assert [_cents(v) for v in frame["VALOR"]] == bank_values
    assert frame["DATA"].tolist() == original["DATA"].tolist()
    report = pd.DataFrame(matched, columns=["Lançamento no extrato", "Linha planilha", "Histórico identificado", "Critério"])
    pendings = pd.DataFrame([r for r in ledger if r["row"] not in used])
    return frame, report, pendings


def workflow_1024(roles, options):
    from app import engine
    from app.advanced import append_dataframe_sheets
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame

    statements, ledgers = roles.get("extrato", []), roles.get("planilha", [])
    if len(statements) != 1 or len(ledgers) != 1:
        raise ValueError("Envie um extrato Banco do Brasil em PDF e uma planilha auxiliar XLSX da mesma competência.")
    if not statements[0][0].lower().endswith(".pdf") or not ledgers[0][0].lower().endswith(".xlsx"):
        raise ValueError("Formatos esperados: extrato PDF e planilha XLSX.")
    frame, matched, pending = enrich(statements[0][1], ledgers[0][1])
    frame = filter_frame(frame, options)
    if frame.empty:
        raise ValueError("Nenhum lançamento bancário no período selecionado.")
    for idx, row in frame.iterrows():
        value = float(row["VALOR"])
        frame.at[idx, "DÉBITO"] = "8" if value > 0 else ""
        frame.at[idx, "CRÉDITO"] = "8" if value < 0 else ""
        history = re.sub(r"^(?:Pago|Recebido)\s*:\s*", "", str(row["HISTÓRICO"]), flags=re.I).strip()
        frame.at[idx, "HISTÓRICO"] = ("Recebido: " if value > 0 else "Pago: ") + history
    book = gerar_modelo_abas({"Banco do Brasil": frame.sort_values("DATA", kind="stable")}, date_format="dd/mm/yyyy")
    notes = {"Identificações auxiliares": matched, "Planilha sem vínculo": pending}
    book = append_dataframe_sheets(book, notes)
    return book, "EMPRESA_1024_BB_MODELO_DOMINIO.xlsx"

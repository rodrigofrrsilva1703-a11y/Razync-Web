"""Empresa 1303 — BMZ Moto Peças. Leitores PDF com validação integral de saldos."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
import re
import unicodedata
import fitz
import pandas as pd

COLUMNS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
DATE = re.compile(r"\d{2}/\d{2}/20\d{2}\Z")
MONEY = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\Z")
PRIVATE = re.compile(r"\b(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11}|\d{14})\b")

def _norm(value):
    return "".join(x for x in unicodedata.normalize("NFKD", str(value or ""))
                   if not unicodedata.combining(x)).casefold()

def _cents(value):
    raw = str(value).strip()
    number = Decimal(raw.lstrip("-").replace(".", "").replace(",", ".")) * 100
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("Valor monetário inválido no extrato.")
    return int(number) * (-1 if raw.startswith("-") else 1)

def _center(word):
    return (word[1] + word[3]) / 2

def _words(words, lower, upper, x0, x1):
    return [w for w in words if lower <= _center(w) < upper and x0 <= w[0] < x1]

def _text(words):
    return " ".join(w[4] for w in sorted(words, key=lambda w: (_center(w), w[0]))).strip()

def _open(pdf, bank):
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF") or len(pdf) > 35 * 1024 * 1024:
        raise ValueError(f"Empresa 1303: o extrato {bank} deve ser PDF válido de até 35 MB.")
    try:
        doc = fitz.open(stream=pdf, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Não foi possível abrir o PDF {bank}.") from exc
    if not 1 <= len(doc) <= 30:
        doc.close()
        raise ValueError("PDF com quantidade de páginas inválida.")
    return doc

def _frame(records, bank, account):
    if not records:
        raise ValueError(f"Extrato {bank} não contém lançamentos válidos.")
    return pd.DataFrame([{
        "DESCRIÇÃO": bank,
        "DATA": pd.Timestamp(day),
        "VALOR": value / 100,
        "DÉBITO": account if value > 0 else "",
        "CRÉDITO": account if value < 0 else "",
        "HISTÓRICO": ("Recebido: " if value > 0 else "Pago: ") +
                     " ".join(PRIVATE.sub("", description).split()),
    } for day, value, description in records], columns=COLUMNS)

def read_itau(content):
    doc = _open(content, "Itaú")
    with doc:
        header = doc[0].get_text()
        if not (re.search(r"BMZ\s+MOTO\s+PECAS", header, re.I)
                and re.search(r"Agência\s+0032\s+Conta\s+0099878-3", header, re.I)):
            raise ValueError("Itaú 1303: titular, agência 0032 ou conta 0099878-3 divergente.")
        match = re.search(r"Lançamentos do período:\s*(\d{2}/\d{2}/20\d{2})\s+até\s+(\d{2}/\d{2}/20\d{2})", header)
        if not match:
            raise ValueError("Itaú 1303: período não identificado.")
        start, end = [datetime.strptime(x, "%d/%m/%Y").date() for x in match.groups()]
        if (start.year, start.month) != (end.year, end.month):
            raise ValueError("Itaú 1303: informe extratos de uma competência por arquivo.")
        records, checks, opening = [], [], None
        for page in doc:
            words = page.get_text("words", sort=True)
            anchors = sorted((w for w in words if 30 <= w[0] < 62 and DATE.fullmatch(w[4])), key=_center)
            for i, w in enumerate(anchors):
                y = _center(w)
                day = datetime.strptime(w[4], "%d/%m/%Y").date()
                row = _words(words, y - 1.8, y + 1.8, 0, 595)
                history_head = _text(_words(row, y - 1.8, y + 1.8, 90, 226))
                heading = _norm(history_head)
                balances = [x[4] for x in row if x[0] >= 515 and MONEY.fullmatch(x[4])]
                if "saldo anterior" in heading:
                    if opening is not None or len(balances) != 1:
                        raise ValueError("Itaú 1303: saldo anterior ausente ou repetido.")
                    opening = _cents(balances[0])
                    continue
                if heading.startswith("saldo"):
                    if "disponivel dia" in heading and start <= day <= end:
                        if len(balances) != 1:
                            raise ValueError("Itaú 1303: saldo diário não identificado.")
                        checks.append((len(records), _cents(balances[0]), day))
                    continue
                if not start <= day <= end:
                    continue
                values = [x[4] for x in row if 465 <= x[0] < 515 and MONEY.fullmatch(x[4])]
                if len(values) != 1:
                    raise ValueError(f"Itaú 1303: valor ambíguo em {day:%d/%m/%Y}.")
                value = _cents(values[0])
                if not value:
                    raise ValueError("Itaú 1303: lançamento de valor zero.")
                low = max(y - 8.5, (_center(anchors[i-1]) + y) / 2 if i else y - 8.5)
                high = min(y + 8.5, (_center(anchors[i+1]) + y) / 2 if i + 1 < len(anchors) else y + 8.5)
                description = _text(_words(words, low, high, 90, 226))
                name = _text(_words(words, low, high, 227, 360))
                description = " ".join((description, name)).strip()
                if not description:
                    raise ValueError(f"Itaú 1303: histórico ausente em {day:%d/%m/%Y}.")
                records.append((day, value, description))
        if opening is None or not checks or not records:
            raise ValueError("Itaú 1303: saldo inicial, movimentos ou saldo final ausentes.")
        running, prev = opening, 0
        for count, balance, day in checks:
            if count < prev:
                raise ValueError("Itaú 1303: ordenação inválida de lançamentos.")
            running += sum(row[1] for row in records[prev:count])
            if running != balance:
                raise ValueError(f"Itaú 1303: saldo não fecha em {day:%d/%m/%Y}.")
            prev = count
        if prev != len(records):
            raise ValueError("Itaú 1303: últimos lançamentos não conciliados.")
        return _frame(records, "BANCO ITAÚ", "508")

def read_banco_brasil(content):
    doc = _open(content, "Banco do Brasil")
    with doc:
        first = doc[0].get_text()
        if not (re.search(r"Agência\s+8224-4", first, re.I)
                and re.search(r"Conta corrente\s+697-1\s*BMZ", first, re.I)):
            raise ValueError("BB 1303: titular, agência 8224-4 ou conta 697-1 divergente.")
        month = re.search(r"Período do extrato\s*(\d{2})\s*/\s*(20\d{2})", first, re.I)
        if not month:
            raise ValueError("BB 1303: competência não identificada.")
        mm, yy = map(int, month.groups())
        records, checks, opening, closing = [], [], None, None
        for page in doc:
            words = page.get_text("words", sort=True)
            anchors = sorted([w for w in words if 60 <= w[0] < 110 and DATE.fullmatch(w[4])], key=_center)
            for i, w in enumerate(anchors):
                y = _center(w)
                day = datetime.strptime(w[4], "%d/%m/%Y").date()
                row = _words(words, y - 1.8, y + 1.8, 0, 595)
                history = _text(_words(row, y - 1.8, y + 1.8, 273, 400))
                normalized = _norm(history).replace(" ", "")
                balances = [x[4] for x in row if 505 <= x[0] < 540 and MONEY.fullmatch(x[4])]
                balance_signs = [x[4].upper() for x in row if x[0] >= 537 and x[4].upper() in ("C", "D")]
                if normalized == "saldoanterior":
                    if opening is not None or len(balances) != 1 or len(balance_signs) != 1:
                        raise ValueError("BB 1303: saldo anterior ausente ou repetido.")
                    opening = abs(_cents(balances[0])) * (1 if balance_signs[0] == "C" else -1)
                    continue
                if normalized == "saldo":
                    if day.month == mm and day.year == yy:
                        if len(balances) != 1 or len(balance_signs) != 1:
                            raise ValueError("BB 1303: saldo final inválido.")
                        closing = abs(_cents(balances[0])) * (1 if balance_signs[0] == "C" else -1)
                    continue
                if (day.month, day.year) != (mm, yy):
                    continue
                amounts = [x[4] for x in row if 450 <= x[0] < 490 and MONEY.fullmatch(x[4])]
                signs = [x[4].upper() for x in row if 490 <= x[0] < 505 and x[4].upper() in ("C", "D")]
                if len(amounts) != 1 or len(signs) != 1 or not history:
                    raise ValueError(f"BB 1303: lançamento incompleto em {day:%d/%m/%Y}.")
                value = abs(_cents(amounts[0])) * (1 if signs[0] == "C" else -1)
                if not value:
                    raise ValueError("BB 1303: valor zero não esperado.")
                next_y = _center(anchors[i+1]) if i + 1 < len(anchors) else y + 18
                detail = _text(_words(words, y + 2.5, min(next_y - 2, y + 18), 255, 400))
                if detail:
                    history += " " + detail
                records.append((day, value, history))
                if balances and balance_signs:
                    checks.append((len(records), abs(_cents(balances[0])) *
                                   (1 if balance_signs[0] == "C" else -1), day))
        if opening is None or closing is None or not records:
            raise ValueError("BB 1303: saldo inicial, final ou lançamentos não identificados.")
        running, previous = opening, 0
        for count, balance, day in checks:
            running += sum(item[1] for item in records[previous:count])
            if running != balance:
                raise ValueError(f"BB 1303: saldo parcial divergente em {day:%d/%m/%Y}.")
            previous = count
        running += sum(item[1] for item in records[previous:])
        if running != closing:
            raise ValueError("BB 1303: saldo final não confere com os lançamentos.")
        return _frame(records, "BANCO DO BRASIL", "8")

READERS = {"itau": read_itau, "banco_brasil": read_banco_brasil}

def workflow_1303(roles, options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    sheets = {}
    for bank, label in (("itau", "Itaú"), ("banco_brasil", "Banco do Brasil")):
        uploads = roles.get(bank) or []
        if not uploads:
            continue
        periods, frames = set(), []
        for filename, content in uploads:
            if not filename.lower().endswith(".pdf"):
                raise ValueError(f"{label}: envie extratos PDF.")
            frame = READERS[bank](content)
            months = set(frame["DATA"].dt.to_period("M"))
            if len(months) != 1 or months & periods:
                raise ValueError(f"{label}: período repetido ou inconsistente.")
            periods.update(months)
            frames.append(frame)
        combined = pd.concat(frames, ignore_index=True)
        filtered = filter_frame(combined, options)
        if not filtered.empty:
            sheets[label] = filtered.sort_values("DATA", kind="stable")
    if not sheets:
        raise ValueError("Empresa 1303: envie extrato PDF de Itaú ou Banco do Brasil.")
    return gerar_modelo_abas(sheets, date_format="dd/mm/yyyy"), "EMPRESA_1303_MODELO_DOMINIO.xlsx"

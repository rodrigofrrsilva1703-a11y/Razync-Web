"""Match Santander collection credits to the paid-invoice report."""
from datetime import datetime, timedelta
from functools import lru_cache
from decimal import Decimal
from io import BytesIO
import re

import pdfplumber

from app.santander_consolidado_1522 import lines, normalize

DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
MONEY = re.compile(r"\d[\d.]*,\d{2}")
ACCOUNT = re.compile(r"Ag[eê]ncia:\s*(\d+)\s+Conta:\s*(\d+)", re.I)
PERIOD = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(?:a|at[eé])\s+(\d{2}/\d{2}/\d{4})", re.I)
COLLECTION = re.compile(r"^CR COB (?:BLOQ COMP|DINHEIRO) CONF RECEBIMENTO\s*\d+/\d+\s*$")


def cents(value):
    return int(Decimal(value.replace(".", "").replace(",", ".")) * 100)


def statement_identity(text):
    account, period = ACCOUNT.search(text), PERIOD.search(text)
    if not account or not period:
        raise ValueError("Não foi possível identificar agência, conta e período no PDF do Santander.")
    return tuple(map(int, account.groups())), period.groups()


def read_report(content):
    records = []
    texts = []
    with pdfplumber.open(BytesIO(content)) as document:
        for page in document.pages:
            text = page.extract_text() or ""
            texts.append(text)
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            payer = next((word for word in words if word["text"] == "Pagador"), None)
            if payer is None:
                continue
            account_heading = next((word for word in words if word["text"] == "Cobrança"
                                    and word["x0"] > payer["x0"] and abs(word["top"] - payer["top"]) < 15), None)
            if account_heading is None:
                raise ValueError("A coluna Conta Cobrança não foi encontrada no relatório.")
            anchors = []
            for row in lines(words):
                if row[0]["top"] <= payer["top"]:
                    continue
                before = [word["text"] for word in row if word["x0"] < payer["x0"] - 5]
                dates = [value for value in before if DATE.fullmatch(value)]
                values = [value for value in before if MONEY.fullmatch(value)]
                if len(dates) == 2 and len(values) == 3:
                    anchors.append((row[0]["top"], datetime.strptime(dates[1], "%d/%m/%Y").date(), cents(values[1])))
            for index, (top, settled, value) in enumerate(anchors):
                lower = (anchors[index - 1][0] + top) / 2 if index else top - 12
                upper = (anchors[index + 1][0] + top) / 2 if index + 1 < len(anchors) else top + 12
                name_words = [word for word in words if lower <= word["top"] < upper
                              and payer["x0"] - 5 <= word["x0"] < account_heading["x0"] - 6]
                name = " ".join(word["text"] for row in lines(name_words) for word in row)
                if not name or value <= 0:
                    raise ValueError("Boleto liquidado sem pagador ou valor válido.")
                records.append((settled, value, name))
    report = "\n".join(texts)
    count = re.search(r"Quantidade:\s*(\d+)", report)
    total = re.search(r"Valor Total Cobrado\s*R\$\s*(\d[\d.]*,\d{2})", report, re.I)
    if not count or not total or len(records) != int(count[1]) or sum(row[1] for row in records) != cents(total[1]):
        raise ValueError("A quantidade ou o valor cobrado dos boletos lidos não bate com o total do relatório.")
    return statement_identity(report), records


def next_weekday(day):
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def unique_matches(values, targets):
    """Resolve all same-day credits together; return no result for ambiguity."""
    if not values or len(values) > 16 or sum(values) != sum(targets):
        return None
    sums = [0] * (1 << len(values))
    masks = {target: [] for target in targets}
    for mask in range(1, len(sums)):
        bit = mask & -mask
        subtotal = sums[mask] = sums[mask ^ bit] + values[bit.bit_length() - 1]
        if subtotal in masks:
            masks[subtotal].append(mask)

    @lru_cache(maxsize=None)
    def search(index, remaining):
        if index == len(targets):
            return ((),) if not remaining else ()
        solutions = []
        for mask in masks[targets[index]]:
            if mask & remaining != mask:
                continue
            for tail in search(index + 1, remaining ^ mask):
                solutions.append((mask, *tail))
                if len(solutions) == 2:
                    return tuple(solutions)
        return tuple(solutions)

    solutions = search(0, len(sums) - 1)
    return solutions[0] if len(solutions) == 1 else None


def enrich(frame, statement_pdf, report_pdf):
    with pdfplumber.open(BytesIO(statement_pdf)) as document:
        statement = statement_identity(document.pages[0].extract_text() or "")
    report, paid = read_report(report_pdf)
    if statement != report:
        raise ValueError("O extrato e o relatório precisam ser da mesma agência, conta e competência.")
    frame = frame.copy().reset_index(drop=True)
    by_day = {}
    for index, row in frame.iterrows():
        if row["VALOR"] > 0 and COLLECTION.fullmatch(normalize(row["HISTÓRICO"])):
            day = datetime.strptime(str(row["DATA"]), "%d/%m/%Y").date()
            by_day.setdefault(day, []).append(index)
    for day, indices in by_day.items():
        candidates = [(value, payer) for settled, value, payer in paid if next_weekday(settled) == day]
        targets = [int(Decimal(str(frame.at[index, "VALOR"])) * 100) for index in indices]
        solution = unique_matches([value for value, _ in candidates], targets)
        if solution is None:
            continue
        for index, mask in zip(indices, solution):
            frame.at[index, "HISTÓRICO"] = " / ".join(dict.fromkeys(
                payer for position, (_, payer) in enumerate(candidates) if mask & (1 << position)
            ))
    return frame

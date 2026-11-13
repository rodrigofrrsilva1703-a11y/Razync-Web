"""Horeb's Sicredi statement and payment receipts."""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re

import pandas as pd
import pdfplumber


MONEY = r"-?\d+(?:\.\d{3})*,\d{2}"
DATE = r"\d{2}/\d{2}/\d{4}"
MOVEMENT = re.compile(rf"^({DATE})\s+(.+?)\s+({MONEY})\s+({MONEY})$")
ACCOUNT = re.compile(r"\bCooperativa:\s*0726\s+Conta(?: Corrente)?:\s*03573-6\b", re.I)


def _cents(value):
    return int(Decimal(value.replace(".", "").replace(",", ".")) * 100)


def _pages(content):
    with pdfplumber.open(BytesIO(content)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def _validate_account(text):
    if not ACCOUNT.search(text):
        raise ValueError("O PDF não é da conta Sicredi cadastrada para a empresa 1092.")


def _kind(history):
    if history.startswith("LIQUIDACAO BOLETO"):
        return "boleto"
    if re.search(r"\bDARFC\d{4}\b", history):
        return "darf"
    return None


def _key(date, cents, history):
    return date, -cents, _kind(history)


def read_statement(content, account):
    text = "\n".join(_pages(content))
    _validate_account(text)
    booked = re.split(r"Lançamentos Futuros", text, maxsplit=1, flags=re.I)[0]
    opening = re.search(rf"^SALDO ANTERIOR\s+({MONEY})\s*$", booked, re.M)
    if not opening or not re.search(r"^Extrato \(Período", booked, re.M):
        raise ValueError("Envie o PDF do extrato mensal Sicredi com o saldo anterior.")
    balance = _cents(opening[1])
    rows = []
    for line in booked.splitlines():
        if not re.match(rf"^{DATE}\s", line):
            continue
        movement = MOVEMENT.fullmatch(line.strip())
        if not movement:
            raise ValueError("Há uma linha de lançamento ilegível no extrato Sicredi.")
        date, history, amount, closing = movement.groups()
        cents = _cents(amount)
        balance += cents
        if balance != _cents(closing):
            raise ValueError(f"O saldo do extrato Sicredi não fecha em {date}.")
        kind = _kind(history)
        history = re.sub(r"\b\d{11,14}\b", "", history)
        if history.startswith("TED "):
            history = re.sub(r"\s+\d{5,}$", "", history)
        history = " ".join(history.split())
        if kind == "darf":
            history = re.sub(r"\b(DARFC\d{4})\s+\1$", r"\1", history)
        rows.append(("Sicredi", datetime.strptime(date, "%d/%m/%Y"), cents / 100,
                     account if cents > 0 else "", account if cents < 0 else "", history))
    if not rows:
        raise ValueError("Nenhum lançamento foi encontrado no extrato Sicredi.")
    return pd.DataFrame(rows, columns=["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"])


def _field(text, label):
    match = re.search(rf"^{re.escape(label)}:[ \t]*([^\n]+)", text, re.M)
    return match[1].strip() if match else ""


def _read_receipts(content):
    for page in _pages(content):
        _validate_account(page)
        date = _field(page, "Data do Pagamento")
        if "COMPROVANTE DE PAGAMENTO DE DARF" in page:
            code = re.search(r"\bDARFC(\d{4})\b", page)
            history = f"DARF {code[1]}" if code else "DARF"
            amount = _field(page, "Valor Total (R$)")
            kind = "darf"
        else:
            name = _field(page, "Nome do Beneficiário Final")
            if name in {"", "-", "N/A"}:
                name = _field(page, "Razão Social do Beneficiário")
            history = f"BOLETO {name}" if name and name not in {"-", "N/A"} else ""
            amount = _field(page, "Valor Pago (R$)")
            kind = "boleto"
        if not re.fullmatch(DATE, date) or not re.fullmatch(MONEY, amount) or not history:
            raise ValueError("Um comprovante Sicredi não contém data, valor pago ou identificação legível.")
        if _cents(amount) <= 0:
            raise ValueError("Um comprovante Sicredi contém valor pago inválido.")
        authentication = _field(page, "Autenticação Eletrônica")
        if not authentication:
            raise ValueError("Um comprovante Sicredi não contém autenticação eletrônica legível.")
        yield (datetime.strptime(date, "%d/%m/%Y"), _cents(amount), kind), (authentication, history)


def enrich(frame, receipt_pdfs):
    """Only replace histories when a payment has a unique statement and receipt match."""
    receipts = defaultdict(set)
    for content in receipt_pdfs:
        for key, receipt in _read_receipts(content):
            receipts[key].add(receipt)
    keys = [_key(date, round(amount * 100), history)
            for date, amount, history in zip(frame["DATA"], frame["VALOR"], frame["HISTÓRICO"])]
    counts = Counter(keys)
    result = frame.copy()
    result["HISTÓRICO"] = [
        ("Pago: " if amount < 0 else "Recebido: ") +
        (next(iter(receipts[key]))[1] if counts[key] == 1 and len(receipts[key]) == 1 else history)
        for key, amount, history in zip(keys, frame["VALOR"], frame["HISTÓRICO"])
    ]
    return result

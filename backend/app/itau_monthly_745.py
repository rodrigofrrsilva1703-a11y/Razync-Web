"""Read the Itaú Empresas monthly statement for the 745 workflow."""
import re
from datetime import date
from decimal import Decimal
from io import BytesIO

import pandas as pd
from pypdf import PdfReader

from app.excel import COLUNAS

MONTHS = "jan fev mar abr mai jun jul ago set out nov dez".split()
HEADER = re.compile(r"extrato\s*mensal\s+ag\s+(\d+)\s+cc\s+([\d.-]+)\s+(\w{3})\s+(\d{4})\s+(\d+)\s*\|\s*(\d+)", re.I)
TABLE = re.compile(r"\bdata\s+descrição\s+entradas\s+R\$.*?saídas\s+R\$.*?saldo\s+R\$", re.I)
MONEY = r"(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
MOVEMENT = re.compile(rf"\s{{2,}}({MONEY}-?)(?=\s|$)")
TOTAL = re.compile(rf"^\s*total\s+({MONEY})\s*$", re.M | re.I)
INTERNAL = re.compile(r"^(?:apl|res)\s+aplic\s+aut\s+mais\b", re.I)


def amount(raw):
    return Decimal(raw.rstrip("-").replace(".", "").replace(",", ".")) * (-1 if raw.endswith("-") else 1)


def read_statement(content):
    pages = [page.extract_text(extraction_mode="layout") or "" for page in PdfReader(BytesIO(content)).pages]
    if not pages:
        raise ValueError("O PDF do Itaú está vazio.")
    header = HEADER.search(pages[0])
    if not header or header[3].lower() not in MONTHS:
        raise ValueError("Envie o Extrato Mensal Itaú Empresas no formato da empresa 745.")
    month = MONTHS.index(header[3].lower()) + 1
    year = int(header[4])
    expected = [amount(value) for value in TOTAL.findall(pages[0])[:2]]
    if len(expected) != 2:
        raise ValueError("Não foi possível conferir os totais de entradas e saídas do extrato.")

    entries = []
    current_day = None
    for number, page in enumerate(pages, 1):
        page_header = HEADER.search(page)
        if (not page_header or page_header.groups()[:4] != header.groups()[:4]
                or int(page_header[5]) != number or int(page_header[6]) != len(pages)):
            raise ValueError("O PDF reúne páginas de competências diferentes ou fora do formato esperado.")
        table = None
        for line in page.splitlines():
            if "totalizador de aplicações automáticas" in line.casefold() or "Conta Corrente | Aplicações" in line:
                break
            if match := TABLE.search(line):
                description_start = line.casefold().index("descrição", match.start())
                balance_start = line.casefold().index("saldo", match.start())
                table = (description_start, balance_start)
                continue
            if table is None:
                continue
            description_start, balance_start = table
            prefix = line[:description_start]
            if day := re.search(r"(\d{2})/(\d{2})\s*$", prefix):
                current_day = date(year, month, int(day[1])) if int(day[2]) == month else None
            segment = line[description_start:]
            match = MOVEMENT.search(segment)
            if match is None or description_start + match.start(1) >= balance_start or current_day is None:
                continue
            description = " ".join(segment[:match.start()].split())
            if not description or description.casefold().startswith(("saldo", "(créditos)")) or INTERNAL.match(description):
                continue
            value = amount(match[1])
            if value:
                entries.append((current_day, description, value))

    credits = sum(value for _, _, value in entries if value > 0)
    debits = -sum(value for _, _, value in entries if value < 0)
    if not entries or [credits, debits] != expected:
        raise ValueError(
            "Os lançamentos lidos não fecham com os totais do PDF do Itaú. "
            "Confira se o extrato mensal está completo."
        )
    return pd.DataFrame([
        ("BANCO ITAÚ", pd.Timestamp(day), float(value), "508" if value > 0 else "",
         "508" if value < 0 else "", f"{'Recebido' if value > 0 else 'Pago'}: {description}")
        for day, description, value in entries
    ], columns=COLUNAS)

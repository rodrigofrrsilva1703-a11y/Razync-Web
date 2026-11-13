"""Empresa 1050 — F2R: extrato mensal Itaú (conta contábil 508).

O resumo do Itaú inclui a movimentação consolidada de conta corrente e
aplicações automáticas: resgates internos não são lançados duas vezes.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
import unicodedata

import fitz
import pandas as pd

COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
MONEY = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}-?$|^\d+,\d{2}-?$")
DAY = re.compile(r"^\d{2}/\d{2}$")
MONTHS = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
          "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
PRIVATE = re.compile(
    r"(?:\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|"
    r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11,14}\b)"
)

def _normalize(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()

def _cents(value):
    raw = str(value).strip()
    negative = raw.startswith("-") or raw.endswith("-")
    amount = Decimal(raw.strip("-").replace(".", "").replace(",", ".")) * 100
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError("Itaú 1050: valor financeiro inválido.")
    return int(amount) * (-1 if negative else 1)

def _lines(page):
    groups = []
    for word in sorted(page.get_text("words", sort=True),
                       key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        center = (word[1] + word[3]) / 2
        if groups and center - groups[-1][0] < 2.3:
            groups[-1][1].append(word)
        else:
            groups.append([center, [word]])
    return [(y, sorted(words, key=lambda w: w[0])) for y, words in groups]

def _text(words, a=0, b=999):
    return " ".join(w[4] for w in words if a <= w[0] < b).strip()

def read_statement(content):
    if not content.startswith(b"%PDF") or len(content) > 35 * 1024 * 1024:
        raise ValueError("Itaú 1050: envie o extrato mensal em PDF válido (até 35 MB).")
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError("Itaú 1050: não foi possível abrir o PDF.") from exc
    with document:
        if not 1 <= len(document) <= 30:
            raise ValueError("Itaú 1050: quantidade de páginas inválida.")
        first = document[0].get_text()
        header = _normalize(first)
        if not (re.search(r"ag\s+0735\s+cc\s+14341-4", header)
                and "f2r excelencia" in header):
            raise ValueError("Itaú 1050: titular, agência 0735 ou conta 14341-4 divergente.")
        period = re.search(r"ag\s+0735\s+cc\s+14341-4\s+([a-z]{3})\s+(20\d{2})", header)
        if not period or period.group(1) not in MONTHS:
            raise ValueError("Itaú 1050: competência mensal não identificada.")
        month, year = MONTHS[period.group(1)], int(period.group(2))
        # Ler os totais expressos no resumo da conta corrente (página 1).
        summary = re.search(
            r"01\.\s*conta corrente e aplicacoes automaticas\s+"
            r"r\$\s*([\d.,]+)\s+r\$\s*([\d.,]+)", header)
        totals = re.search(
            r"total entradas\s+total saidas\s*\(creditos\)\s*\(debitos\)\s*"
            r"r\$\s*([\d.,]+)\s+r\$\s*([\d.,]+)", header)
        if not summary or not totals:
            raise ValueError("Itaú 1050: resumo mensal e totais não encontrados.")
        initial, final = _cents(summary.group(1)), _cents(summary.group(2))
        expected_in, expected_out = _cents(totals.group(1)), _cents(totals.group(2))
        rows = []
        within = False
        current_date = None
        for page in document:
            if "Conta Corrente | Movimentação" in page.get_text():
                within = True
            if not within:
                continue
            for y, words in _lines(page):
                entire = _normalize(_text(words))
                if ("conta corrente | aplicacoes automaticas" in entire
                        or "conta corrente | cheque especial" in entire
                        or "totalizador de aplicacoes automaticas" in entire):
                    within = False
                    break
                dates = [w[4] for w in words if 145 <= w[0] < 180 and DAY.fullmatch(w[4])]
                if dates:
                    day, mm = map(int, dates[0].split("/"))
                    try:
                        current_date = date(year, mm, day)
                    except ValueError as exc:
                        raise ValueError("Itaú 1050: data bancária inválida.") from exc
                    if (current_date.year, current_date.month) != (year, month):
                        current_date = None
                if current_date is None:
                    continue
                label = _text(words, 202, 365)
                normalized = _normalize(label)
                if not label:
                    continue
                # Saldos e transferências internas do Aplic Aut Mais aparecem
                # na própria movimentação, mas são excluídos do total do banco.
                if (normalized.startswith(("saldo", "res aplic aut", "aplic aut mais"))
                        or normalized.startswith("totalizador")):
                    continue
                credits = [w[4] for w in words if 365 <= w[0] < 414 and MONEY.fullmatch(w[4])]
                debits = [w[4] for w in words if 420 <= w[0] < 476 and MONEY.fullmatch(w[4])]
                if not credits and not debits:
                    continue
                if len(credits) + len(debits) != 1:
                    raise ValueError(f"Itaú 1050: valores ambíguos em {current_date:%d/%m/%Y}.")
                if credits:
                    value = abs(_cents(credits[0]))
                else:
                    value = -abs(_cents(debits[0]))
                if not value:
                    continue
                history = " ".join(PRIVATE.sub("", label).split())
                rows.append({
                    "DESCRIÇÃO": "BANCO ITAÚ",
                    "DATA": pd.Timestamp(current_date),
                    "VALOR": value / 100,
                    "DÉBITO": "508" if value > 0 else "",
                    "CRÉDITO": "508" if value < 0 else "",
                    "HISTÓRICO": ("Recebido: " if value > 0 else "Pago: ") + history,
                })
            if not within:
                break
        income = sum(round(r["VALOR"] * 100) for r in rows if r["VALOR"] > 0)
        expenses = -sum(round(r["VALOR"] * 100) for r in rows if r["VALOR"] < 0)
        if not rows or income != expected_in or expenses != expected_out:
            raise ValueError(
                "Itaú 1050: os lançamentos encontrados não conferem com os totais "
                "de entradas e saídas do resumo mensal."
            )
        if initial + income - expenses != final:
            raise ValueError("Itaú 1050: saldo final não confere com o resumo mensal.")
        return pd.DataFrame(rows, columns=COLUNAS)

def workflow_1050(roles, options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    uploads = roles.get("itau") or []
    if not uploads:
        raise ValueError("Empresa 1050: envie um extrato mensal Itaú em PDF.")
    months, frames = set(), []
    for filename, content in uploads:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1050: o extrato deve ser PDF.")
        frame = read_statement(content)
        period = str(frame["DATA"].dt.to_period("M").iloc[0])
        if period in months:
            raise ValueError("Empresa 1050: extrato mensal repetido.")
        months.add(period)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    filtered = filter_frame(combined, options)
    if filtered.empty:
        raise ValueError("Empresa 1050: sem lançamentos no período solicitado.")
    return (gerar_modelo_abas({"Itaú": filtered.sort_values("DATA", kind="stable")},
                              date_format="dd/mm/yyyy"),
            "EMPRESA_1050_ITAU_MODELO_DOMINIO.xlsx")

"""Itaú extrato mensal consolidado da empresa 1058, validado contra totais do PDF."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
import re

import pandas as pd
from pypdf import PdfReader

MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
HEADER = re.compile(r'extrato\s*mensal\s+ag\s+(\d+)\s+cc\s+([\d.-]+)\s*(\w{3})\s+(20\d{2})\s+(\d+)\s*\|\s*(\d+)', re.I)
DATE = re.compile(r'(?<!\d)(\d{2})/(\d{2})(?!\d)')
MONEY = re.compile(r'(?<!\d)(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}-?(?!\d)')
PREFIX = re.compile(r'(?i)(?<!\w)(Sispag\b|BOLETO PAGO\b|PIX ENVIADO\b|IOF\b|JUROS LIMITE DA CONTA\b|Res Aplic Aut Mais\b|Rend Pago Aplic Aut Mais\b|Apl Aplic Aut Mais\b)')
AUTO = re.compile(r'^(?:Apl Aplic Aut Mais|Res Aplic Aut Mais)\b', re.I)


def cents(value):
    return int(Decimal(value.rstrip('-').replace('.', '').replace(',', '.')) * 100) * (-1 if value.endswith('-') else 1)


def looks_like_quarteto_itau(content):
    if not content.startswith(b'%PDF'):
        return False
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        head = reader.pages[0].extract_text() or ''
    except Exception:
        return False
    return bool(re.search(r'extrato\s*mensal\s+ag\s+7111\s+cc\s+99743-8\s*(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s+20\d{2}', head, re.I))


def read_itau_monthly(content):
    if not content.startswith(b'%PDF') or len(content) > 25 * 1024 * 1024:
        raise ValueError('Envie o extrato mensal Itaú original em PDF (até 25 MB).')
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if not 1 <= len(reader.pages) <= 20:
            raise ValueError('Quantidade de páginas do extrato Itaú inválida.')
        pages = [p.extract_text(extraction_mode='layout') or '' for p in reader.pages]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Não foi possível abrir o extrato Itaú PDF.') from exc
    head = HEADER.search(pages[0])
    if not head or head.group(1) != '7111' or head.group(2) != '99743-8' or head.group(3).lower() not in MONTHS:
        raise ValueError('O extrato não corresponde ao Itaú, agência 7111, conta 99743-8 da empresa 1058.')
    month = MONTHS.index(head.group(3).lower()) + 1
    year, expected_pages = int(head.group(4)), int(head.group(6))
    if expected_pages != len(pages):
        raise ValueError('O extrato mensal Itaú está incompleto.')
    if 'QUARTETO DE OBRAS' not in pages[0].upper():
        raise ValueError('Titular do extrato não corresponde à empresa 1058.')
    summary = re.findall(r'R\$\s*([\d.]+,\d{2})', pages[0])
    if len(summary) < 4:
        raise ValueError('Totais do extrato mensal Itaú não identificados.')
    opening, closing, credit_expected, debit_expected = [cents(x) for x in summary[:4]]
    entries = []
    current = None
    finished = False
    for page_number, page_text in enumerate(pages, 1):
        match = HEADER.search(page_text)
        if not match or match.group(1, 2, 3, 4, 6) != head.group(1, 2, 3, 4, 6) or int(match.group(5)) != page_number:
            raise ValueError(f'Cabeçalho incompatível na página {page_number} do extrato Itaú.')
        active = False
        if finished:
            continue
        for line in page_text.splitlines():
            if ('Conta Corrente' in line and 'Movimentação' in line) or (page_number > 1 and re.search(r'\bdata\s+descrição\s+entradas\s+R\$', line, re.I)):
                active = True
                continue
            if active and ('totalizador de aplicações automáticas' in line or ('Conta Corrente' in line and 'Aplicações Automáticas' in line)):
                finished = True
                active = False
            if not active:
                continue
            day = DATE.search(line)
            if day and int(day.group(2)) == month:
                try:
                    current = date(year, month, int(day.group(1)))
                except ValueError as exc:
                    raise ValueError('Data inválida na movimentação Itaú.') from exc
            name = PREFIX.search(line)
            if not name:
                continue
            tail = line[name.start():]
            amounts = list(MONEY.finditer(tail))
            if not amounts or current is None:
                raise ValueError(f'Lançamento incompleto na página {page_number} do extrato Itaú.')
            history = ' '.join(tail[:amounts[0].start()].split())
            value = cents(amounts[0].group())
            if not value or not history:
                raise ValueError('Lançamento Itaú sem valor ou histórico.')
            entries.append((current, history, value))
    if not entries:
        raise ValueError('Nenhum lançamento reconhecido na movimentação da conta corrente Itaú.')
    credits = sum(value for _, history, value in entries if not AUTO.match(history) and value > 0)
    debits = -sum(value for _, history, value in entries if not AUTO.match(history) and value < 0)
    if (credits, debits) != (credit_expected, debit_expected):
        raise ValueError(f'Totais do extrato Itaú divergentes: créditos {credits/100:.2f} e débitos {debits/100:.2f}.')
    if opening + credits - debits != closing:
        raise ValueError('O saldo inicial e final não fecham com o movimento mensal Itaú.')
    return pd.DataFrame([{
        'DESCRIÇÃO': 'BANCO ITAÚ', 'DATA': pd.Timestamp(day), 'VALOR': value / 100,
        'DÉBITO': '514' if value > 0 else '', 'CRÉDITO': '514' if value < 0 else '',
        'HISTÓRICO': ('Recebido: ' if value > 0 else 'Pago: ') + history,
    } for day, history, value in entries])

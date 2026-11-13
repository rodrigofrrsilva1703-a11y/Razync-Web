"""Leitor do extrato de conta corrente BB com valor e sinal entre parênteses."""
from datetime import datetime
import re

import fitz

from app.itau_1399 import _ocr_page
from app.company_1151 import frame

DATE = re.compile(r"\d{2}/\d{2}/\d{3,4}")
MONEY = re.compile(r"\d[\d.,]*[,.]\d{2}")
IDENTITY = re.compile(r"\b301-8\s+Conta:\s+260957-6\b", re.I)


def _date(text):
    return datetime.strptime(text, "%d/%m/%Y").date()


def _amount(words):
    tokens = [w[4] for w in words]
    amounts = [token for token in tokens if MONEY.fullmatch(token)]
    signs = [token for token in tokens if token in {"(+)", "(-)"}]
    if len(amounts) != 1 or len(signs) != 1:
        raise ValueError("Valor ou sinal ilegível em um lançamento do Banco do Brasil.")
    value = re.sub(r"[.,]", "", amounts[0])
    return int(value) * (-1 if signs[0] == "(-)" else 1)


def _history(words):
    lines = []
    for word in sorted(words, key=lambda w: w[1]):
        if not lines or word[1] - lines[-1][0][1] > 4:
            lines.append([])
        lines[-1].append(word)
    text = " ".join(w[4] for line in lines for w in sorted(line, key=lambda w: w[0]))
    text = re.sub(r"\b\d{2}/\d{2}\s+\d{2}:\d{2}\b|\b\d{11,14}\b", "", text)
    return " ".join(text.split()).strip(" -|")


def read_statement(content):
    if not content.startswith(b"%PDF") or len(content) > 25 * 1024 * 1024:
        raise ValueError("Envie um extrato Banco do Brasil em PDF de até 25 MB.")
    with fitz.open(stream=content, filetype="pdf") as doc:
        if not 1 <= len(doc) <= 20:
            raise ValueError("O extrato Banco do Brasil precisa ter de 1 a 20 páginas.")
        pages = []
        for page in doc:
            words = _ocr_page(page)
            header = " ".join(w[4] for w in words if w[1] < 94)
            if "Extrato de Conta Corrente" not in header or not IDENTITY.search(header):
                raise ValueError("O extrato Banco do Brasil não corresponde à empresa 1535.")
            dates = _ocr_page(page, clip=fitz.Rect(27, 109, 90, page.rect.height))
            anchors = sorted((w[1], w[4]) for w in dates if DATE.fullmatch(w[4]))
            if not anchors:
                raise ValueError("Nenhuma data legível em uma página do extrato Banco do Brasil.")
            pages.append((words, dates, anchors))

        rows = []
        running = opening_day = closing_day = None
        last_day = None
        needs_checkpoint = False
        for page_index, (words, _, anchors) in enumerate(pages):
            for i, (top, date_text) in enumerate(anchors):
                amount = _amount([w for w in words if w[0] >= 480 and top - 2 <= w[1] <= top + 10])
                lower = top - 8 if i == 0 or top - anchors[i-1][0] >= 24 else top - 2
                upper = anchors[i+1][0] - 8 if i+1 < len(anchors) and anchors[i+1][0] - top >= 24 else top + 19
                history_words = [w for w in words if 264 <= w[0] < 480 and lower <= w[1] < upper]
                if len(date_text) == 9:
                    if i != len(anchors) - 1 or page_index + 1 >= len(pages):
                        raise ValueError("Data incompleta no extrato Banco do Brasil.")
                    next_words, next_dates, next_anchors = pages[page_index + 1]
                    split = [w[4] for w in next_dates if w[1] < next_anchors[0][0] - 8 and re.fullmatch(r"\d", w[4])]
                    if len(split) != 1:
                        raise ValueError("Data dividida entre páginas não reconhecida no Banco do Brasil.")
                    date_text += split[0]
                    history_words.extend((x, y + 1000, x1, y1 + 1000, value)
                                         for x, y, x1, y1, value in next_words
                                         if 264 <= x < 480 and 105 <= y < next_anchors[0][0] - 8)
                history = _history(history_words)
                label = history.casefold()
                if label.startswith("saldo anterior"):
                    if running is not None:
                        raise ValueError("Saldo anterior repetido no extrato Banco do Brasil.")
                    opening_day = _date(date_text)
                    running = amount
                elif label.startswith("saldo do dia") or label == "saldo":
                    if running != amount:
                        raise ValueError("Os valores lidos não fecham com o saldo do Banco do Brasil.")
                    needs_checkpoint = False
                    if label == "saldo":
                        closing_day = _date(date_text)
                else:
                    day = _date(date_text)
                    if running is None or closing_day or not history or not amount or day < (last_day or opening_day):
                        raise ValueError("Lançamento inconsistente no extrato Banco do Brasil.")
                    running += amount
                    last_day = day
                    needs_checkpoint = True
                    rows.append((day, amount, history))
        if not rows or closing_day is None or needs_checkpoint or last_day > closing_day:
            raise ValueError("O extrato Banco do Brasil está sem movimentos ou sem saldo de fechamento.")
        return frame(rows, "BANCO DO BRASIL", "8")

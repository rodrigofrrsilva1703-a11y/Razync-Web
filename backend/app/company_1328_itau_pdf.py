"""Itaú A&Z (1328): conferência independente do PDF digitalizado por OCR.

Lê movimentos e fecha saldos diários em centavos. Só considera leituras
alternativas de OCR quando o fechamento com o extrato for inequívoco.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from itertools import product
import os
import re
import unicodedata

import fitz
import numpy as np
import pandas as pd
from PIL import Image
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
import pytesseract

DATE = re.compile(r"^\d{2}/\d{2}/20\d{2}$")
PDF_COLUMNS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]


def _norm(value):
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^A-Z0-9]", "", "".join(
        x for x in raw if not unicodedata.combining(x)
    ).upper())


def _center(word):
    return word["y"] + word["height"] / 2


def _cents(word):
    """Tolerar pontuação duplicada pelo OCR, jamais arredondar centavos."""
    digits = re.sub(r"\D", "", str(word))
    return int(digits) if 3 <= len(digits) <= 10 else None


def _ocr(image, zoom, mode):
    try:
        data = pytesseract.image_to_data(
            image, lang="eng", config=f"--psm {mode}",
            output_type=pytesseract.Output.DICT, timeout=90,
        )
    except Exception as exc:
        raise ValueError("Itaú 1328: OCR do PDF indisponível ou interrompido.") from exc
    return [
        {"text": str(data["text"][i]).strip(),
         "x": data["left"][i] / zoom, "y": data["top"][i] / zoom,
         "width": data["width"][i] / zoom,
         "height": data["height"][i] / zoom}
        for i in range(len(data["text"])) if str(data["text"][i]).strip()
    ]


def _sign(rgb, word, zoom):
    """No PDF original, o banco imprime créditos verdes e débitos vermelhos."""
    h, w = rgb.shape[:2]
    x0 = max(0, int(word["x"] * zoom))
    y0 = max(0, int(word["y"] * zoom))
    x1 = min(w, x0 + max(1, int(word["width"] * zoom)))
    y1 = min(h, y0 + max(1, int(word["height"] * zoom)))
    if x0 >= x1 or y0 >= y1:
        raise ValueError("Itaú 1328: cor do valor não identificável.")
    pixels = rgb[y0:y1, x0:x1].reshape(-1, 3).astype(np.int32)
    pixels = pixels[pixels.max(axis=1) < 210]
    if len(pixels) == 0:
        raise ValueError("Itaú 1328: valor não reconhecido no PDF.")
    red = int(((pixels[:, 0] > pixels[:, 1] * 1.24) &
               (pixels[:, 0] > pixels[:, 2] * 1.20)).sum())
    green = int(((pixels[:, 1] > pixels[:, 0] * 1.14) &
                 (pixels[:, 1] > pixels[:, 2] * 0.92)).sum())
    if max(red, green) < 8 or min(red, green) * 5 > max(red, green):
        raise ValueError("Itaú 1328: não foi possível confirmar débito/crédito pela cor.")
    return 1 if green > red else -1


def _candidates(first, second, y, balance, rgb, zoom):
    results = []
    for words in (first, second):
        matches = [
            w for w in words
            if abs(_center(w) - y) < 6.0
            and (511 <= w["x"] < 595 if balance else 455 < w["x"] < 513)
            and _cents(w["text"]) is not None
        ]
        if len(matches) > 1:
            raise ValueError("Itaú 1328: valores sobrepostos no OCR.")
        if not matches:
            continue
        w = matches[0]
        number = _cents(w["text"])
        if not balance:
            number *= _sign(rgb, w, zoom)
        if number not in results:
            results.append(number)
    return results


def _scan_bitmap(raw, width, height, zoom):
    image = Image.frombytes("RGB", (width, height), raw)
    first = _ocr(image, zoom, 11)
    second = _ocr(image, zoom, 6)
    rgb = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))
    return first, second, rgb


def _extract_pages(content):
    if (not isinstance(content, bytes) or not content.startswith(b"%PDF")
            or len(content) > 35 * 1024 * 1024):
        raise ValueError("Itaú 1328: envie o extrato bancário original PDF (até 35 MB).")
    with fitz.open(stream=content, filetype="pdf") as pdf:
        if not 1 <= len(pdf) <= 25:
            raise ValueError("Itaú 1328: quantidade inválida de páginas no PDF.")
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="itau1328-ocr") as pool:
            pending = {}
            zoom = 3

            def submit(idx):
                page = pdf[idx]
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(zoom, zoom),
                    colorspace=fitz.csRGB, alpha=False,
                )
                pending[idx] = pool.submit(
                    _scan_bitmap, pix.samples, pix.width, pix.height, zoom
                )

            for idx in range(min(3, len(pdf))):
                submit(idx)
            for idx in range(len(pdf)):
                first, second, rgb = pending.pop(idx).result()
                if idx + 3 < len(pdf):
                    submit(idx + 3)
                if idx == 0:
                    header = " ".join(w["text"] for w in first + second if w["y"] < 110)
                    compact = _norm(header)
                    if not ("INDUSTRIA" in compact and "COMERCIO" in compact
                            and "2782" in compact and "00996462" in compact):
                        raise ValueError(
                            "Itaú 1328: empresa, agência 2782 ou conta 0099646-2 "
                            "não correspondem ao PDF."
                        )
                date_words = [
                    w for w in first if 25 <= w["x"] < 65
                    and DATE.fullmatch(w["text"])
                ]
                other_dates = [
                    w for w in second if 25 <= w["x"] < 65
                    and DATE.fullmatch(w["text"])
                ]
                for other in other_dates:
                    if not any(abs(_center(w) - _center(other)) < 5.0
                               for w in date_words):
                        raise ValueError(
                            f"Itaú 1328: data ilegível na página {idx + 1} do PDF."
                        )
                for dated in date_words:
                    y = _center(dated)
                    near = sorted(
                        (w for w in first if abs(_center(w) - y) < 6),
                        key=lambda w: w["x"],
                    )
                    label = " ".join(
                        w["text"] for w in near if 80 <= w["x"] < 222
                    ).strip()
                    opening = "SALDOANTERIOR" in _norm(label)
                    balance = "SALDOTOTAL" in _norm(label)
                    if not label:
                        raise ValueError(
                            f"Itaú 1328: descrição ilegível na página {idx + 1}."
                        )
                    values = _candidates(
                        first, second, y, opening or balance, rgb, zoom
                    )
                    if not values:
                        raise ValueError(
                            f"Itaú 1328: valor ilegível na página {idx + 1} "
                            f"({dated['text']})."
                        )
                    day = datetime.strptime(dated["text"], "%d/%m/%Y").date()
                    yield {
                        "date": day,
                        "label": label,
                        "type": ("opening" if opening else "balance"
                                 if balance else "movement"),
                        "values": values,
                    }


def _resolve_day(movements, reported, opening, day):
    """Mudar uma leitura OCR somente quando existir solução única e verificável."""
    primary = sum(item["values"][0] for item in movements)
    difference = reported - opening - primary
    if difference == 0:
        return [item["values"][0] for item in movements]
    ambiguous = [
        (idx, item["values"]) for idx, item in enumerate(movements)
        if len(item["values"]) > 1
    ]
    if len(ambiguous) > 12:
        raise ValueError(f"Itaú 1328: leitura excessivamente ambígua em {day:%d/%m/%Y}.")
    solutions = []
    for alternatives in product(*[
        range(len(choices)) for _, choices in ambiguous
    ]):
        delta = sum(
            choices[selected] - choices[0]
            for (_, choices), selected in zip(ambiguous, alternatives)
        )
        if delta == difference:
            changed = sum(selected != 0 for selected in alternatives)
            solutions.append((changed, alternatives))
    if not solutions:
        raise ValueError(
            f"Itaú 1328: movimentos não fecham o saldo em {day:%d/%m/%Y}. "
            "Confira a legibilidade do extrato."
        )
    minimum = min(score for score, _ in solutions)
    best = [s for score, s in solutions if score == minimum]
    if len(best) != 1:
        raise ValueError(
            f"Itaú 1328: OCR com mais de uma interpretação em {day:%d/%m/%Y}."
        )
    selected = [item["values"][0] for item in movements]
    for (idx, choices), choice in zip(ambiguous, best[0]):
        selected[idx] = choices[choice]
    return selected


def read_statement(content):
    opening = running = current_day = None
    movements = []
    rows = []
    daily = []
    for item in _extract_pages(content):
        kind, day = item["type"], item["date"]
        if kind == "opening":
            if opening is not None or rows or movements:
                raise ValueError("Itaú 1328: saldo anterior duplicado ou fora de ordem.")
            if len(item["values"]) > 1 and item["values"][0] != item["values"][1]:
                raise ValueError("Itaú 1328: saldo anterior ilegível.")
            opening = running = item["values"][0]
            continue
        if opening is None:
            raise ValueError("Itaú 1328: saldo anterior não identificado.")
        if current_day is None:
            current_day = day
        if kind == "movement":
            if day != current_day:
                raise ValueError(
                    f"Itaú 1328: faltou o saldo diário de {current_day:%d/%m/%Y}."
                )
            movements.append(item)
            continue
        if kind == "balance":
            if day != current_day or not movements:
                raise ValueError(
                    f"Itaú 1328: saldo diário sem movimentos em {day:%d/%m/%Y}."
                )
            reported = item["values"][0]
            values = _resolve_day(movements, reported, running, day)
            for movement, value in zip(movements, values):
                rows.append({
                    "DESCRIÇÃO": "BANCO ITAÚ",
                    "DATA": pd.Timestamp(day),
                    "VALOR": value / 100,
                    "DÉBITO": "508" if value > 0 else "",
                    "CRÉDITO": "508" if value < 0 else "",
                    "HISTÓRICO": ("Recebido: " if value > 0 else "Pago: ")
                                 + movement["label"],
                })
            running = reported
            daily.append({
                "DATA": pd.Timestamp(day),
                "SALDO BANCO": reported / 100,
                "QUANTIDADE": len(movements),
            })
            movements = []
            current_day = None
    if movements:
        raise ValueError("Itaú 1328: PDF terminou com movimentos sem saldo diário.")
    if opening is None or not rows or not daily:
        raise ValueError("Itaú 1328: PDF sem saldos e movimentos completos.")
    if len({row["DATA"].to_period("M") for row in rows}) != 1:
        raise ValueError("Itaú 1328: extrato contém mais de uma competência.")
    if sum(round(row["VALOR"] * 100) for row in rows) != running - opening:
        raise ValueError("Itaú 1328: saldo final não confere com movimentações.")
    frame = pd.DataFrame(rows, columns=PDF_COLUMNS)
    frame.attrs["opening_balance_cents"] = opening
    frame.attrs["closing_balance_cents"] = running
    frame.attrs["daily_balances"] = daily
    return frame

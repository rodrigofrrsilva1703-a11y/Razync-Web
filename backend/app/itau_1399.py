"""Empresa 1399: extrato Itaú 7111 / 0097478-3, saldos diários em centavos."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re

import fitz
import pandas as pd

from app.history_names import join_history_description

COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
DATE = re.compile(r"\d{2}/\d{2}/20\d{2}")
MONEY = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}")
PRIVATE = re.compile(
    r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|"
    r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|"
    r"\b\d{11,14}\b"
)


def cents(text):
    return int(Decimal(text.replace(".", "").replace(",", "."))*100)


def _center(word):
    return (word[1] + word[3])/2


def _ocr_page(page, *, clip=None):
    from PIL import Image
    import pytesseract

    dpi = 300
    pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False, clip=clip)
    image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
    data = pytesseract.image_to_data(image, lang="eng", config="--psm 6",
                                     output_type=pytesseract.Output.DICT, timeout=20)
    scale = 72 / dpi
    words = []
    for i, value in enumerate(data["text"]):
        if not value.strip():
            continue
        x, y = pixmap.x + data["left"][i], pixmap.y + data["top"][i]
        words.append((x * scale, y * scale, (x + data["width"][i]) * scale,
                      (y + data["height"][i]) * scale, value.strip()))
    return words


def read_statement(content, *, holder=r"JETMAQ\s+COMERCIAL\s+DE\s+MAQUINAS",
                   tax_id="27.514.567/0001-32", agency="7111", account="0097478-3",
                   accounting_account="508", salary_names=(), allow_ocr=False, include_blocked_balance=False):
    if not content.startswith(b"%PDF") or len(content)>35*1024*1024:
        raise ValueError("Envie o extrato Itaú PDF válido de até 35 MB.")
    try:
        doc = fitz.open(stream=content,filetype="pdf")
    except Exception as exc:
        raise ValueError("Não foi possível abrir o extrato Itaú.") from exc
    with doc:
        if not 1<=len(doc)<=30:
            raise ValueError("Número de páginas do Itaú inválido.")
        first=doc[0].get_text()
        first_words = _ocr_page(doc[0]) if allow_ocr and not first.strip() else None
        account_header = first
        if first_words is not None:
            first = " ".join(word[4] for word in first_words if word[1] < 205)
            account_header = " ".join(word[4] for word in first_words
                                      if word[0] > 400 and word[1] < 120)
        account_number, check_digit = account.lstrip("0").split("-", 1)
        account_pattern = rf"0*{re.escape(account_number)}-\s*{re.escape(check_digit)}"
        if (not re.search(holder, first, re.I)
            or (tax_id and tax_id not in first)
            or not re.search(rf"(?<!\d){re.escape(agency)}\s+Conta\s+{account_pattern}\b", account_header, re.I)):
            raise ValueError("Titular ou agência/conta Itaú não corresponde à empresa selecionada.")
        period = re.search(
            (r"Lançamentos do período:\s*" if first_words is None else "")
            + r"(\d{2}/\d{2}/20\d{2})\s+at[ée]\s+(\d{2}/\d{2}/20\d{2})",
            first,re.I)
        if not period:
            raise ValueError("Período do extrato Itaú não encontrado.")
        start,end=(datetime.strptime(period[i],"%d/%m/%Y").date() for i in (1,2))
        if start>end or (start.year,start.month)!=(end.year,end.month):
            raise ValueError("Extrato Itaú deve ter somente uma competência.")
        opening=None
        transactions=[]
        checks=[]
        for page_index, page in enumerate(doc):
            words = first_words if page_index == 0 and first_words is not None else page.get_text("words", sort=True)
            scanned = page_index == 0 and first_words is not None
            if allow_ocr and not words:
                words = _ocr_page(page)
                scanned = True
            merchant_words = (_ocr_page(page, clip=fitz.Rect(225, 0, 362, page.rect.height))
                              if scanned else words)
            dates=sorted(
                [(w[4],_center(w)) for w in words
                 if w[0]<65 and DATE.fullmatch(w[4])],
                key=lambda item:item[1])
            for i,(date_text,y) in enumerate(dates):
                day=datetime.strptime(date_text,"%d/%m/%Y").date()
                row=[w for w in words if abs(_center(w)-y)<3.7]
                label=" ".join(w[4] for w in sorted(row,key=lambda w:w[0])
                               if 85<=w[0]<225).strip(" —=|§")
                values=[w[4] for w in row if 455<=w[0]<515 and MONEY.fullmatch(w[4])]
                balances=[w[4] for w in row if w[0]>=515 and MONEY.fullmatch(w[4])]
                if not label and not values and not balances:
                    continue
                if "SALDOANTERIOR" in label.replace(" ", ""):
                    if opening is not None or len(balances)!=1 or transactions:
                        raise ValueError("Saldo inicial Itaú inválido ou repetido.")
                    opening=cents(balances[0])
                    continue
                if include_blocked_balance and label == "SALDO BLOQUEADO":
                    continue
                if label.startswith("SALDO TOTAL DISPON") or (include_blocked_balance and label == "SALDO TOTAL"):
                    if len(balances)!=1 or not transactions:
                        raise ValueError("Saldo diário Itaú não reconhecido.")
                    if not (include_blocked_balance and checks and
                            checks[-1][0] == day and checks[-1][2] == len(transactions)):
                        checks.append((day,cents(balances[0]),len(transactions)))
                    continue
                if not start<=day<=end:
                    continue
                if len(values)!=1:
                    raise ValueError(f"Lançamento Itaú sem valor válido em {date_text}.")
                if not label:
                    # RENDIMENTOS, RECEBIMENTO REDE VISA e COMPRA NO
                    # DÉBITO têm o nome dividido acima e abaixo da data.
                    # Linhas adjacentes ficam a ~5,3 pt; novos movimentos
                    # têm espaçamento maior. Nunca buscar em outra página.
                    nearby = [w for w in words
                              if 85 <= w[0] < 225
                              and 3.5 < abs(_center(w)-y) <= 7.5]
                    before = sorted((w for w in nearby if _center(w)<y),
                                    key=lambda w: w[0])
                    after = sorted((w for w in nearby if _center(w)>y),
                                   key=lambda w: w[0])
                    label = " ".join(w[4] for w in before+after).strip()
                if not label:
                    raise ValueError(f"Histórico Itaú não encontrado em {date_text}.")
                low=(dates[i-1][1]+y)/2 if i else y-12
                high=(dates[i+1][1]+y)/2 if i+1<len(dates) else y+12
                merchant=[w for w in merchant_words if 225<=w[0]<362 and low<=_center(w)<high]
                merchant=sorted(merchant,key=lambda w:(round(_center(w)/5),w[0]))
                merchant_name=" ".join(w[4] for w in merchant)
                merchant_name=PRIVATE.sub("",merchant_name).strip()
                merchant_name=" ".join(merchant_name.split())
                history=join_history_description(label.replace("PIXENVIADO", "PIX ENVIADO"), merchant_name)
                amount=cents(values[0])
                if not amount:raise ValueError("Lançamento Itaú com valor zero.")
                if amount < 0 and merchant_name.casefold() in salary_names:
                    history = f"Salários - {merchant_name}"
                transactions.append((day,amount,history))
        if not transactions or opening is None or not checks:
            raise ValueError("Extrato Itaú sem saldos ou movimentos reconhecidos.")
        running=opening
        last=0
        for day,balance,count in checks:
            running+=sum(value for _,value,_ in transactions[last:count])
            if running!=balance:
                raise ValueError(f"Saldo do Itaú diverge no dia {day:%d/%m/%Y}.")
            last=count
        if last!=len(transactions):
            raise ValueError("Movimentações do Itaú sem saldo bancário de fechamento.")
        return pd.DataFrame([{
            "DESCRIÇÃO":"BANCO ITAÚ",
            "DATA":pd.Timestamp(day),
            "VALOR":value/100,
            "DÉBITO":accounting_account if value>0 else "",
            "CRÉDITO":accounting_account if value<0 else "",
            "HISTÓRICO":("Recebido: " if value>0 else "Pago: ")+history
        } for day,value,history in transactions],columns=COLUNAS)

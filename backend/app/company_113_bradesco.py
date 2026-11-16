"""Leitor Bradesco Leravi 113 usando pdfplumber e conciliação completa em centavos."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re

import pandas as pd
import pdfplumber

_DATE=re.compile(r"^\d{2}/\d{2}/20\d{2}$")
_MONEY=re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}$")
_COLS=["DESCRIÇÃO","DATA","VALOR","DÉBITO","CRÉDITO","HISTÓRICO"]

def _centavos(value):
    return int(Decimal(value.replace(".","").replace(",","."))*100)

def _mid(word):
    return (word[1]+word[3])/2

def read_statement(content, verify_account):
    if not isinstance(content,bytes) or not content.startswith(b"%PDF") or len(content)>35*1024*1024:
        raise ValueError("Leravi Bradesco: envie PDF válido de até 35 MB.")
    with pdfplumber.open(BytesIO(content)) as document:
        if not 1 <= len(document.pages) <= 40:
            raise ValueError("Leravi Bradesco: quantidade de páginas inválida.")
        if not verify_account(document.pages[0].extract_text() or ""):
            raise ValueError("Leravi Bradesco: agência/conta não correspondem ao PDF.")
        records=[]
        opening=running=totals=current_day=None
        last_page=0
        for page_number,page in enumerate(document.pages,start=1):
            words=[(w["x0"],w["top"],w["x1"],w["bottom"],w["text"])
                   for w in page.extract_words(x_tolerance=1.5,y_tolerance=2)]
            amount_words=sorted(
                (w for w in words if 335<=w[0]<520 and _MONEY.fullmatch(w[4])),
                key=_mid)
            balance_words=sorted(
                (w for w in words if w[0]>=525 and _MONEY.fullmatch(w[4])),
                key=_mid)
            date_words=sorted(
                (w for w in words if w[0]<86 and _DATE.fullmatch(w[4])),
                key=_mid)
            for balance in balance_words:
                y=_mid(balance)
                near=sorted(
                    (w for w in words if 39<=w[0]<260 and abs(_mid(w)-y)<=7.2),
                    key=lambda w:(round(_mid(w)/3),w[0]))
                history=" ".join(w[4] for w in near if w[0]>=99)
                dates=[w for w in date_words if abs(_mid(w)-y)<=6.4]
                if len(dates)>1:
                    raise ValueError(f"Leravi Bradesco: data ambígua na página {page_number}.")
                if dates:
                    current_day=datetime.strptime(dates[0][4],"%d/%m/%Y").date()
                values=[w for w in amount_words if abs(_mid(w)-y)<=2.8]
                if len(values)==2 and any(w[4].casefold()=="total" for w in near):
                    totals=(_centavos(values[0][4]),_centavos(values[1][4]),
                            _centavos(balance[4]))
                    last_page=page_number
                    break
                if not values:
                    if "SALDO ANTERIOR" in history.upper():
                        if opening is not None or records:
                            raise ValueError("Leravi Bradesco: saldo anterior repetido.")
                        opening=running=_centavos(balance[4])
                    continue
                if len(values)!=1:
                    raise ValueError(f"Leravi Bradesco: valor ambíguo na página {page_number}.")
                if running is None or current_day is None:
                    raise ValueError(f"Leravi Bradesco: saldo inicial ou data ausente na página {page_number}.")
                value=_centavos(values[0][4])
                if not value or not history:
                    raise ValueError(f"Leravi Bradesco: valor/histórico incompleto na página {page_number}.")
                running+=value
                if running!=_centavos(balance[4]):
                    raise ValueError(
                        f"Leravi Bradesco: saldo divergente em {current_day:%d/%m/%Y}."
                    )
                records.append((current_day,value,history))
            if totals is not None:
                break
        if opening is None or not records or totals is None:
            missing=", ".join(
                label for label,exists in
                (("saldo inicial",opening is not None),("movimentos",bool(records)),
                 ("totalizador",totals is not None)) if not exists
            )
            raise ValueError(f"Leravi Bradesco: {missing} não localizado no PDF.")
        credits=sum(max(value,0) for _,value,_ in records)
        debits=sum(min(value,0) for _,value,_ in records)
        if (credits,debits,running)!=totals:
            raise ValueError("Leravi Bradesco: totais ou saldo final não conferem com o PDF.")
        august=[r for r in records if r[0].year==2026 and r[0].month==8]
        if not august:
            raise ValueError("Leravi Bradesco: extrato sem lançamentos de agosto/2026.")
        from app.company_113 import frame
        return frame([dict(date=day,value=value,history=history)
                      for day,value,history in august],"BANCO BRADESCO","9")

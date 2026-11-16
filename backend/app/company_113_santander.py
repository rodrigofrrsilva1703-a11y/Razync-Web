"""Leravi 113: Santander Empresas PDF digitalizado, validado em centavos."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from decimal import Decimal
import calendar
import re
import unicodedata
import fitz
import numpy as np
import pandas as pd
import cv2
from PIL import Image
import pytesseract

_MONTHS={"JANEIRO":1,"FEVEREIRO":2,"MARCO":3,"ABRIL":4,"MAIO":5,"JUNHO":6,
         "JULHO":7,"AGOSTO":8,"SETEMBRO":9,"OUTUBRO":10,"NOVEMBRO":11,"DEZEMBRO":12}
_MONEY=re.compile(r"\d[\d.,]*[,\.]\d{2}[-:.,]?")
_PRIVATE=re.compile(r"\b(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11,14})\b")

def _norm(text):
    text=unicodedata.normalize("NFKD",str(text or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper()

def _cents(text):
    raw=str(text).strip("-:., ")
    if raw.count(",")>1:raw=raw.replace(",",".",raw.count(",")-1)
    if not re.fullmatch(r"\d+(?:\.\d{3})*,\d{2}",raw):
        raise ValueError("Santander 113: valor monetário ilegível no OCR.")
    return int(Decimal(raw.replace(".","").replace(",","."))*100)

def _ocr(page,mode):
    dpi=300
    pix=page.get_pixmap(dpi=dpi,colorspace=fitz.csGRAY,alpha=False)
    im=Image.frombytes("L",(pix.width,pix.height),pix.samples)
    processed=cv2.adaptiveThreshold(np.asarray(im,dtype=np.uint8),255,
                                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,35,13)
    try:
        data=pytesseract.image_to_data(processed,lang="eng",config=f"--psm {mode}",
                                       output_type=pytesseract.Output.DICT,timeout=60)
    except Exception as exc:
        raise ValueError("Santander 113: OCR indisponível para o PDF digitalizado.") from exc
    scale=72/dpi
    return [dict(text=str(data["text"][i]).strip(),x=data["left"][i]*scale,
                 y=(data["top"][i]+data["height"][i]/2)*scale,
                 confidence=float(data["conf"][i]))
            for i in range(len(data["text"])) if str(data["text"][i]).strip()]

def _text(words):
    lines=defaultdict(list)
    for w in words:lines[round(w["y"]/3)*3].append(w)
    return "\n".join(" ".join(w["text"] for w in sorted(line,key=lambda a:a["x"]))
                     for _,line in sorted(lines.items()))

def _period_and_totals(words):
    text=_norm(_text(words))
    if "LERAVI INDUSTRIAL" not in text:
        raise ValueError("Santander 113: titular Leravi não encontrado no resumo.")
    compact=re.sub(r"[^0-9A-Z]","",text)
    if "1565" not in compact or "130000182" not in compact:
        raise ValueError("Santander 113: agência 1565 ou conta 13.000018-2 divergente.")
    match=re.search(r"RESUMO\s*-?\s*("+"|".join(_MONTHS)+r")\s*/\s*(20\d{2})",text)
    if not match:
        raise ValueError("Santander 113: competência não identificada no resumo.")
    month,year=_MONTHS[match[1]],int(match[2])
    if not 2024<=year<=2100:raise ValueError("Santander 113: competência inválida.")
    totals=[]
    for title in (r"TOTAL DE CR.DITOS",r"TOTAL DE D.BITOS"):
        match=re.search(title+r"\s+(\d{1,3}(?:[.,]\d{3})+)\s*(?:\([+-]?\))?\s*(\d{2})",text)
        if not match:
            raise ValueError("Santander 113: totais mensais ilegíveis.")
        totals.append(_cents(match[1]+","+match[2]))
    return year,month,*totals

def _parse_transactions(pages,year,month):
    records=[];current_day=None;balances=[]
    max_day=calendar.monthrange(year,month)[1]
    for page_num,(words6,words11) in enumerate(pages,start=2):
        dates=[]
        for word in words6+words11:
            if word["x"]>58:continue
            raw=word["text"]
            # Datas tipo 29109 são artefato do OCR em layouts digitalizados.
            if re.fullmatch(r"\d{2}1\d{2}",raw):raw=raw[:2]+"/"+raw[3:]
            match=re.fullmatch(r"(\d{2})/(\d{2})",raw)
            if not match:continue
            day,mm=map(int,match.groups())
            if mm==month and 1<=day<=max_day:dates.append((word["y"],day))
        dates.sort()
        candidates=[]
        for mode,words in ((6,words6),(11,words11)):
            for w in words:
                if not 365<=w["x"]<475 or not _MONEY.fullmatch(w["text"]):continue
                if page_num==2 and w["y"]<670:continue
                try:value=_cents(w["text"])
                except ValueError:continue
                if not value:continue
                value=value if w["x"]<415 else -value
                candidates.append((w["y"],w["x"],w["confidence"],value))
        selected=[]
        for cand in sorted(candidates,key=lambda r:-r[2]):
            if any(abs(cand[0]-r[0])<4.5 and abs(cand[1]-r[1])<14 for r in selected):continue
            selected.append(cand)
        selected.sort()
        for index,(cy,x,conf,value) in enumerate(selected):
            earlier=[d for d in dates if d[0]<=cy+6]
            if earlier:current_day=earlier[-1][1]
            if current_day is None:raise ValueError("Santander 113: lançamento sem data válida.")
            def title_for(words):
                row=sorted((w for w in words if abs(w["y"]-cy)<3.6
                            and 63<=w["x"]<313),key=lambda w:w["x"])
                return " ".join(w["text"] for w in row)
            history=max((title_for(words6),title_for(words11)),key=len)
            next_y=selected[index+1][0] if index+1<len(selected) else cy+17
            details=[]
            for words in (words6,words11):
                adjacent=[w for w in words if cy+4.5<=w["y"]<min(next_y-3,cy+14)
                          and 64<=w["x"]<310]
                groups=defaultdict(list)
                for w in adjacent:groups[round(w["y"]/3)*3].append(w)
                label=" ".join(" ".join(w["text"] for w in sorted(g,key=lambda a:a["x"]))
                               for _,g in sorted(groups.items()))
                if label and not re.search(r"(?i)PERIODO:|PAGSAL:|PAGINA:|EXTRATO|DATA DESCRICAO",label):
                    details.append(label)
            if details:history+=" "+max(details,key=len)
            history=re.sub(r"\s+"," ",_PRIVATE.sub("",history)).strip(" -|~_=:")
            if not history:raise ValueError("Santander 113: histórico ilegível.")
            records.append((date(year,month,current_day),value,history))
            nearby=[w for words in (words6,words11) for w in words
                    if w["x"]>=508 and abs(w["y"]-cy)<4.5 and _MONEY.fullmatch(w["text"])]
            if nearby:
                highest=max(nearby,key=lambda w:w["confidence"])
                check=_cents(highest["text"])
                balances.append((len(records),check))
    if not records:raise ValueError("Santander 113: nenhum movimento reconhecido.")
    running=0;previous=0
    for count,expected in balances:
        running+=sum(value for _,value,_ in records[previous:count])
        # O OCR pode suprimir o traço final de um saldo negativo.
        # Confere a magnitude sem alterar nenhum lançamento bancário.
        if abs(running)!=expected:
            day=records[count-1][0]
            raise ValueError(f"Santander 113: saldo diverge em {day:%d/%m/%Y}.")
        previous=count
    if not balances or balances[-1][0]!=len(records):
        raise ValueError("Santander 113: saldo final não reconhecido.")
    return records

def read_statement(content):
    if not isinstance(content,bytes) or not content.startswith(b"%PDF") or len(content)>35*1024*1024:
        raise ValueError("Santander 113: envie o extrato original PDF de até 35 MB.")
    with fitz.open(stream=content,filetype="pdf") as doc:
        if not 5<=len(doc)<=30:raise ValueError("Santander 113: PDF consolidado incompleto.")
        summary=_ocr(doc[1],6)
        year,month,credit_expected,debit_expected=_period_and_totals(summary)
        pages=[(summary,_ocr(doc[1],11))]
        for page in doc[2:4]:pages.append((_ocr(page,6),_ocr(page,11)))
        rows=_parse_transactions(pages,year,month)
    credit=sum(max(value,0) for _,value,_ in rows)
    debit=-sum(min(value,0) for _,value,_ in rows)
    if credit!=credit_expected or debit!=debit_expected:
        raise ValueError("Santander 113: OCR incompleto: créditos/débitos não conferem com resumo.")
    return pd.DataFrame([{
        "DESCRIÇÃO":"BANCO SANTANDER","DATA":pd.Timestamp(day),
        "VALOR":value/100,"DÉBITO":"513" if value>0 else "",
        "CRÉDITO":"513" if value<0 else "",
        "HISTÓRICO":("Recebido: " if value>0 else "Pago: ")+history,
    } for day,value,history in rows],columns=[
        "DESCRIÇÃO","DATA","VALOR","DÉBITO","CRÉDITO","HISTÓRICO"])

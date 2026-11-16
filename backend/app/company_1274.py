"""Empresa 1274 — Auguri: BB 8, Itaú 508 e Santander 513.

Os PDFs Itaú e Santander incluem julho e setembro; somente a competência
08/2026 é convertida no fluxo padrão. Cada PDF é conferido antes do recorte.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from collections import defaultdict
import re
import fitz
import pandas as pd

COLS = ["DESCRIÇÃO","DATA","VALOR","DÉBITO","CRÉDITO","HISTÓRICO"]
DATE = re.compile(r"\d{2}/\d{2}/20\d{2}$")
MONEY = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}$")
PRIVATE = re.compile(r"(?:\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11,14}\b)")

def cents(value):
    raw=str(value).strip()
    return int(Decimal(raw.replace(".","").replace(",","."))*100)

def clean(value):
    return " ".join(PRIVATE.sub("",str(value)).split())

def frame(rows, bank, account):
    if not rows:
        raise ValueError(f"Empresa 1274: nenhum lançamento identificado no {bank}.")
    return pd.DataFrame([{
        "DESCRIÇÃO":bank, "DATA":pd.Timestamp(day), "VALOR":value/100,
        "DÉBITO":account if value>0 else "", "CRÉDITO":account if value<0 else "",
        "HISTÓRICO":("Recebido: " if value>0 else "Pago: ")+clean(history)
    } for day,value,history in rows],columns=COLS)

def _pdf(content,bank):
    if not content.startswith(b"%PDF") or len(content)>35*1024*1024:
        raise ValueError(f"Empresa 1274: envie um PDF {bank} válido de até 35 MB.")
    doc=fitz.open(stream=content,filetype="pdf")
    if not 1<=len(doc)<=40:
        doc.close()
        raise ValueError("PDF bancário com quantidade de páginas inválida.")
    return doc

def read_santander(content):
    from app.santander_aplicativo import processar_extrato_santander_aplicativo_pdf
    with _pdf(content,"Santander") as doc:
        first=doc[0].get_text()
    if not (re.search(r"AUGURI SOLUCOES EM SAUDE",first,re.I)
            and re.search(r"Agência:\s*4354",first,re.I)
            and re.search(r"Conta:\s*130026022",first,re.I)):
        raise ValueError("Santander 1274: titular, agência ou conta divergente.")
    records=processar_extrato_santander_aplicativo_pdf(content)
    rows=[]
    for rec in records:
        day=datetime.strptime(rec["DATA"],"%d/%m/%Y").date()
        amount=round(rec["VALOR"]*100)
        if amount and day.year==2026 and day.month==8:
            rows.append((day,amount,rec["HISTÓRICO"]))
    rows.sort(key=lambda r:r[0])
    return frame(rows,"BANCO SANTANDER","513")

def read_banco_brasil(content):
    with _pdf(content,"Banco do Brasil") as doc:
        if not all(re.search(pattern,doc[0].get_text(),re.I) for pattern in
                   (r"Cliente AUGURI S SAUDE LTDA",r"Agência:\s*3131-3\s+Conta:\s*24073-7")):
            raise ValueError("BB 1274: agência, conta ou titular divergente.")
        lines=[]
        for number, page in enumerate(doc, start=1):
            page_lines=[s.strip() for s in page.get_text().splitlines() if s.strip()]
            # O cabeçalho reaparece em todas as páginas. Se mantido, pode
            # ser anexado ao último Pix da página anterior e fazê-lo sumir
            # da conferência diária (ex.: R$ 100.000,00 em 06/08/2026).
            marker=next((i for i, text in enumerate(page_lines)
                         if text=="Lançamentos"), None)
            if marker is None or page_lines[marker+1:marker+6]!=[
                "Dia","Lote","Documento","Histórico","Valor"
            ]:
                raise ValueError(
                    f"BB 1274: cabeçalho do extrato inválido na página {number}."
                )
            lines.extend(page_lines[marker+6:])
    amount_re=re.compile(r"^([\d.]+,\d{2})\s*\(([+-])\)$")
    date_re=re.compile(r"^\d{2}/\d{2}/20\d{2}$")
    rows=[];opening=None;running=None;closing=False;checkpoints=0
    i=0
    while i<len(lines):
        match=amount_re.fullmatch(lines[i])
        if not match or i+1>=len(lines) or not (date_re.fullmatch(lines[i+1]) or lines[i+1]=="00/00/0000"):
            i+=1;continue
        amount=abs(cents(match[1]))*(1 if match[2]=="+" else -1)
        date_str=lines[i+1]
        j=i+2
        parts=[]
        while j<len(lines):
            if amount_re.fullmatch(lines[j]) and j+1<len(lines) and (date_re.fullmatch(lines[j+1]) or lines[j+1]=="00/00/0000"):
                break
            parts.append(lines[j]);j+=1
            if j-i>14:break
        desc=" ".join(parts)
        if "Saldo Anterior" in desc:
            if opening is not None:raise ValueError("BB 1274: saldo anterior repetido.")
            opening=running=amount
        elif "Saldo do dia" in desc:
            if running is None or running!=amount:
                raise ValueError("BB 1274: saldo diário divergente.")
            checkpoints+=1
        elif "S A L D O" in desc:
            if running!=amount:raise ValueError("BB 1274: saldo final divergente.")
            closing=True
            break
        elif date_re.fullmatch(date_str):
            if running is None:raise ValueError("BB 1274: movimentos sem saldo inicial.")
            day=datetime.strptime(date_str,"%d/%m/%Y").date()
            hist_index=next((k for k,v in enumerate(parts) if re.search(
                r"Pix - |Tarifa |Pagamento |BB Rende Fácil|TED-|Pagto cartão|Cobrança",v,re.I)),None)
            if hist_index is None:raise ValueError(f"BB 1274: histórico não identificado em {date_str}.")
            history=" ".join(parts[hist_index:]).strip()
            if not amount:raise ValueError("BB 1274: valor zerado.")
            running+=amount
            if day.year==2026 and day.month==8:
                rows.append((day,amount,history))
        i=j
    if opening is None or not closing or not checkpoints:
        raise ValueError("BB 1274: extrato incompleto, sem saldos conciliados.")
    return frame(rows,"BANCO DO BRASIL","8")

def _center(w):
    return (w[1]+w[3])/2

def read_itau(content):
    with _pdf(content,"Itaú") as doc:
        first=doc[0].get_text()
        if not (re.search(r"AUGURI SOLUCOES EM SAUDE",first,re.I)
                and "10.301.312/0001-99" in first
                and re.search(r"1514\s+Conta\s+0096367-5",first,re.I)):
            raise ValueError("Itaú 1274: titular, agência ou conta divergente.")
        records=[];daily={};opening=None;current=None
        for page in doc:
            words=page.get_text("words",sort=True)
            dates=sorted([w for w in words if 25<=w[0]<85 and DATE.fullmatch(w[4])],key=_center)
            for n,w in enumerate(dates):
                day=datetime.strptime(w[4],"%d/%m/%Y").date()
                y=_center(w)
                same=[x for x in words if abs(_center(x)-y)<3.4]
                label=" ".join(x[4] for x in sorted(same,key=lambda x:x[0]) if 87<=x[0]<230).strip()
                values=[x[4] for x in same if 460<=x[0]<515 and MONEY.fullmatch(x[4])]
                balances=[x[4] for x in same if x[0]>=515 and MONEY.fullmatch(x[4])]
                low=(y+_center(dates[n-1]))/2 if n else y-9
                high=(y+_center(dates[n+1]))/2 if n+1<len(dates) else y+12
                if "SALDO ANTERIOR" in label.upper():
                    if len(balances)!=1 or opening is not None:raise ValueError("Itaú 1274: saldo anterior inválido.")
                    opening=cents(balances[0]);continue
                if label.upper().startswith("SALDO"):
                    if "SALDO TOTAL DISPON" in label.upper() and len(balances)==1:
                        daily[day]=cents(balances[0])
                    continue
                if not values:
                    continue
                if len(values)!=1:raise ValueError(f"Itaú 1274: valor ambíguo em {day}.")
                amount=cents(values[0])
                if not amount:continue
                extra=sorted((x for x in words if 230<=x[0]<360 and low<=_center(x)<high),key=lambda x:(_center(x),x[0]))
                merchant=" ".join(x[4] for x in extra)
                history=" ".join(x for x in (label,clean(merchant)) if x)
                if not history:raise ValueError("Itaú 1274: lançamento sem histórico.")
                records.append((day,amount,history))
        if not records or not daily or opening is None:
            raise ValueError("Itaú 1274: extrato sem movimentos ou saldos.")
        # O PDF é decrescente e inclui julho, agosto e setembro; os saldos
        # diários estão antes dos movimentos daquele dia na ordem impressa.
        by_day=defaultdict(list)
        for row in records:by_day[row[0]].append(row[1])
        running=opening
        for day in sorted(by_day):
            running+=sum(by_day[day])
            if day in daily and running!=daily[day]:
                raise ValueError(f"Itaú 1274: saldo diverge em {day:%d/%m/%Y}.")
        if not any(day.month==8 and day.year==2026 for day in by_day):
            raise ValueError("Itaú 1274: nenhum movimento de agosto/2026.")
        return frame([r for r in reversed(records) if r[0].year==2026 and r[0].month==8],
                     "BANCO ITAÚ","508")

READERS={"banco_brasil":read_banco_brasil,"itau":read_itau,"santander":read_santander}

def workflow_1274(roles,options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    sheets={}
    for key,label in (("banco_brasil","Banco do Brasil"),("itau","Itaú"),("santander","Santander")):
        uploads=roles.get(key) or []
        if not uploads:continue
        if len(uploads)!=1:raise ValueError(f"Auguri: envie apenas um extrato mensal {label}.")
        filename,content=uploads[0]
        if not filename.lower().endswith(".pdf"):raise ValueError(f"Auguri: extrato {label} deve ser PDF.")
        df=filter_frame(READERS[key](content),options)
        if not df.empty:sheets[label]=df.sort_values("DATA",kind="stable")
    if not sheets:raise ValueError("Empresa 1274: envie pelo menos um extrato de agosto/2026.")
    return gerar_modelo_abas(sheets,date_format="dd/mm/yyyy"),"AUGURI_1274_MODELO_DOMINIO.xlsx"

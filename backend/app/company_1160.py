"""Empresa 1160 (Gung Wen) — quatro leitores PDF com saldos validados.

A conta contábil vem do cadastro: Banco do Brasil 8, Sicoob 506,
Itaú 508, Bradesco 515. O lançamento de estorno não é removido junto
com seu débito; ambos são movimentos bancários reais.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import re
import unicodedata

import fitz
import pandas as pd

from app.history_names import join_history_description

COLUMNS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
MONEY = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}-?$")
PRIVATE = re.compile(
    r"(?:\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|"
    r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11,14}\b|"
    r"\b\d{2}\.\d{3}\.\d{3}\s+\d{4}-\d{2}\b)")
FULL_DATE = re.compile(r"^\d{2}/\d{2}/20\d{2}$")
SHORT_DATE = re.compile(r"^\d{2}/\d{2}$")


def _normalize(value):
    text=unicodedata.normalize("NFKD",str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def _cents(value):
    text=str(value).strip()
    negative=text.startswith("-") or text.endswith("-")
    text=text.strip("-").replace(".","").replace(",",".")
    amount=Decimal(text)*100
    if not amount.is_finite() or amount!=amount.to_integral_value():
        raise ValueError("Valor bancário inválido.")
    return int(amount)*(-1 if negative else 1)


def _open(content, bank):
    if not content.startswith(b"%PDF") or len(content)>35*1024*1024:
        raise ValueError(f"Empresa 1160: extrato {bank} deve ser PDF válido até 35 MB.")
    try:
        doc=fitz.open(stream=content,filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Não foi possível abrir o PDF {bank}.") from exc
    if not 1<=len(doc)<=30:
        doc.close()
        raise ValueError("Número de páginas de extrato inválido.")
    return doc


def _center(word):
    return (word[1]+word[3])/2


def _lines(page, tolerance=3.0):
    groups=[]
    words=sorted(page.get_text("words",sort=True),key=lambda w:(_center(w),w[0]))
    for w in words:
        y=_center(w)
        if groups and abs(groups[-1][0]-y)<tolerance:
            groups[-1][1].append(w)
        else:
            groups.append([y,[w]])
    return [(y,sorted(ws,key=lambda w:w[0])) for y,ws in groups]


def _text(words,left=0,right=999):
    return " ".join(w[4] for w in words if left<=w[0]<right).strip()


def _frame(rows,bank,account):
    if not rows:raise ValueError(f"Extrato {bank} sem lançamentos.")
    return pd.DataFrame([{
        "DESCRIÇÃO":bank,"DATA":pd.Timestamp(day),"VALOR":value/100,
        "DÉBITO":account if value>0 else "",
        "CRÉDITO":account if value<0 else "",
        "HISTÓRICO":("Recebido: " if value>0 else "Pago: ")+
                     " ".join(PRIVATE.sub("",history).split()),
    } for day,value,history in rows],columns=COLUMNS)


def read_banco_brasil(content):
    doc=_open(content,"Banco do Brasil")
    with doc:
        first=doc[0].get_text()
        if not (re.search(r"Agência\s*8224-4",first,re.I) and
                re.search(r"Conta corrente\s*379-4",first,re.I) and
                "GUNG" in first.upper()):
            raise ValueError("BB 1160: titular, agência 8224-4 ou conta 379-4 divergente.")
        month_match=re.search(r"Período do extrato\s*(\d{2})\s*/\s*(20\d{2})",first,re.I)
        if not month_match:
            raise ValueError("BB 1160: competência não encontrada.")
        month,year=map(int,month_match.groups())
        rows=[];checks=[];opening=None;last_row=None
        for page in doc:
            words=page.get_text("words",sort=True)
            for w in words:
                if not (60<=w[0]<115 and FULL_DATE.fullmatch(w[4])):
                    continue
                y=_center(w)
                day=datetime.strptime(w[4],"%d/%m/%Y").date()
                row=[x for x in words if abs(_center(x)-y)<3.6]
                description=_text(row,264,372)
                amount=[x for x in row if 451<=x[0]<500 and MONEY.fullmatch(x[4])]
                debit_credit=[x[4].upper() for x in row if 488<=x[0]<502 and x[4].upper() in ("D","C")]
                balance=[x[4] for x in row if 501<=x[0]<544 and MONEY.fullmatch(x[4])]
                balance_sign=[x[4].upper() for x in row if x[0]>=538 and x[4].upper() in ("D","C")]
                if "saldo anterior" in _normalize(description):
                    if opening is not None or len(balance)!=1:
                        raise ValueError("BB 1160: saldo anterior inválido.")
                    opening=_cents(balance[0])*(-1 if balance_sign==["D"] else 1)
                    continue
                if _normalize(description).strip().replace(" ","") in ("saldo","saldoatual"):
                    continue
                if day.month!=month or day.year!=year:
                    continue
                if len(amount)!=1 or len(debit_credit)!=1 or not description:
                    raise ValueError(f"BB 1160: lançamento incompleto em {w[4]}.")
                value=abs(_cents(amount[0][4]))*(-1 if debit_credit[0]=="D" else 1)
                if value==0:raise ValueError("BB 1160: valor zerado.")
                rows.append((day,value,description))
                if balance and balance_sign:
                    checks.append((len(rows),_cents(balance[0])*(-1 if balance_sign[0]=="D" else 1),day))
        if opening is None or not rows or not checks:
            raise ValueError("BB 1160: extrato sem abertura, saldos ou movimentos.")
        running=opening;last=0
        for count,balance,day in checks:
            running+=sum(v for _,v,_ in rows[last:count])
            if running!=balance:
                raise ValueError(f"BB 1160: saldo não fecha em {day:%d/%m/%Y}.")
            last=count
        if last!=len(rows):
            raise ValueError("BB 1160: final do extrato sem saldo bancário.")
        return _frame(rows,"BANCO DO BRASIL","8")


def read_sicoob(content):
    doc=_open(content,"Sicoob")
    with doc:
        header=doc[0].get_text()
        if not (re.search(r"4340-0\s*/\s*SICOOB",header,re.I) and
                re.search(r"210\.034-7\s*/\s*GUNG",header,re.I)):
            raise ValueError("Sicoob 1160: cooperativa 4340 ou conta 210.034-7 divergente.")
        match=re.search(r"Periodo:\s*(\d{2}/\d{2}/20\d{2})\s*-\s*(\d{2}/\d{2}/20\d{2})",header,re.I)
        if not match:raise ValueError("Sicoob 1160: período não encontrado.")
        start,end=(datetime.strptime(t,"%d/%m/%Y").date() for t in match.groups())
        if (start.year,start.month)!=(end.year,end.month):
            raise ValueError("Sicoob 1160: extrato com mais de uma competência.")
        movements=[];daily={};opening=None
        last_index=None
        for page in doc:
            words=page.get_text("words",sort=True)
            for y,row in _lines(page,3):
                dates=[w[4] for w in row if 30<=w[0]<64 and SHORT_DATE.fullmatch(w[4])]
                if not dates:
                    if last_index is not None:
                        extra=_text(row,133,480)
                        if extra.startswith("Recebimento Pix") and abs(y-last_index[0])<18:
                            i=last_index[1]
                            day,val,old=movements[i]
                            detail=PRIVATE.sub("",extra)
                            movements[i]=(day,val,join_history_description(old,detail))
                    continue
                day=datetime.strptime(f"{dates[0]}/{start.year}","%d/%m/%Y").date()
                if not start<=day<=end:
                    if dates[0]=="30/06":
                        # Opening is validated from the final summary below.
                        pass
                    else:
                        continue
                history=_text(row,133,480)
                amounts=[w[4] for w in row if w[0]>480 and
                         re.fullmatch(r"[\d.]+,\d{2}[CD]",w[4],re.I)]
                if len(amounts)!=1:
                    continue
                token=amounts[0]
                value=_cents(token[:-1])*(1 if token[-1].upper()=="C" else -1)
                lower=_normalize(history)
                if lower.startswith("saldo anterior"):
                    opening=value
                    continue
                if lower.startswith(("saldo do dia","saldo bloqueado anterior")):
                    if lower.startswith("saldo do dia"):
                        if day in daily:raise ValueError("Sicoob 1160: saldo diário repetido.")
                        daily[day]=value
                    continue
                if not start<=day<=end:
                    continue
                if not history:
                    raise ValueError(f"Sicoob 1160: histórico ausente em {day}.")
                movements.append((day,value,history))
                last_index=(y,len(movements)-1)
        if opening is None or not daily or not movements:
            raise ValueError("Sicoob 1160: saldo inicial, diário ou movimentos ausentes.")
        # Relatório é decrescente. Reverter todas as linhas mantendo estornos.
        movements.reverse()
        running=opening
        by_day=defaultdict(list)
        for day,val,history in movements:by_day[day].append(val)
        for day in sorted(by_day):
            running+=sum(by_day[day])
            if day not in daily or running!=daily[day]:
                raise ValueError(f"Sicoob 1160: saldo não confere em {day:%d/%m/%Y}.")
        if len(by_day)!=len(daily):
            raise ValueError("Sicoob 1160: há dias sem lançamentos reconhecidos.")
        return _frame(movements,"BANCO SICOOB","506")


def read_itau(content):
    doc=_open(content,"Itaú")
    with doc:
        first=doc[0].get_text()
        if not (re.search(r"Agência\s+7111\s+Conta\s+0099819-6",first,re.I)
                and re.search(r"GUNG\s+WEN\s+COM",first,re.I)
                and "39.792.168/0001-12" in first):
            raise ValueError("Itaú 1160: empresa, agência 7111 ou conta 0099819-6 divergente.")
        period=re.search(r"Lançamentos do período:\s*(\d{2}/\d{2}/20\d{2})\s+até\s+(\d{2}/\d{2}/20\d{2})",first)
        if not period:raise ValueError("Itaú 1160: período não reconhecido.")
        start,end=(datetime.strptime(v,"%d/%m/%Y").date() for v in period.groups())
        if (start.year,start.month)!=(end.year,end.month):
            raise ValueError("Itaú 1160: período deve conter uma competência.")
        records=[];checks=[];opening=None
        for page in doc:
            words=page.get_text("words",sort=True)
            anchors=sorted([(w,_center(w)) for w in words
                if w[0]<85 and FULL_DATE.fullmatch(w[4])],
                key=lambda entry:entry[1])
            for i,(w,y) in enumerate(anchors):
                day=datetime.strptime(w[4],"%d/%m/%Y").date()
                row=[x for x in words if abs(_center(x)-y)<3.5]
                basic=_text(row,89,225)
                values=[x[4] for x in row if 466<=x[0]<515 and MONEY.fullmatch(x[4])]
                balances=[x[4] for x in row if x[0]>=515 and MONEY.fullmatch(x[4])]
                upper=_normalize(basic)
                if "saldo anterior" in upper:
                    if opening is not None or len(balances)!=1:
                        raise ValueError("Itaú 1160: saldo anterior não identificado.")
                    opening=_cents(balances[0])
                    continue
                if upper.startswith("saldo"):
                    if balances and ("total" in upper or "disponivel dia" in upper):
                        checks.append((day,len(records),_cents(balances[-1]),"total" if upper=="saldo total" else "available"))
                    continue
                if not start<=day<=end:
                    continue
                if len(values)!=1:
                    raise ValueError(f"Itaú 1160: lançamento incompleto em {day:%d/%m/%Y}.")
                low=(anchors[i-1][1]+y)/2 if i else y-14
                high=(anchors[i+1][1]+y)/2 if i+1<len(anchors) else y+14
                label_words=[x for x in words if 89<=x[0]<225 and low<=_center(x)<high]
                text=" ".join(x[4] for x in sorted(label_words,key=lambda x:(_center(x),x[0])))
                if not text:raise ValueError(f"Itaú 1160: histórico vazio em {day}.")
                names=[x for x in words if 225<=x[0]<360 and low<=_center(x)<high]
                name=" ".join(x[4] for x in sorted(names,key=lambda x:(_center(x),x[0])))
                history=join_history_description(text,name)
                amount=_cents(values[0])
                if not amount:raise ValueError("Itaú 1160: movimento de valor zero.")
                records.append((day,amount,history))
        if opening is None or not records or not checks:
            raise ValueError("Itaú 1160: saldo inicial, lançamentos ou saldos diários ausentes.")
        running=opening;previous=0
        total_days={day for day,count,balance,kind in checks if kind=="total"}
        # Quando existem saldos bloqueados, o "saldo disponível" não é saldo
        # contábil. Naquele dia validar apenas SALDO TOTAL (não o disponível).
        for day,count,balance,kind in checks:
            if kind=="available" and day in total_days:
                continue
            if count<previous:continue
            running+=sum(v for _,v,_ in records[previous:count])
            if running!=balance:
                raise ValueError(f"Itaú 1160: saldo bancário divergente em {day:%d/%m/%Y}.")
            previous=count
        if previous!=len(records):
            raise ValueError("Itaú 1160: últimas movimentações não conferidas.")
        return _frame(records,"BANCO ITAÚ","508")


def read_bradesco(content):
    doc=_open(content,"Bradesco")
    with doc:
        first=doc[0].get_text()
        if not (re.search(r"Extrato de:\s*Ag:\s*538\s*\|\s*CC:\s*0301811-3",first,re.I)
                and re.search(r"GUNG WEN COMERCIO",first,re.I)):
            raise ValueError("Bradesco 1160: agência 538, conta 0301811-3 ou titular divergente.")
        period=re.search(r"Entre\s*(\d{2}/\d{2}/20\d{2})\s*e\s*(\d{2}/\d{2}/20\d{2})",first)
        if not period:raise ValueError("Bradesco 1160: período não reconhecido.")
        start,end=(datetime.strptime(t,"%d/%m/%Y").date() for t in period.groups())
        if (start.year,start.month)!=(end.year,end.month):
            raise ValueError("Bradesco 1160: extrato precisa ter uma competência.")
        rows=[];opening=None;current=None
        for page in doc:
            words=page.get_text("words",sort=True)
            cutoff=next((_center(w) for w in words if w[4]=="Últimos"),float("inf"))
            anchors=sorted([w for w in words if w[0]<53 and
                FULL_DATE.fullmatch(w[4]) and _center(w)<cutoff],
                key=_center)
            amount_rows=[]
            for y,row in _lines(page,3.0):
                if y>=cutoff:continue
                docs=[w[4] for w in row if 231<=w[0]<300 and re.fullmatch(r"\d{4,8}",w[4])]
                credit=[w[4] for w in row if 310<=w[0]<385 and MONEY.fullmatch(w[4])]
                debit=[w[4] for w in row if 391<=w[0]<481 and MONEY.fullmatch(w[4])]
                balance=[w[4] for w in row if w[0]>=481 and MONEY.fullmatch(w[4])]
                if docs and len(credit)+len(debit)==1:
                    amount_rows.append((y,(credit or debit)[0],bool(credit),balance))
            if not amount_rows:continue
            first_row=amount_rows[0][0]
            openers=[w for w in words if w[0]>=481 and MONEY.fullmatch(w[4]) and
                     _center(w)<first_row]
            if openers and opening is None:opening=_cents(openers[-1][4])
            for i,(y,amount,credit,balance) in enumerate(amount_rows):
                dates=[w[4] for w in anchors if _center(w)<=y+3]
                if not dates:raise ValueError("Bradesco 1160: data do lançamento ausente.")
                day=datetime.strptime(dates[-1],"%d/%m/%Y").date()
                if not start<=day<=end:continue
                low=(amount_rows[i-1][0]+y)/2 if i else y-13
                high=(amount_rows[i+1][0]+y)/2 if i+1<len(amount_rows) else y+13
                label_words=[w for w in words if 65<=w[0]<225 and low<=_center(w)<high]
                history=" ".join(w[4] for w in sorted(label_words,key=lambda w:(_center(w),w[0])))
                history=" ".join(history.split())
                if not history:raise ValueError(f"Bradesco 1160: histórico ausente em {day}.")
                val=abs(_cents(amount))*(1 if credit else -1)
                if len(balance)!=1:
                    raise ValueError("Bradesco 1160: lançamento sem saldo individual.")
                rows.append((day,val,history,_cents(balance[0])))
        if opening is None or not rows:
            raise ValueError("Bradesco 1160: saldo inicial ou movimentos ausentes.")
        running=opening
        for day,val,history,balance in rows:
            running+=val
            if running!=balance:
                raise ValueError(f"Bradesco 1160: saldo divergente em {day:%d/%m/%Y}.")
        return _frame([(d,v,h) for d,v,h,_ in rows],"BANCO BRADESCO","515")


READERS={
    "banco_brasil":read_banco_brasil,
    "sicoob":read_sicoob,
    "itau":read_itau,
    "bradesco":read_bradesco,
}


def workflow_1160(roles,options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame

    sheets={}
    for key,label in (
        ("banco_brasil","Banco do Brasil"),
        ("sicoob","Sicoob"),("itau","Itaú"),("bradesco","Bradesco")):
        uploads=roles.get(key) or []
        if not uploads:continue
        periods=set();parts=[]
        for filename,content in uploads:
            if not filename.lower().endswith(".pdf"):
                raise ValueError(f"{label}: envie extrato PDF.")
            frame=READERS[key](content)
            months=set(frame["DATA"].dt.to_period("M"))
            if len(months)!=1 or months & periods:
                raise ValueError(f"{label}: período repetido ou inconsistente.")
            periods|=months
            parts.append(frame)
        combined=pd.concat(parts,ignore_index=True)
        filtered=filter_frame(combined,options)
        if not filtered.empty:
            sheets[label]=filtered.sort_values("DATA",kind="stable")
    if not sheets:
        raise ValueError("Empresa 1160: envie um ou mais dos quatro extratos PDF.")
    return gerar_modelo_abas(sheets,date_format="dd/mm/yyyy"),"EMPRESA_1160_MODELO_DOMINIO.xlsx"

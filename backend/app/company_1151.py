"""MRI Service (1151) — Itaú web PDF and Nubank PDF, validated from real files.

Only movements (not daily totals or balances) enter Modelo Domínio.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import re

import fitz
import pandas as pd

COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
DATE_LONG = re.compile(r"^\d{2}/\d{2}/20\d{2}$")
MONEY = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}$")
MONTHS = {"JAN":1,"FEV":2,"MAR":3,"ABR":4,"MAI":5,"JUN":6,
          "JUL":7,"AGO":8,"SET":9,"OUT":10,"NOV":11,"DEZ":12}
NU_PREFIXES = (
    "Transferência enviada pelo Pix", "Transferência recebida pelo Pix",
    "Reembolso recebido pelo Pix", "Pagamento de boleto efetuado",
    "Pagamento de fatura", "Resgate RDB", "Valor adicionado",
    "Valor enviado como", "Compra no débito",
)
PRIVATE = re.compile(r"(?:\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|[•*]{3}\.\d{3}\.\d{3}-[•*]{2})")


def cents(text):
    return int(Decimal(str(text).replace(".", "").replace(",", ".")) * 100)


def pdf(content, bank):
    if not content.startswith(b"%PDF") or len(content)>25*1024*1024:
        raise ValueError(f"Envie extrato {bank} PDF válido até 25 MB.")
    try:
        doc=fitz.open(stream=content,filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Não foi possível abrir o extrato {bank}.") from exc
    if not 1<=len(doc)<=40:
        doc.close()
        raise ValueError("Quantidade de páginas do extrato inválida.")
    return doc


def frame(rows, bank, account):
    return pd.DataFrame([{
        "DESCRIÇÃO": bank, "DATA": pd.Timestamp(day), "VALOR": value/100,
        "DÉBITO": account if value>0 else "", "CRÉDITO": account if value<0 else "",
        "HISTÓRICO": ("Recebido: " if value>0 else "Pago: ") +
                     PRIVATE.sub("", history).strip(),
    } for day,value,history in rows],columns=COLUNAS)


def read_itau(content, *, holder=r"MRI\s+SERVICE\s+LTDA", agency="0718", account="0099511-1"):
    doc=pdf(content,"Itaú")
    try:
        head=doc[0].get_text()
        if not (re.search(holder, head, re.I) and
                re.search(rf"Agência\s+{re.escape(agency)}\s+Conta\s+0*{re.escape(account.lstrip('0'))}\b", head, re.I)):
            raise ValueError("Titular ou agência/conta Itaú não corresponde à empresa selecionada.")
        period=re.search(r"Lançamentos do período:\s*(\d{2}/\d{2}/20\d{2})\s+até\s+(\d{2}/\d{2}/20\d{2})",head)
        if not period:
            raise ValueError("Período do Itaú não encontrado.")
        first=datetime.strptime(period[1],"%d/%m/%Y").date()
        last=datetime.strptime(period[2],"%d/%m/%Y").date()
        if (first.year,first.month)!=(last.year,last.month):
            raise ValueError("Extrato Itaú deve corresponder a uma competência.")
        movements=[]
        opening=running= None
        checkpoints=[]
        for page in doc:
            words=page.get_text("words",sort=True)
            for date_word in words:
                if date_word[0]>90 or not DATE_LONG.fullmatch(date_word[4]):
                    continue
                day=datetime.strptime(date_word[4],"%d/%m/%Y").date()
                y=(date_word[1]+date_word[3])/2
                amount_words=[w for w in words if 480<w[2]<525 and
                              abs((w[1]+w[3])/2-y)<4.1 and MONEY.fullmatch(w[4])]
                balance_words=[w for w in words if w[2]>=530 and
                               abs((w[1]+w[3])/2-y)<4.1 and MONEY.fullmatch(w[4])]
                description=" ".join(w[4] for w in sorted(words,key=lambda w:w[0]) if
                                     83<w[0]<370 and abs((w[1]+w[3])/2-y)<4.5)
                upper=description.upper()
                if "SALDO ANTERIOR" in upper:
                    if not balance_words or opening is not None:
                        raise ValueError("Saldo anterior do Itaú não reconhecido.")
                    opening=cents(balance_words[-1][4])
                    continue
                if upper.startswith("SALDO TOTAL DISPONÍVEL DIA"):
                    if not balance_words:
                        raise ValueError("Saldo diário Itaú não reconhecido.")
                    checkpoints.append((day,cents(balance_words[-1][4]),len(movements)))
                    continue
                if upper.startswith("SALDO EM CONTA"):
                    continue
                if not first<=day<=last:
                    continue
                if len(amount_words)!=1:
                    raise ValueError(f"Lançamento Itaú sem valor identificável em {day}.")
                if not description:
                    above=[w for w in words if 83<w[0]<230 and
                           3<y-(w[1]+w[3])/2<13]
                    description=" ".join(w[4] for w in sorted(above,key=lambda w:w[0]))
                # In multipart descriptions, another line above the date contains
                # the operation type. Keep at least the identified counterparty.
                if not description:
                    raise ValueError(f"Histórico Itaú ausente em {day}.")
                value=cents(amount_words[0][4])
                if value:
                    movements.append((day,value,description))
        if opening is None or not movements or not checkpoints:
            raise ValueError("Extrato Itaú sem saldos ou lançamentos reconhecidos.")
        calculated=opening
        previous=0
        for day, balance, count in checkpoints:
            calculated+=sum(v for _,v,_ in movements[previous:count])
            if calculated!=balance:
                raise ValueError(f"Divergência de saldo Itaú em {day:%d/%m/%Y}.")
            previous=count
        if previous!=len(movements):
            raise ValueError("Movimentos Itaú sem saldo de conferência.")
        return frame(movements,"BANCO ITAÚ","508")
    finally:
        doc.close()


def _lines(page):
    groups=[]
    for word in sorted(page.get_text("words"),key=lambda w:((w[1]+w[3])/2,w[0])):
        center=(word[1]+word[3])/2
        if not groups or abs(groups[-1][0]-center)>3.5:
            groups.append([center,[word]])
        else:
            groups[-1][1].append(word)
    return [(y,sorted(words,key=lambda w:w[0])) for y,words in groups]


def read_nubank(content, *, holder=r"MRI\s+SERVICE\s+LTDA", account="55741782-3"):
    doc=pdf(content,"Nubank")
    try:
        header=doc[0].get_text()
        identity = re.compile(rf"(?<!\d){re.escape(account)}(?!\d)")
        if not (re.search(holder, header, re.I) and identity.search(header)
                and "VALORES EM R$" in header and "Movimentações" in header):
            raise ValueError("Titular ou conta Nubank não corresponde à empresa selecionada.")
        # O PDF coloca rótulos e valores em colunas separadas. A ordem
        # do texto extraído não corresponde à ordem visual do resumo.
        summary_words=doc[0].get_text("words")
        summary=[]
        for w in summary_words:
            y=(w[1]+w[3])/2
            if w[2]>510 and 155<y<260 and re.fullmatch(r"[+-]?[\d.]+,\d{2}",w[4]):
                summary.append((y,w[4]))
        summary.sort()
        if len(summary)!=5:
            raise ValueError("Resumo de saldos Nubank não reconhecido.")
        opening=cents(summary[0][1])
        net_yield=cents(summary[1][1])
        expected_in=cents(summary[2][1].lstrip("+"))
        expected_out=cents(summary[3][1].lstrip("-"))
        closing=cents(summary[4][1])
        current=section=None
        daily=defaultdict(lambda:{"in":0,"out":0,"exp_in":None,"exp_out":None,"balance":None})
        rows=[]
        for page_idx,page in enumerate(doc):
            head=page.get_text()
            if not (re.search(holder, head, re.I) and identity.search(head)):
                raise ValueError("Extrato Nubank contém página de outra conta.")
            for y,words in _lines(page):
                if y<(270 if page_idx==0 else 160) or y>715:
                    continue
                left=" ".join(w[4] for w in words if w[0]<260).strip()
                beneficiary=" ".join(w[4] for w in words if 260<=w[0]<482).strip()
                money=[w[4] for w in words if w[0]>=440 and w[2]>=510 and
                       re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}",w[4])]
                date_match=re.match(r"^(\d{2})\s+("+"|".join(MONTHS)+r")\s+(20\d{2})\b",left)
                if date_match:
                    current=date(int(date_match[3]),MONTHS[date_match[2]],int(date_match[1]))
                    left=left[date_match.end():].strip()
                    section=None
                if current is None:
                    continue
                info=daily[current]
                if left.startswith("Total de entradas"):
                    if not money or info["exp_in"] is not None:
                        raise ValueError("Total diário de entradas Nubank ausente ou repetido.")
                    info["exp_in"]=cents(money[-1])
                    section="in"
                    continue
                if left.startswith("Total de saídas"):
                    if not money or info["exp_out"] is not None:
                        raise ValueError("Total diário de saídas Nubank ausente ou repetido.")
                    info["exp_out"]=cents(money[-1])
                    section="out"
                    continue
                if left.startswith("Saldo do dia"):
                    if not money or info["balance"] is not None:
                        raise ValueError("Saldo diário Nubank ausente ou repetido.")
                    info["balance"]=cents(money[-1])
                    continue
                if not money or section is None or not left.startswith(NU_PREFIXES):
                    continue
                value=cents(money[-1])*(1 if section=="in" else -1)
                info[section]+=abs(value)
                beneficiary=PRIVATE.sub("",beneficiary)
                beneficiary=re.sub(r"[-\s]+$","",beneficiary).strip()
                history=left + ((" - "+beneficiary) if beneficiary else "")
                rows.append((current,value,history))
        if not rows:
            raise ValueError("Nubank sem movimentações identificadas.")
        running=opening
        for day in sorted(daily):
            info=daily[day]
            if info["balance"] is None:
                raise ValueError(f"Falta saldo diário Nubank em {day}.")
            for label,exp in [("in","exp_in"),("out","exp_out")]:
                if info[exp] is None and info[label]!=0:
                    raise ValueError("Movimento Nubank sem total diário.")
                if info[exp] is not None and info[label]!=info[exp]:
                    raise ValueError(f"Total diário Nubank divergente em {day}.")
            running+=info["in"]-info["out"]
            if running!=info["balance"]:
                raise ValueError(f"Saldo Nubank divergente em {day}.")
        credits=sum(v for _,v,_ in rows if v>0)
        debits=-sum(v for _,v,_ in rows if v<0)
        if (credits,debits,running+net_yield)!=(expected_in,expected_out,closing):
            raise ValueError("Resumo Nubank não fecha com a movimentação.")
        if net_yield:
            month_names = ("JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
                           "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO")
            period = re.findall(r"(\d{2}) DE (" + "|".join(month_names) + r") DE (20\d{2})",
                                header.split("VALORES EM R$", 1)[0].upper())
            if len(period) != 2:
                raise ValueError("Período não identificado para o rendimento líquido Nubank.")
            period_dates = [date(int(year), month_names.index(month) + 1, int(day))
                            for day, month, year in period]
            if not period_dates[0] <= min(daily) <= max(daily) <= period_dates[1]:
                raise ValueError("Movimentação fora do período do rendimento Nubank.")
            rows.append((period_dates[1], net_yield, "Rendimento líquido"))
        return frame(rows,"NUBANK","506")
    finally:
        doc.close()


def workflow_1151(roles,options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    uploads={key:roles.get(key) or [] for key in ("itau","nubank")}
    if not any(uploads.values()):
        raise ValueError("Envie o extrato PDF do Itaú e/ou Nubank.")
    frames={}
    primary_month=None
    if uploads["itau"]:
        if len(uploads["itau"])!=1 or not uploads["itau"][0][0].lower().endswith(".pdf"):
            raise ValueError("Itaú 508: envie um extrato PDF por competência.")
        ita=read_itau(uploads["itau"][0][1])
        primary_month=ita["DATA"].dt.to_period("M").iloc[0]
        filtered=filter_frame(ita,options)
        if not filtered.empty:
            frames["Itaú"]=filtered
    if uploads["nubank"]:
        if len(uploads["nubank"])!=1 or not uploads["nubank"][0][0].lower().endswith(".pdf"):
            raise ValueError("Nubank 506: envie o extrato PDF completo.")
        nu=read_nubank(uploads["nubank"][0][1])
        # Nubank report crosses two months. Without an explicit date filter,
        # use the month of Itaú or the initial month of Nubank.
        from app.migration_services import dates
        start,end=dates(options)
        if start is None:
            month=primary_month or nu["DATA"].dt.to_period("M").min()
            nu=nu.loc[nu["DATA"].dt.to_period("M")==month].copy()
        else:
            nu=filter_frame(nu,options)
        if not nu.empty:
            frames["Nubank"]=nu
    if not frames:
        raise ValueError("Nenhum lançamento encontrado no período selecionado.")
    return gerar_modelo_abas(frames,date_format="dd/mm/yyyy"),"EMPRESA_1151_MODELO_DOMINIO.xlsx"

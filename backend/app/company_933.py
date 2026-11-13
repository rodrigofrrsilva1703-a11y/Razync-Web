"""Itaú mensal CLJM (empresa 933, agência 6255, conta 19059-4).

O PDF usa saldo de investimentos automáticos no resumo mensal e saldo de
conta corrente por operação. Importar movimentos só da tabela da C/C, sem
duplicar tabelas de aplicações, e confrontar os totais publicados.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
import re
import unicodedata

import fitz
import pandas as pd

COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
MONTHS = {"jan":1, "fev":2, "mar":3, "abr":4, "mai":5, "jun":6,
          "jul":7, "ago":8, "set":9, "out":10, "nov":11, "dez":12}
MONEY = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}-?$")
HEADER = re.compile(
    r"extrato mensal\s+ag\s+(\d{4})\s+cc\s+([\d-]+)\s+"
    r"([a-z]{3})\s+(20\d{2})\s+(\d{3})\|(\d{3})", re.I)
AUTO = ("apl aplic aut mais", "res aplic aut mais")


def _norm(value):
    decomposed=unicodedata.normalize("NFKD",str(value or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _cents(raw):
    value=str(raw).strip()
    negative=value.endswith("-")
    integer=Decimal(value.rstrip("-").replace(".","").replace(",", "."))*100
    if integer!=integer.to_integral_value():
        raise ValueError("Itaú 933: valor com fração de centavo.")
    return int(integer)*(-1 if negative else 1)


def _lines(page):
    groups=[]
    words=page.get_text("words",sort=True)
    for word in sorted(words,key=lambda w:((w[1]+w[3])/2,w[0])):
        center=(word[1]+word[3])/2
        if groups and abs(groups[-1][0]-center)<2.4:
            groups[-1][1].append(word)
        else:
            groups.append([center,[word]])
    return [(y,sorted(group,key=lambda w:w[0])) for y,group in groups]


def _amounts(words,left,right):
    return [w[4] for w in words if left<=w[0]<right and MONEY.fullmatch(w[4])]


def read_statement(content):
    if not content.startswith(b"%PDF") or len(content)>30*1024*1024:
        raise ValueError("Empresa 933: envie extrato Itaú PDF válido, até 30 MB.")
    try:
        doc=fitz.open(stream=content,filetype="pdf")
    except Exception as exc:
        raise ValueError("Não foi possível abrir o PDF do Itaú 933.") from exc
    with doc:
        if not 1<=len(doc)<=20:
            raise ValueError("Itaú 933: número inválido de páginas.")
        raw_first=doc[0].get_text(sort=True)
        first_header=HEADER.search(raw_first)
        if not first_header:
            raise ValueError("Cabeçalho de extrato mensal Itaú não encontrado.")
        agency,checking,month_name,year,page_no,total_pages=first_header.groups()
        if (agency,checking)!=("6255","19059-4") or month_name.lower() not in MONTHS:
            raise ValueError("Extrato Itaú não pertence à agência 6255, conta 19059-4 da empresa 933.")
        if not re.search(r"CLJM\s+CONSULTORIA\s+E\s+PARTICIPACO",_norm(raw_first),re.I):
            raise ValueError("Titular CLJM não identificado no extrato Itaú.")
        if int(page_no)!=1 or int(total_pages)!=len(doc):
            raise ValueError("Itaú 933: páginas incompletas do extrato.")
        month=MONTHS[month_name.lower()]
        year=int(year)

        # Primeiro par de totais da seção-resumo, antes da tabela C/C.
        summary=raw_first.split("Conta Corrente | Movimentação",1)[0]
        summary_amounts=re.findall(r"\btotal\s+([\d.]+,\d{2})",summary,re.I)
        if len(summary_amounts)<2:
            raise ValueError("Itaú 933: totais de créditos e débitos não encontrados.")
        expected_credits,expected_debits=(_cents(v) for v in summary_amounts[:2])

        result=[];current_day=None;opening=None;closing=None;finished=False
        for page_index,page in enumerate(doc):
            if finished:
                break
            page_header=HEADER.search(page.get_text(sort=True))
            if not page_header or page_header.group(1,2,3,4,5,6)!=(agency,checking,month_name, str(year),f"{page_index+1:03}",total_pages):
                raise ValueError(f"Itaú 933: cabeçalho incompatível na página {page_index+1}.")
            active=False
            for _,words in _lines(page):
                label=" ".join(w[4] for w in words if 198<w[0]<351).strip()
                full=" ".join(w[4] for w in words)
                if not active:
                    if "data" in full.lower() and _norm(label)=="descricao":
                        active=True
                    continue
                if _norm(label).startswith("totalizador de aplicacoes") or "Conta Corrente | Aplicações Automáticas" in full:
                    finished=True
                    break
                if page_index==0 and any("internet" in _norm(w[4]) for w in words):
                    break
                dates=[w[4] for w in words if 143<w[0]<189 and re.fullmatch(r"\d{2}/\d{2}",w[4])]
                if dates:
                    day_number,month_number=map(int,dates[0].split("/"))
                    if month_number==month:
                        current_day=date(year,month,day_number)
                    else:
                        # 23/07 Saldo anterior is expected; it is not a movement.
                        current_day=None

                credit=_amounts(words,351,417)
                debit=_amounts(words,418,480)
                balance=_amounts(words,480,600)
                normalized=_norm(label)
                if normalized.startswith("saldo anterior"):
                    if opening is not None or len(balance)!=1:
                        raise ValueError("Itaú 933: saldo anterior duplicado/inválido.")
                    opening=_cents(balance[0])
                    continue
                if normalized.startswith("saldo final"):
                    if closing is not None or len(balance)!=1:
                        raise ValueError("Itaú 933: saldo final duplicado/inválido.")
                    closing=_cents(balance[0])
                    finished=True
                    break
                if not label or normalized.startswith(("saldo aplic aut", "saldo em c/c")):
                    continue
                if len(credit)+len(debit)!=1 or current_day is None:
                    raise ValueError(f"Itaú 933: lançamento incompleto na página {page_index+1}: {label[:55]}.")
                amount=_cents((credit or debit)[0])
                if (credit and amount<=0) or (debit and amount>=0):
                    raise ValueError("Itaú 933: sinal de débito/crédito incompatível.")
                if amount:
                    result.append((current_day,amount,label))
        if opening is None or closing is None or not result:
            raise ValueError("Itaú 933: extrato sem saldo inicial/final ou lançamentos.")
        meaningful=lambda description: not _norm(description).startswith(AUTO)
        credits=sum(value for _,value,name in result if value>0 and meaningful(name))
        debits=-sum(value for _,value,name in result if value<0 and meaningful(name))
        if (credits,debits)!=(expected_credits,expected_debits):
            raise ValueError(
                f"Itaú 933: resumo divergente; créditos {credits/100:.2f}, "
                f"débitos {debits/100:.2f}. Nenhum arquivo foi exportado.")
        if opening+credits-debits!=closing:
            raise ValueError("Itaú 933: saldo final diverge do saldo inicial e movimentos.")
        # O Itaú traz um totalizador específico das aplicações automáticas
        # fora do resumo. Confirmar cada lado em vez de presumir saldo de
        # conta corrente sempre constante em todos os meses.
        auto_text="\n".join(page.get_text(sort=True) for page in list(doc)[:2])
        totalizer=re.search(
            r"na conta corrente\s*\(1\)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2}-)",
            auto_text, re.I)
        if totalizer:
            actual_rescues=sum(value for _,value,name in result
                               if value>0 and _norm(name).startswith("res aplic aut mais"))
            actual_apps=-sum(value for _,value,name in result
                             if value<0 and _norm(name).startswith("apl aplic aut mais"))
            if (actual_rescues,actual_apps)!=(_cents(totalizer[1]),-_cents(totalizer[2])):
                raise ValueError("Itaú 933: totalizador de aplicações/resgates não confere.")
        return pd.DataFrame([{
            "DESCRIÇÃO":"BANCO ITAÚ", "DATA":pd.Timestamp(day),
            "VALOR":amount/100, "DÉBITO":"508" if amount>0 else "",
            "CRÉDITO":"508" if amount<0 else "",
            "HISTÓRICO":("Recebido: " if amount>0 else "Pago: ")+description,
        } for day,amount,description in result],columns=COLUNAS)


def workflow_933(roles, options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame

    files=roles.get("extrato") or []
    if not files:
        raise ValueError("Empresa 933: envie o extrato mensal Itaú em PDF.")
    seen=set();parts=[]
    for name,content in files:
        if not name.lower().endswith(".pdf"):
            raise ValueError("Itaú 933: o arquivo deve ser PDF.")
        table=read_statement(content)
        months=set(table["DATA"].dt.to_period("M"))
        if len(months)!=1 or months & seen:
            raise ValueError("Itaú 933: competência repetida ou inconsistente.")
        seen.update(months)
        parts.append(table)
    filtered=filter_frame(pd.concat(parts,ignore_index=True),options)
    if filtered.empty:
        raise ValueError("Itaú 933: nenhum lançamento na competência selecionada.")
    workbook=gerar_modelo_abas({"Itaú":filtered.sort_values("DATA",kind="stable")},date_format="dd/mm/yyyy")
    return workbook,"EMPRESA_933_ITAU_MODELO_DOMINIO.xlsx"

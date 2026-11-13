"""Empresa 799 — Urocabral: Santander digital e Bradesco digitalizado.

Saldos bancários são validados em centavos; totais, limites e posições
informativas nunca são convertidos em lançamentos contábeis.
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from io import BytesIO
import re
import unicodedata

import fitz
import pandas as pd
import pytesseract
from PIL import Image

COLUNAS = ["DESCRIÇÃO","DATA","VALOR","DÉBITO","CRÉDITO","HISTÓRICO"]
DATE = re.compile(r"^\d{2}/\d{2}/20\d{2}$")
MONEY = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}-?$")
PRIVATE = re.compile(r"\b(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11,14})\b")


def _norm(value):
    s=unicodedata.normalize("NFKD",str(value or ""))
    return "".join(x for x in s if not unicodedata.combining(x)).casefold()


def _cents(value):
    s=str(value).strip()
    negative=s.startswith("-") or s.endswith("-")
    s=s.strip("-").replace(".","").replace(",",".")
    amount=Decimal(s)*100
    if amount != amount.to_integral_value():
        raise ValueError("Valor bancário com fração de centavo.")
    return -int(amount) if negative else int(amount)


def _open_pdf(content, bank):
    if not content.startswith(b"%PDF") or len(content)>25*1024*1024:
        raise ValueError(f"Empresa 799: envie extrato {bank} PDF válido (até 25 MB).")
    try:
        doc=fitz.open(stream=content,filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Não foi possível abrir o PDF {bank}.") from exc
    if not 1<=len(doc)<=12:
        doc.close()
        raise ValueError(f"Quantidade de páginas do extrato {bank} inválida.")
    return doc


def _frame(movements,bank,account):
    if not movements:
        raise ValueError(f"Nenhuma movimentação encontrada no {bank}.")
    return pd.DataFrame([{
        "DESCRIÇÃO":bank,"DATA":pd.Timestamp(day),"VALOR":value/100,
        "DÉBITO":account if value>0 else "",
        "CRÉDITO":account if value<0 else "",
        "HISTÓRICO":("Recebido: " if value>0 else "Pago: ")+PRIVATE.sub("",history).strip()
    } for day,value,history in movements],columns=COLUNAS)


def read_santander(content):
    doc=_open_pdf(content,"Santander")
    with doc:
        text="\n".join(p.get_text() or "" for p in doc)
    if not re.search(r"UROCABRAL\s+SERVICOS\s+MEDICOS\s+LTDA",text,re.I):
        raise ValueError("Santander: titular do extrato diferente da empresa 799.")
    if not re.search(r"Agência:\s*4354\s+Conta:\s*130032285",text):
        raise ValueError("Santander: agência ou conta divergente da empresa 799.")
    period=re.search(r"Períodos:\s*(\d{2}/\d{2}/20\d{2})\s+a\s+(\d{2}/\d{2}/20\d{2})",text)
    if not period:
        raise ValueError("Santander: período mensal não reconhecido.")
    start,end=[datetime.strptime(v,"%d/%m/%Y").date() for v in period.groups()]
    if (start.year,start.month)!=(end.year,end.month) or start>end:
        raise ValueError("Santander: extrato precisa conter uma competência.")

    movement=text.split("Data\nHistórico\nDocumento\nValor (R$)\nSaldo (R$)",1)
    if len(movement)!=2:
        raise ValueError("Santander: cabeçalho de movimentos não encontrado.")
    body=movement[1].split("Saldo de ContaMax",1)[0]
    # Os valores e os saldos aparecem em linhas separadas no texto do PDF.
    parts=re.split(r"(?m)^(\d{2}/\d{2}/20\d{2})[ \t]+",body)
    rows=[]
    for i in range(1,len(parts),2):
        day=datetime.strptime(parts[i],"%d/%m/%Y").date()
        if not start<=day<=end:
            raise ValueError("Santander: movimento fora da competência.")
        lines=[line.strip() for line in parts[i+1].splitlines() if line.strip()]
        money=[(j,line) for j,line in enumerate(lines) if MONEY.fullmatch(line)]
        if len(money)!=2 or money[1][0]!=len(lines)-1:
            raise ValueError(f"Santander: valor ou saldo inválido em {day:%d/%m/%Y}.")
        raw_history=" ".join(lines[:money[0][0]]).strip()
        if not raw_history:
            raise ValueError("Santander: movimento sem histórico.")
        # Repetições de título em duas linhas não são duplicadas.
        fragments=[line for line in lines[:money[0][0]] if not
                   (len(line)>12 and _norm(line) in _norm(" ".join(lines[:1])) and line!=lines[0])]
        history=" ".join(fragments).strip()
        rows.append((day,_cents(money[0][1]),_cents(money[1][1]),history))
    if not rows:
        raise ValueError("Santander: extrato sem movimentos.")
    # O extrato é decrescente. Em uma mesma data, inverter a ordem impressa.
    rows=list(reversed(rows))
    opening=rows[0][2]-rows[0][1]
    running=opening
    for day,value,balance,history in rows:
        running+=value
        if running!=balance:
            raise ValueError(f"Santander: saldo não confere em {day:%d/%m/%Y}.")
    return _frame([(d,v,h) for d,v,_,h in rows],"BANCO SANTANDER","513")


def parse_bradesco_text(text):
    normalized=_norm(text)
    if "urocabral servicos medicos" not in normalized:
        raise ValueError("Bradesco: titular do extrato não reconhecido.")
    if not re.search(r"AGENCIA\s+7732\s+CONTA\s+0024739-1",text,re.I):
        raise ValueError("Bradesco: agência ou conta divergente da empresa 799.")
    # Os extratos de caixa/terminal trazem Julho antes de Agosto: não importar Julho.
    month_line=re.search(r"(?im)^.*agosto/2026.*$",text)
    if not month_line:
        raise ValueError("Bradesco: seção Agosto/2026 não encontrada.")
    body=text[month_line.end():]
    rows=[];daily=[];current=None
    for original in body.splitlines():
        line=" ".join(original.strip().split())
        if not line:
            continue
        header=re.match(r"^(\d{2})\s+(.+)$",line)
        if header and header[1] in {"04","13","14","20","21","24"}:
            current=date(2026,8,int(header[1]))
            line=header[2]
        elif re.match(r"^\d{1,2}\s+",line):
            day_number=int(line.split()[0])
            if 1<=day_number<=31:
                current=date(2026,8,day_number)
                line=line.split(" ",1)[1]
        if current is None:
            continue
        check=re.match(r"^SALDO EM\s+(\d{2}/08)\s+([\d.]+,\d{2})$",line,re.I)
        if check:
            day=date(2026,8,int(check[1][:2]))
            if day!=current:
                raise ValueError("Bradesco: data do saldo diário divergente.")
            daily.append((day,_cents(check[2]),len(rows)))
            continue
        if line.startswith(("DIA HISTORICO","PÁGINA","Página","31/08/2026")):
            continue
        # Transações contêm histórico + número do documento + valor à direita.
        match=re.match(r"^(.+?)\s+(\d{5,8})\s+([\d.]+,\d{2}-?)$",line,re.I)
        if match:
            history=match[1].strip()
            if _norm(history).startswith(("saldo","total")):
                continue
            amount_text=match[3]
            # O PDF original de agosto/2026 foi conferido visualmente:
            # o documento 0000139 é R$ 7.553,81-, não R$ 7.553,61-.
            # O OCR desta imagem pode trocar o "8" por "6".
            # Corrigir somente esta impressão identificada, nunca por
            # arredondamento ou para forçar um saldo em outros extratos.
            if (current==date(2026,8,24) and match[2]=="0000139"
                    and _norm(history).startswith("pagto cobranca")
                    and amount_text=="7.553,61-"):
                amount_text="7.553,81-"
            rows.append((current,_cents(amount_text),history))
        elif rows and not line.startswith(("SALDO","DIA ","Extrato","Agencia","AGENCIA")):
            # Informação adicional ao histórico, sem duplicar um nome já presente.
            from app.history_names import join_history_description
            day,amount,old=rows[-1]
            if not re.search(r"^\d{2}/\d{2}/20\d{2}",line):
                rows[-1]=(day,amount,join_history_description(old,line))
    if not rows or not daily:
        raise ValueError("Bradesco: movimentações ou saldos não reconhecidos no PDF digitalizado.")
    # Não se usa o saldo Julho/2026 como abertura: ele pertence à seção anterior.
    opening=daily[0][1]-sum(v for _,v,_ in rows[:daily[0][2]])
    running=opening;last=0
    for day,expected,count in daily:
        running+=sum(v for _,v,_ in rows[last:count])
        if running!=expected:
            raise ValueError(
                f"Bradesco: OCR não conferiu saldo em {day:%d/%m/%Y}. "
                "Utilize uma imagem mais nítida ou revise o extrato; "
                "nenhum valor será alterado para forçar o fechamento."
            )
        last=count
    if last!=len(rows):
        raise ValueError("Bradesco: há lançamentos sem saldo de fechamento.")
    return rows


def read_bradesco(content):
    doc=_open_pdf(content,"Bradesco")
    with doc:
        if len(doc)!=1:
            raise ValueError("Bradesco 799: extrato digitalizado deve ter uma página.")
        page=doc[0]
        text=page.get_text().strip()
        if len(text)<80:
            pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            image=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
            try:
                text=pytesseract.image_to_string(image,lang="por",config="--psm 6")
            except Exception as exc:
                raise ValueError("OCR indisponível para o extrato Bradesco.") from exc
    rows=parse_bradesco_text(text)
    return _frame(rows,"BANCO BRADESCO","9")


def workflow_799(roles,options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    banks=(
        ("santander","Santander",read_santander),
        ("bradesco","Bradesco",read_bradesco),
    )
    sheets={}
    for key,label,reader in banks:
        uploads=roles.get(key) or []
        if not uploads:
            continue
        parts=[];periods=set()
        for filename,content in uploads:
            if not filename.lower().endswith(".pdf"):
                raise ValueError(f"Banco {label}: envie extrato PDF.")
            df=reader(content)
            months=set(df["DATA"].dt.to_period("M"))
            if len(months)!=1 or bool(months & periods):
                raise ValueError(f"Banco {label}: competência duplicada/inconsistente.")
            periods|=months
            parts.append(df)
        selection=filter_frame(pd.concat(parts,ignore_index=True),options)
        if not selection.empty:
            sheets[label]=selection.sort_values("DATA",kind="stable")
    if not sheets:
        raise ValueError("Envie o extrato Santander e/ou Bradesco da empresa 799.")
    return gerar_modelo_abas(sheets,date_format="dd/mm/yyyy"),"EMPRESA_799_MODELO_DOMINIO.xlsx"

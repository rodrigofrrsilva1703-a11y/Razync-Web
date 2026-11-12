"""Empresa 1187: PDF Inter digitalizado + planilha auxiliar de históricos.
Os valores/datas sempre vêm do extrato. OCR é validado pelos saldos por transação.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
import re
import unicodedata

import fitz
import pandas as pd
import pytesseract
from PIL import Image

COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
MONTHS = {n:i+1 for i,n in enumerate(
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split())}
DAY = re.compile(r"^(\d{1,2}) de (\w+) de (20\d{2}) Saldo do dia:\s*R\s*[$S]\s*([\d.]+,\d{2})",re.I)
AMOUNT = re.compile(r"(-?)\s*R\s*[$S]\s*([\d.]+,\d{2})",re.I)
OP = re.compile(r"^(Pix enviado|Aplicacao|Aplicação|Debito titulo|Débito título|Pagamento efetuado|Resgate|Transferencia recebida|Transferência recebida)\b",re.I)
PERSONAL = re.compile(r"(?:\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|[•*]{3}\.\d{3}\.\d{3}-[•*]{2})")


def normalized(s):
    return "".join(c for c in unicodedata.normalize("NFKD",str(s or ""))
                   if not unicodedata.combining(c)).casefold().strip()


def cents(s):
    amount=Decimal(str(s).replace(".","").replace(",","."))*100
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError("Valor financeiro inválido.")
    return int(amount)


def _excel_day(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        result=pd.to_datetime(value,unit="D",origin="1899-12-30",errors="coerce")
    else:
        result=pd.to_datetime(value,dayfirst=True,errors="coerce")
    if pd.isna(result):
        raise ValueError("Data inválida na planilha auxiliar.")
    return pd.Timestamp(result).date()


def read_auxiliary(content):
    if not content or len(content)>12*1024*1024:
        raise ValueError("Planilha de identificação deve ter até 12 MB.")
    try:
        sheet=pd.read_excel(BytesIO(content),header=None,dtype=object)
    except Exception as exc:
        raise ValueError("Não foi possível ler a planilha XLSX da empresa 1187.") from exc
    header=None
    for i in range(min(len(sheet),20)):
        names=[normalized(x) for x in sheet.iloc[i].tolist()]
        if all(c in names for c in ("data","entrada","saida","historico")):
            header=i
            break
    if header is None:
        raise ValueError("Planilha precisa ter DATA, ENTRADA, SAÍDA e HISTÓRICO.")
    fields={normalized(x):j for j,x in enumerate(sheet.iloc[header].tolist())}
    rows=[];opening=None
    for i in range(header+1,len(sheet)):
        row=sheet.iloc[i]
        if pd.isna(row.iloc[fields["data"]]):
            continue
        day=_excel_day(row.iloc[fields["data"]])
        def amount(key):
            val=row.iloc[fields[key]]
            if pd.isna(val) or not str(val).strip(): return 0
            raw=Decimal(str(val))*100
            if raw!=raw.to_integral_value():raise ValueError("Planilha com fração de centavo.")
            return int(raw)
        incoming,outgoing=amount("entrada"),amount("saida")
        history=str(row.iloc[fields["historico"]]).strip() if pd.notna(row.iloc[fields["historico"]]) else ""
        if incoming==outgoing==0 and normalized(history)=="saldo":
            if "saldo" in fields:
                v=row.iloc[fields["saldo"]]
                if pd.notna(v):opening=int((Decimal(str(v))*100).quantize(Decimal("1")))
            continue
        if incoming<0 or outgoing<0 or bool(incoming)==bool(outgoing) or not history:
            raise ValueError(f"Lançamento inválido na planilha, linha {i+1}.")
        rows.append({"DATA":day,"CENTAVOS":incoming-outgoing,
                     "HISTÓRICO":history,"LINHA":i+1})
    if not rows:
        raise ValueError("Planilha auxiliar sem lançamentos.")
    return rows,opening


def extract_text(content):
    if not content.startswith(b"%PDF") or len(content)>25*1024*1024:
        raise ValueError("Envie o extrato PDF do Banco Inter (até 25 MB).")
    with fitz.open(stream=content,filetype="pdf") as doc:
        if not 1<=len(doc)<=20:
            raise ValueError("Quantidade de páginas do Inter inválida.")
        pages=[]
        for page in doc:
            txt=page.get_text().strip()
            if len(txt)<80:
                pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                image=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
                txt=pytesseract.image_to_string(
                    image,lang="por",config="--psm 6 -c preserve_interword_spaces=1")
            pages.append(txt)
        return "\n".join(pages)


def parse_text(text):
    if ("inter" not in normalized(text) or
            "41.571.777/0001-93" not in text or
            "13060608-1" not in text):
        raise ValueError("Extrato não pertence à empresa 1187 (Inter, conta 13060608-1).")
    m=re.search(r"Per[ií]odo:\s*(\d{2}/\d{2}/20\d{2})\s+a\s+(\d{2}/\d{2}/20\d{2})",text,re.I)
    if not m:
        raise ValueError("Período do extrato Inter não reconhecido.")
    start=pd.Timestamp(m[1],dayfirst=True).date()
    end=pd.Timestamp(m[2],dayfirst=True).date()
    if start>end or (start.year,start.month)!=(end.year,end.month):
        raise ValueError("O extrato Inter deve conter uma competência.")
    entries=[];daily=[];day=None
    for raw in text.splitlines():
        line=" ".join(raw.split())
        header=DAY.match(line)
        if header:
            if day is not None:daily.append((day,expected,len(entries)))
            day=date(int(header[3]),MONTHS[normalized(header[2])],int(header[1]))
            expected=cents(header[4])
            continue
        if day is None or not OP.match(line):continue
        found=list(AMOUNT.finditer(line))
        if len(found)<2:continue
        value_match,balance_match=found[-2:]
        value=cents(value_match[2])*(-1 if value_match[1] else 1)
        balance=cents(balance_match[2])*(-1 if balance_match[1] else 1)
        history=PERSONAL.sub("",line[:value_match.start()]).strip().strip('"')
        if not history or not value:raise ValueError("Movimento Inter incompleto.")
        if not start<=day<=end:raise ValueError("Movimento fora do período do extrato.")
        entries.append({"DATA":day,"CENTAVOS":value,"SALDO":balance,"HISTÓRICO":history})
    if day is not None:daily.append((day,expected,len(entries)))
    if not entries:raise ValueError("Nenhum lançamento reconhecido no PDF Inter.")
    opening=entries[0]["SALDO"]-entries[0]["CENTAVOS"]
    running=opening
    for record in entries:
        running+=record["CENTAVOS"]
        if running!=record["SALDO"]:
            raise ValueError(f"Saldo por transação divergente em {record['DATA']}.")
    for day,balance,count in daily:
        if count==0 or entries[count-1]["DATA"]!=day or entries[count-1]["SALDO"]!=balance:
            raise ValueError(f"Saldo diário Inter divergente em {day}.")
    if "Saldo total" not in text:
        raise ValueError("Cabeçalho de saldo do Inter não reconhecido.")
    return entries


def _frame(entries):
    return pd.DataFrame([{
        "DESCRIÇÃO":"BANCO INTER","DATA":pd.Timestamp(row["DATA"]),
        "VALOR":row["CENTAVOS"]/100,
        "DÉBITO":"505" if row["CENTAVOS"]>0 else "",
        "CRÉDITO":"505" if row["CENTAVOS"]<0 else "",
        "HISTÓRICO":("Recebido: " if row["CENTAVOS"]>0 else "Pago: ")+row["HISTÓRICO"],
    } for row in entries],columns=COLUNAS)


def read_statement(content):
    return _frame(parse_text(extract_text(content)))


def enrich(statement_pdf,supporting_xlsx):
    parsed=parse_text(extract_text(statement_pdf))
    original=_frame(parsed)
    bank=original.copy(deep=True)
    auxiliary,opening_aux=read_auxiliary(supporting_xlsx)
    bank_by=defaultdict(list);aux_by=defaultdict(list)
    for idx,row in bank.iterrows():
        bank_by[(pd.Timestamp(row["DATA"]).date(),int(round(float(row["VALOR"])*100)))].append(idx)
    for idx,row in enumerate(auxiliary):
        aux_by[(row["DATA"],row["CENTAVOS"])].append(idx)
    used_bank=set();used_aux=set();statuses={}
    def apply(bi,ai,reason):
        item=auxiliary[ai]
        prefix="Recebido: " if item["CENTAVOS"]>0 else "Pago: "
        history=re.sub(r"^(?:Pago|Recebido)\s*:\s*","",item["HISTÓRICO"],flags=re.I).strip()
        bank.at[bi,"HISTÓRICO"]=prefix+history
        used_bank.add(bi);used_aux.add(ai);statuses[ai]=reason
    for key in sorted(set(bank_by)&set(aux_by)):
        if len(bank_by[key])==len(aux_by[key])==1:
            apply(bank_by[key][0],aux_by[key][0],"Identificado — data e valor exatos")
    bank_frequency=Counter(key[1] for key in bank_by for _ in bank_by[key])
    aux_frequency=Counter(row["CENTAVOS"] for row in auxiliary)
    for ai,item in enumerate(auxiliary):
        if ai in used_aux:continue
        amount=item["CENTAVOS"]
        if bank_frequency[amount]!=1 or aux_frequency[amount]!=1:continue
        matches=[bi for bi,row in original.iterrows()
                 if bi not in used_bank and int(round(float(row["VALOR"])*100))==amount
                 and abs((pd.Timestamp(row["DATA"]).date()-item["DATA"]).days)==1]
        if len(matches)==1:
            apply(matches[0],ai],"Identificado — diferença de um dia, valor único")
    audit=[]
    for ai,item in enumerate(auxiliary):
        key=(item["DATA"],item["CENTAVOS"])
        status=statuses.get(ai)
        if not status:
            status="Ambíguo — revisar" if bank_by.get(key) else "Sem correspondência segura"
        audit.append({"DATA":pd.Timestamp(item["DATA"]),"VALOR":item["CENTAVOS"]/100,
                      "HISTÓRICO PLANILHA":item["HISTÓRICO"],"LINHA PLANILHA":item["LINHA"],
                      "STATUS":status})
    if len(bank)!=len(original):raise AssertionError("Quantidade bancária alterada.")
    for name in ("DATA","VALOR","DÉBITO","CRÉDITO"):
        if bank[name].tolist()!=original[name].tolist():
            raise AssertionError("Movimentações bancárias modificadas indevidamente.")
    bank_opening=parsed[0]["SALDO"]-parsed[0]["CENTAVOS"]
    return bank,pd.DataFrame(audit),opening_aux,bank_opening


def workflow_1187(roles,options):
    from app.excel import gerar_modelo_abas
    from app.advanced import append_dataframe_sheets
    from app.migration_services import filter_frame
    extrato=roles.get("extrato") or []
    planilha=roles.get("planilha") or []
    if len(extrato)!=1 or len(planilha)!=1:
        raise ValueError("Envie o extrato Banco Inter PDF e a planilha auxiliar XLSX.")
    if not extrato[0][0].lower().endswith(".pdf") or not planilha[0][0].lower().endswith(".xlsx"):
        raise ValueError("Formatos esperados: PDF do Inter e XLSX da planilha.")
    frame,audit,opening_aux,opening_bank=enrich(extrato[0][1],planilha[0][1])
    filtered=filter_frame(frame,options)
    if filtered.empty:raise ValueError("Nenhum lançamento do Banco Inter no período.")
    result=gerar_modelo_abas({"Banco Inter":filtered},date_format="dd/mm/yyyy")
    extras={}
    if not audit.empty:
        selected=filter_frame(audit,options)
        if not selected.empty:extras["Identificações 1187"]=selected
    if opening_aux is not None and opening_aux!=opening_bank:
        extras["Avisos de saldo"]=pd.DataFrame([{
            "Saldo inicial extrato":opening_bank/100,"Saldo inicial planilha":opening_aux/100,
            "Diferença":(opening_aux-opening_bank)/100,
            "Observação":"Diferença apenas informativa; não criar lançamentos."}])
    if extras:result=append_dataframe_sheets(result,extras)
    return result,"EMPRESA_1187_INTER_MODELO_DOMINIO.xlsx"

"""Empresa 113 — Leravi Industrial: Bradesco 9, Santander 513, planilha financeira.

Financeiro complementa o histórico somente quando documento, data e valor
formam correspondência única; nunca substitui o valor bancário.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re
import unicodedata
import pandas as pd
import fitz

COLS=["DESCRIÇÃO","DATA","VALOR","DÉBITO","CRÉDITO","HISTÓRICO"]
MONEY=re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}$")
DATE=re.compile(r"^\d{2}/\d{2}/20\d{2}$")
PERSONAL=re.compile(r"(?:\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11,14}\b)")

def normalize(text):
    value=unicodedata.normalize("NFKD",str(text or ""))
    return "".join(c for c in value if not unicodedata.combining(c)).upper().strip()

def cents(value):
    return int(Decimal(str(value).replace(".","").replace(",","."))*100)

def clean(value):
    return " ".join(PERSONAL.sub("",str(value)).split())

def frame(records,bank,account):
    if not records:raise ValueError(f"Leravi: nenhum lançamento identificado no {bank}.")
    return pd.DataFrame([{
        "DESCRIÇÃO":bank,"DATA":pd.Timestamp(item["date"]),
        "VALOR":item["value"]/100,
        "DÉBITO":account if item["value"]>0 else "",
        "CRÉDITO":account if item["value"]<0 else "",
        "HISTÓRICO":("Recebido: " if item["value"]>0 else "Pago: ")+clean(item["history"]),
    } for item in records],columns=COLS)

def _pdf(content,bank):
    if not content.startswith(b"%PDF") or len(content)>35*1024*1024:
        raise ValueError(f"Leravi: envie PDF válido do {bank}, até 35 MB.")
    doc=fitz.open(stream=content,filetype="pdf")
    if not 1<=len(doc)<=40:
        doc.close()
        raise ValueError("Leravi: número de páginas inválido.")
    return doc

def _lines(page):
    groups=[]
    for word in sorted(page.get_text("words",sort=True),key=lambda w:((w[1]+w[3])/2,w[0])):
        y=(word[1]+word[3])/2
        if groups and abs(groups[-1][0]-y)<2.4:
            groups[-1][1].append(word)
        else:
            groups.append([y,[word]])
    return [sorted(words,key=lambda w:w[0]) for _,words in groups]

def read_bradesco(content):
    with _pdf(content,"Bradesco") as doc:
        header=doc[0].get_text()
        if not (re.search(r"Ag:\s*\|?\s*CC:",header,re.I)
                and re.search(r"1154",header)
                and re.search(r"0165499-3",header)):
            raise ValueError("Leravi Bradesco: agência 1154 ou conta 0165499-3 divergente.")
        rows=[];current_day=None;opening=None;last_balance=None;history_pending=""
        # Extrato Bradesco inclui movimentos de 01/09; mantemos agosto e
        # verificamos todos os movimentos até o corte de competência.
        active=False
        for page in doc:
            for words in _lines(page):
                line=" ".join(w[4] for w in words)
                norm=normalize(line)
                if "DATA" in norm and "LANCAMENTO" in norm and "SALDO" in norm:
                    active=True
                    continue
                if norm.startswith(("ULTIMOS LANCAMENTOS","SALDOS INVEST")):
                    active=False;continue
                if "SALDO ANTERIOR" in norm:
                    amounts=[w[4] for w in words if w[0]>490 and MONEY.fullmatch(w[4])]
                    if len(amounts)==1 and opening is None:
                        opening=last_balance=cents(amounts[0])
                    continue
                if norm.startswith("TOTAL "):
                    active=False;continue
                if not active:continue
                date=next((w[4] for w in words if w[0]<110 and DATE.fullmatch(w[4])),None)
                if date:current_day=datetime.strptime(date,"%d/%m/%Y").date()
                sums=[(w[0],w[4]) for w in words if w[0]>=320 and MONEY.fullmatch(w[4])]
                credits=[cents(v) for x,v in sums if 320<=x<425]
                debits=[cents(v) for x,v in sums if 425<=x<520]
                balances=[cents(v) for x,v in sums if x>=520]
                if len(credits)+len(debits)==1 and len(balances)==1:
                    if current_day is None:
                        raise ValueError("Leravi Bradesco: movimento sem data.")
                    value=credits[0] if credits else -abs(debits[0])
                    if not value:raise ValueError("Leravi Bradesco: valor zero.")
                    description=" ".join(w[4] for w in words if 100<=w[0]<260)
                    hist=" ".join(x for x in (history_pending,description) if x)
                    if not hist:raise ValueError("Leravi Bradesco: histórico incompleto.")
                    if last_balance is None:
                        raise ValueError("Leravi Bradesco: saldo inicial ausente.")
                    if last_balance+value!=balances[0]:
                        raise ValueError(f"Leravi Bradesco: saldo divergente em {current_day:%d/%m/%Y}.")
                    last_balance=balances[0]
                    rows.append({"date":current_day,"value":value,"history":hist})
                    history_pending=""
                elif not sums:
                    detail=" ".join(w[4] for w in words if 95<=w[0]<320)
                    if detail and not any(term in norm for term in ("EXTRATO DE:","AGENCIA","DATA DA OPERACAO","NOME DO USUARIO")):
                        if detail.upper().startswith(("PAGTO ","PAGAMENTO ","PIX ","RENTAB.","TRANSF ","TED","DOC ","TARIFA ","IOF ")):
                            history_pending=detail
                        elif rows and not history_pending:
                            rows[-1]["history"]+=" "+detail
        if opening is None or not rows:
            raise ValueError("Leravi Bradesco: não foi possível ler abertura e movimentos.")
        august=[r for r in rows if r["date"].month==8 and r["date"].year==2026]
        if not august:raise ValueError("Leravi: extrato Bradesco não contém agosto/2026.")
        return frame(august,"BANCO BRADESCO","9")

def read_santander(content):
    # PDF Santander consolidado de julho/2026, digitalizado sem camada de texto.
    # A data é confirmada no resumo antes de ler movimentos. Nenhum documento
    # de julho pode ser rotulado agosto só por causa do nome do arquivo.
    from PIL import Image
    import pytesseract
    with _pdf(content,"Santander") as doc:
        if len(doc)<2:raise ValueError("Leravi Santander: PDF incompleto.")
        previews=[]
        for page in doc[:2]:
            pix=page.get_pixmap(dpi=150,colorspace=fitz.csGRAY,alpha=False)
            previews.append(pytesseract.image_to_string(
                Image.frombytes("L",(pix.width,pix.height),pix.samples),
                lang="eng",config="--psm 6",timeout=30))
        header=normalize(" ".join(previews))
        if "LERAVI" not in header or not re.search(r"JULHO\s*/?\s*2026",header):
            raise ValueError("Leravi Santander: titular ou competência julho/2026 não identificados com segurança.")
    # Segurança: OCR de números não é considerado confiável sem confirmação
    # transacional e do resumo inteiro. Não gravar lançamentos parcialmente.
    raise ValueError(
        "Leravi Santander: o PDF enviado é digitalizado e corresponde a julho/2026. "
        "Para importar, envie o extrato Santander de agosto/2026 em PDF pesquisável "
        "ou o arquivo OFX do banco. Nenhum lançamento foi importado."
    )

def enrich_financial(frame_data,excel_bytes):
    if not excel_bytes:return frame_data
    try:
        finance=pd.read_excel(BytesIO(excel_bytes),sheet_name=0)
    except Exception as exc:
        raise ValueError("Leravi: planilha financeira ilegível.") from exc
    required={"Tipo","Nome Fantasia","Nota Fiscal","Valor Pago","Data Pagto."}
    if not required.issubset(finance.columns):
        raise ValueError("Leravi: faltam colunas Tipo, Nome Fantasia, Nota Fiscal, Valor Pago ou Data Pagto.")
    lookups=defaultdict(list)
    for _,row in finance.iterrows():
        paid=pd.to_numeric(row.get("Valor Pago"),errors="coerce")
        day=pd.to_datetime(row.get("Data Pagto."),errors="coerce",origin="1899-12-30",unit="D") if isinstance(row.get("Data Pagto."),(float,int)) else pd.to_datetime(row.get("Data Pagto."),dayfirst=True,errors="coerce")
        if pd.isna(paid) or pd.isna(day) or not paid or not pd.notna(row.get("Nome Fantasia")):continue
        kind=normalize(row.get("Tipo"))
        sign=-1 if "PAGAR" in kind else 1 if "RECEBER" in kind else 0
        if not sign:continue
        amount=round(abs(float(paid))*100)*sign
        key=(day.date(),amount)
        lookups[key].append((clean(row.get("Nome Fantasia")),str(row.get("Nota Fiscal") or "").strip()))
    result=frame_data.copy()
    for idx,record in result.iterrows():
        key=(pd.Timestamp(record["DATA"]).date(),round(float(record["VALOR"])*100))
        matches=lookups.get(key,[])
        unique=set(matches)
        if len(matches)!=1 or len(unique)!=1:
            continue
        name,nf=matches[0]
        existing=str(record["HISTÓRICO"])
        # Não repetir o nome se já constar do extrato.
        suffix=(f" | {name}" if name and normalize(name) not in normalize(existing) else "")
        if nf and nf.lower()!="nan":suffix+=f" | NF: {nf}"
        result.at[idx,"HISTÓRICO"]=existing+suffix
        # Consumo um único registro para não relacionar uma NF a outro
        # lançamento bancário repetido de mesmo valor e data.
        lookups[key]=[]
    return result

READERS={"bradesco":read_bradesco,"santander":read_santander}

def workflow_113(roles,options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    finance=roles.get("financeiro") or []
    if len(finance)>1:raise ValueError("Leravi: envie somente uma planilha financeira.")
    content=finance[0][1] if finance else None
    sheets={}
    for key,label in (("bradesco","Bradesco"),("santander","Santander")):
        uploads=roles.get(key) or []
        if not uploads:continue
        if len(uploads)!=1:raise ValueError(f"Leravi: envie um extrato mensal {label}.")
        filename,data=uploads[0]
        if not filename.lower().endswith(".pdf"):raise ValueError(f"Leravi: extrato {label} deve ser PDF.")
        result=filter_frame(READERS[key](data),options)
        if result.empty:continue
        if content:result=enrich_financial(result,content)
        sheets[label]=result.sort_values("DATA",kind="stable")
    if not sheets:raise ValueError("Leravi: envie extrato bancário da competência correta.")
    return gerar_modelo_abas(sheets,date_format="dd/mm/yyyy"),"LERAVI_113_MODELO_DOMINIO.xlsx"

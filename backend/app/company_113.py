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

BANK_HISTORY_PREFIXES = (
    "PAGTO ", "PAGAMENTO ", "PIX ", "RENTAB.", "TRANSF ", "TRANSF.",
    "TED", "DOC ", "DOC/TED", "TARIFA ", "IOF ",
    "CONTA DE TELEFONE", "TITULO DE CAPITALIZACAO",
)


def is_bank_history_heading(text):
    """Reconhece títulos efetivamente impressos no extrato Bradesco da Leravi."""
    return normalize(text).startswith(BANK_HISTORY_PREFIXES)


def verify_bradesco_account(header):
    """Confirma agência/conta como par, independentemente das quebras do PDF.

    Este extrato coloca 'Ag: | CC:' numa linha, '1154' e '0165499-3'
    na linha seguinte e repete '01154 | 0165499-3' no resumo.
    Exigir ambos juntos impede aceitar números encontrados isoladamente.
    """
    normalized = " ".join(str(header or "").split())
    if not re.search(r"Extrato\s+de:\s*Ag:", normalized, re.I):
        return False
    expected_account = r"0*165499\s*-\s*3"
    expected_agency = r"0*1154"
    # Resumo 'Agência | Conta': extratos com linha em ordem normal.
    summary = re.search(
        rf"(?<!\d){expected_agency}\s*\|\s*{expected_account}(?!\d)",
        normalized, re.I,
    )
    # Cabeçalho do extrato com campos dispostos em mais de uma linha.
    header_pair = re.search(
        rf"(?<!\d){expected_agency}\s+{expected_account}\s*\|\s*Entre",
        normalized, re.I,
    )
    return bool(summary or header_pair)


def _word_y(word):
    return (word[1] + word[3]) / 2


def read_bradesco(content):
    """Bradesco 113: usar extração estável em colunas do extrato."""
    from app.company_113_bradesco import read_statement
    return read_statement(content, verify_bradesco_account)


def read_santander(content):
    """Extrato consolidado Santander 513, competência identificada pelo PDF."""
    from app.company_113_santander import read_statement
    return read_statement(content)


def _bank_label(value):
    """Vincula registros financeiros ao banco do lançamento, nunca a outro."""
    name=normalize(value)
    if "BRADESCO" in name:
        return "bradesco"
    if "SANTANDER" in name:
        return "santander"
    return None


def _financial_description(value):
    """Preserva a descrição livre, sem repetir a nota já exibida como NF."""
    if pd.isna(value):
        return ""
    return clean(str(value)).strip()


def _invoice(value):
    if pd.isna(value):
        return ""
    # Excel frequentemente armazena a NF como 12345.0.
    if isinstance(value,(int,float)) and float(value).is_integer():
        return str(int(value))
    return clean(str(value)).strip()


def enrich_financial(frame_data,excel_bytes):
    """Extrato define data/valor/sinal; financeiro complementa o histórico.

    Banco, data exata, valor e natureza devem coincidir de modo unívoco.
    Casos ambíguos permanecem com histórico bancário intacto.
    """
    if not excel_bytes:
        return frame_data
    try:
        finance=pd.read_excel(BytesIO(excel_bytes),sheet_name=0)
    except Exception as exc:
        raise ValueError("Leravi: planilha financeira ilegível.") from exc
    required={"Tipo","Nome Fantasia","Descrição","Nota Fiscal",
              "Valor Pago","Data Pagto.","Banco"}
    if not required.issubset(finance.columns):
        missing=", ".join(sorted(required.difference(finance.columns)))
        raise ValueError(f"Leravi: colunas ausentes na planilha financeira: {missing}.")
    lookups=defaultdict(list)
    for _,item in finance.iterrows():
        bank=_bank_label(item.get("Banco"))
        if bank is None:
            continue
        paid=pd.to_numeric(item.get("Valor Pago"),errors="coerce")
        date_value=item.get("Data Pagto.")
        if isinstance(date_value,(int,float)) and not isinstance(date_value,bool):
            day=pd.to_datetime(date_value,errors="coerce",
                               origin="1899-12-30",unit="D")
        else:
            day=pd.to_datetime(date_value,dayfirst=True,errors="coerce")
        if pd.isna(paid) or pd.isna(day) or not paid:
            continue
        kind=normalize(item.get("Tipo"))
        sign=-1 if kind=="PAGAR" else 1 if kind=="RECEBER" else 0
        if not sign:
            continue
        value=int(round(abs(float(paid))*100))*sign
        key=(bank,day.date(),value)
        lookups[key].append({
            "name":clean(item.get("Nome Fantasia")) if pd.notna(item.get("Nome Fantasia")) else "",
            "description":_financial_description(item.get("Descrição")),
            "invoice":_invoice(item.get("Nota Fiscal")),
            "document":clean(item.get("Documento")) if pd.notna(item.get("Documento")) else "",
        })

    output=frame_data.copy()
    keys=[]
    for _,record in output.iterrows():
        keys.append((_bank_label(record["DESCRIÇÃO"]),
                     pd.Timestamp(record["DATA"]).date(),
                     int(round(float(record["VALOR"])*100))))
    bank_counts=defaultdict(int)
    for key in keys:
        bank_counts[key]+=1
    for (idx,record),key in zip(output.iterrows(),keys):
        # Não atribuir automaticamente uma NF a pagamentos iguais repetidos.
        matches=lookups.get(key,[])
        if bank_counts[key]!=1 or len(matches)!=1:
            continue
        match=matches[0]
        if not (match["name"] or match["description"]):
            continue
        original=str(record["HISTÓRICO"])
        base=("Recebido: " if key[2]>0 else "Pago: ")
        parts=[]
        if match["name"]:
            parts.append(match["name"])
        description=match["description"]
        invoice=match["invoice"]
        # Descrições geradas automaticamente, como 'Título gerado sobre
        # a NF: 2396', não acrescentam informação ao campo NF.
        if description and not re.fullmatch(
            r"T[íi]tulo gerado sobre a NF:\s*[\w./-]+",
            description,flags=re.IGNORECASE):
            if normalize(description) not in {normalize(x) for x in parts}:
                parts.append(description)
        if invoice:
            parts.append(f"NF: {invoice}")
        if not parts:
            continue
        # Histórico bancário permanece disponível para rastreabilidade,
        # seguido dos dados efetivamente fornecidos pelo financeiro.
        existing=original[len(base):] if original.startswith(base) else original
        extra=" | ".join(parts)
        output.at[idx,"HISTÓRICO"]=base + existing + " | " + extra
    return output

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

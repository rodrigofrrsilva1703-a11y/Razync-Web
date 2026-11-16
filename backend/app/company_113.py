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
    """Lê linhas por valor+saldo, não pelo cabeçalho quebrado em colunas.

    O extrato da Leravi continua na página seguinte sem repetir a data e
    inclui operações de 01/09 após agosto. Todos os movimentos do quadro
    principal são conferidos com saldo acumulado e totalizador; somente
    agosto é exportado.
    """
    with _pdf(content, "Bradesco") as doc:
        if not verify_bradesco_account(doc[0].get_text()):
            raise ValueError(
                "Leravi Bradesco: agência/conta não correspondem ao extrato "
                "cadastrado ou cabeçalho bancário ilegível."
            )
        rows = []
        opening = running = totals = current_day = None
        for page in doc:
            words = page.get_text("words", sort=True)
            amount_words = sorted(
                (w for w in words if 335 <= w[0] < 520 and MONEY.fullmatch(w[4])),
                key=_word_y,
            )
            balance_words = sorted(
                (w for w in words if w[0] >= 525 and MONEY.fullmatch(w[4])),
                key=_word_y,
            )
            date_words = sorted(
                (w for w in words if w[0] < 86 and DATE.fullmatch(w[4])),
                key=_word_y,
            )
            for balance in balance_words:
                y = _word_y(balance)
                near_words = sorted(
                    (w for w in words if 39 <= w[0] < 260
                     and abs(_word_y(w) - y) <= 7.2),
                    key=lambda w: (round(_word_y(w) / 3), w[0]),
                )
                history = " ".join(w[4] for w in near_words if w[0] >= 99)
                day_matches = [w for w in date_words if abs(_word_y(w)-y) <= 6.4]
                if len(day_matches) > 1:
                    raise ValueError("Leravi Bradesco: datas ambíguas no extrato.")
                if day_matches:
                    current_day = datetime.strptime(day_matches[0][4], "%d/%m/%Y").date()
                value_words = [w for w in amount_words if abs(_word_y(w)-y) <= 2.8]
                if (len(value_words) == 2 and any(
                    w[4].casefold() == "total" for w in near_words
                )):
                    totals = (
                        cents(value_words[0][4]),
                        cents(value_words[1][4]),
                        cents(balance[4]),
                    )
                    break
                if not value_words:
                    if "SALDO ANTERIOR" in history.upper():
                        if opening is not None or rows:
                            raise ValueError("Leravi Bradesco: saldo anterior repetido.")
                        opening = running = cents(balance[4])
                    continue
                if len(value_words) != 1:
                    raise ValueError("Leravi Bradesco: lançamento com valor ambíguo.")
                if running is None or current_day is None:
                    raise ValueError("Leravi Bradesco: saldo inicial ou data ausente.")
                value = cents(value_words[0][4])
                if value == 0 or not history:
                    raise ValueError("Leravi Bradesco: valor ou histórico incompleto.")
                running += value
                if running != cents(balance[4]):
                    raise ValueError(
                        f"Leravi Bradesco: saldo divergente em "
                        f"{current_day:%d/%m/%Y}."
                    )
                rows.append({
                    "date": current_day,
                    "value": value,
                    "history": history,
                })
            if totals is not None:
                break
        if opening is None or not rows or totals is None:
            raise ValueError(
                "Leravi Bradesco: saldo inicial, lançamentos ou totais ausentes."
            )
        credits = sum(max(row["value"], 0) for row in rows)
        debits = sum(min(row["value"], 0) for row in rows)
        if (credits, debits, running) != totals:
            raise ValueError(
                "Leravi Bradesco: total de créditos, débitos ou saldo final "
                "divergente do PDF."
            )
        august = [row for row in rows
                  if row["date"].year == 2026 and row["date"].month == 8]
        if not august:
            raise ValueError("Leravi Bradesco: nenhum lançamento em agosto/2026.")
        return frame(august, "BANCO BRADESCO", "9")

def read_santander(content):
    """Extrato consolidado Santander 513, competência identificada pelo PDF."""
    from app.company_113_santander import read_statement
    return read_statement(content)


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
    bank_counts=defaultdict(int)
    for _,row in result.iterrows():
        bank_key=(pd.Timestamp(row["DATA"]).date(),round(float(row["VALOR"])*100))
        bank_counts[bank_key]+=1
    for idx,record in result.iterrows():
        key=(pd.Timestamp(record["DATA"]).date(),round(float(record["VALOR"])*100))
        if bank_counts[key]!=1:
            continue
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

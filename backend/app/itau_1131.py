"""Empresa 1131 — extrato Itaú de conta 0074/0099705-7, auxiliar em PDF.

Somente o extrato estabelece lançamentos, datas e valores.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
import re
import unicodedata

import fitz
import pandas as pd

MONEY = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}$")
FULL_DATE = re.compile(r"^\d{2}/\d{2}/20\d{2}$")
SHORT_DATE = re.compile(r"^(\d{2})/([a-zç]{3})$", re.I)
MONTHS = {"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,
          "jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}
COLUNAS = ["DESCRIÇÃO","DATA","VALOR","DÉBITO","CRÉDITO","HISTÓRICO"]


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _cents(value):
    return int(Decimal(str(value).replace(".","").replace(",","."))*100)


def _words_at(words, center, xmin=0, xmax=999, tolerance=4.9):
    return sorted([w for w in words if xmin <= w[0] < xmax and
                   abs((w[1]+w[3])/2-center) < tolerance], key=lambda w:w[0])


def _text(words):
    return " ".join(w[4] for w in words).strip()


def _pdf(content, label):
    if not content.startswith(b"%PDF") or len(content) > 20*1024*1024:
        raise ValueError(f"{label}: envie um PDF válido, com até 20 MB.")
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"{label}: não foi possível abrir o PDF.") from exc
    if not 1 <= len(document) <= 20:
        document.close()
        raise ValueError(f"{label}: número inválido de páginas.")
    return document


def read_bank(content):
    doc = _pdf(content, "Extrato Itaú 1131")
    try:
        first = doc[0].get_text()
        if not (re.search(r"COTAS\s*PREMIADAS",first,re.I) and
                re.search(r"Agência\s*0074\s+Conta\s*0099705-7",first,re.I)):
            raise ValueError("Extrato Itaú não corresponde à empresa 1131, agência 0074, conta 0099705-7.")
        period = re.search(r"Lançamentos do período:\s*(\d{2}/\d{2}/20\d{2})\s+até\s+(\d{2}/\d{2}/20\d{2})", first)
        if not period:
            raise ValueError("Período bancário do Itaú não encontrado.")
        start = date.fromisoformat("-".join(reversed(period[1].split("/"))))
        end = date.fromisoformat("-".join(reversed(period[2].split("/"))))
        if (start.year,start.month)!=(end.year,end.month) or start>end:
            raise ValueError("Extrato Itaú precisa conter uma competência mensal.")
        records = []
        opening = closing = None
        balance_checks = []
        for page in doc:
            words = page.get_text("words", sort=True)
            for date_word in words:
                if date_word[0] > 85 or not FULL_DATE.fullmatch(date_word[4]):
                    continue
                y = (date_word[1]+date_word[3])/2
                line = _words_at(words,y,86,600)
                description = _text([w for w in line if w[0] < 360])
                money = [w for w in line if w[0] > 445 and MONEY.fullmatch(w[4])]
                if not money:
                    continue
                day = date.fromisoformat("-".join(reversed(date_word[4].split("/"))))
                value = _cents(money[-1][4])
                desc_norm = _norm(description)
                if "saldo anterior" in desc_norm:
                    opening = value
                    continue
                if "saldo total disponivel dia" in desc_norm or "saldo em conta corrente" in desc_norm:
                    if "saldo em conta corrente" in desc_norm:
                        closing = value
                    else:
                        balance_checks.append((day,value,len(records)))
                    continue
                if not start <= day <= end:
                    continue
                if not description:
                    # TED dividida em várias linhas: a descrição fica acima da
                    # linha que contém a data e o valor.
                    previous = [w for w in words if 88 < w[0] < 351 and
                                0 < y-(w[1]+w[3])/2 <= 12]
                    previous_text = _text(sorted(previous,key=lambda w:w[0]))
                    description = previous_text or "TRANSFERÊNCIA RECEBIDA"
                if value == 0:
                    continue
                # Históricos devem conter o evento e não identificadores pessoais.
                description = re.sub(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", "", description)
                description = re.sub(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", "", description)
                description = " ".join(description.split())
                records.append((day, value, description))
        if not records or opening is None or closing is None:
            raise ValueError("Extrato Itaú incompleto: movimentos ou saldos ausentes.")
        running = opening
        previous_checked = 0
        for _, balance, count in balance_checks:
            running += sum(row[1] for row in records[previous_checked:count])
            if running != balance:
                raise ValueError("Saldo diário do extrato Itaú não confere; leitura interrompida.")
            previous_checked = count
        running += sum(row[1] for row in records[previous_checked:])
        if running != closing:
            raise ValueError("Saldo final do extrato Itaú não confere; leitura interrompida.")
        frame = pd.DataFrame([{
            "DESCRIÇÃO":"BANCO ITAÚ","DATA":pd.Timestamp(day),
            "VALOR":value/100,
            "DÉBITO":"508" if value>0 else "",
            "CRÉDITO":"508" if value<0 else "",
            "HISTÓRICO":("Recebido: " if value>0 else "Pago: ")+history,
        } for day,value,history in records],columns=COLUNAS)
        return frame, (start.year,start.month)
    finally:
        doc.close()


def read_auxiliary(content, period):
    doc = _pdf(content,"Documento auxiliar 1131")
    year, month = period
    rows = []
    try:
        for page in doc:
            words = page.get_text("words", sort=True)
            # O resumo inicial "01/ago Saldo Reiscon" não é movimentação.
            # Somente as linhas abaixo do cabeçalho Data/Descrição/Débito/Crédito.
            header_y = [
                (w[1]+w[3])/2 for w in words
                if w[0] < 145 and _norm(w[4]) == "data"
            ]
            if not header_y:
                raise ValueError("Documento auxiliar sem cabeçalho da tabela de lançamentos.")
            start_y = min(header_y) + 10
            for date_word in words:
                y = (date_word[1]+date_word[3])/2
                if date_word[0] > 135 or y < start_y:
                    continue
                date_match = SHORT_DATE.fullmatch(_norm(date_word[4]))
                if not date_match or MONTHS.get(date_match[2]) != month:
                    continue
                day = date(year,month,int(date_match[1]))
                y = (date_word[1]+date_word[3])/2
                desc = _text(_words_at(words,y,140,393,6.0))
                debit = [w[4] for w in _words_at(words,y,395,493,6.0) if MONEY.fullmatch(w[4])]
                credit = [w[4] for w in _words_at(words,y,495,620,6.0) if MONEY.fullmatch(w[4])]
                if len(debit)!=1 or len(credit)!=1 or not desc:
                    raise ValueError(f"Documento auxiliar: linha de {date_word[4]} incompleta.")
                outgoing, incoming = _cents(debit[0]), _cents(credit[0])
                if outgoing and incoming:
                    raise ValueError("Documento auxiliar informa débito e crédito na mesma linha.")
                value = incoming-outgoing
                if value:
                    rows.append({"date":day,"cents":value,"history":desc.strip()})
    finally:
        doc.close()
    if not rows:
        raise ValueError("Documento auxiliar sem lançamentos reconhecidos para a competência.")
    return rows


def enrich(statement, auxiliary):
    bank, period = read_bank(statement)
    ledger = read_auxiliary(auxiliary,period)
    original = bank.copy(deep=True)
    by_bank, by_ledger = defaultdict(list), defaultdict(list)
    for i,row in bank.iterrows():
        key = (pd.Timestamp(row["DATA"]).date(),int(round(float(row["VALOR"])*100)))
        by_bank[key].append(i)
    for i,row in enumerate(ledger):
        by_ledger[(row["date"],row["cents"])].append(i)
    used_bank, used_aux, audit = set(), set(), []

    def replace(bank_id, aux_id, rule):
        candidate = ledger[aux_id]
        amount = candidate["cents"]
        history = re.sub(r"^(?:Pago|Recebido)\s*:\s*","",candidate["history"],flags=re.I).strip()
        if not history:
            return
        bank.at[bank_id,"HISTÓRICO"] = ("Recebido: " if amount>0 else "Pago: ")+history
        used_bank.add(bank_id)
        used_aux.add(aux_id)
        audit.append({"DATA EXTRATO":bank.at[bank_id,"DATA"],"VALOR":amount/100,
                      "HISTÓRICO AUXILIAR":history,"STATUS":rule,
                      "DATA AUXILIAR":str(candidate["date"])})

    for key in sorted(by_ledger):
        b, a = by_bank.get(key,[]),by_ledger[key]
        if len(b)==1 and len(a)==1:
            replace(b[0],a[0],"Correspondência exata")
        elif b and a:
            for idx in a:
                audit.append({"DATA EXTRATO":pd.NaT,"VALOR":key[1]/100,
                              "HISTÓRICO AUXILIAR":ledger[idx]["history"],
                              "STATUS":"Valor/data repetidos: revisão necessária",
                              "DATA AUXILIAR":str(ledger[idx]["date"])})
    # Tolerância de 1 dia apenas quando o valor aparece uma única vez em cada
    # documento, em todo o período. Não usar sequência da planilha.
    from collections import Counter
    bank_freq = Counter(int(round(float(v)*100)) for v in original["VALOR"])
    aux_freq = Counter(item["cents"] for item in ledger)
    for idx,item in enumerate(ledger):
        if idx in used_aux:
            continue
        value = item["cents"]
        if bank_freq[value]!=1 or aux_freq[value]!=1:
            continue
        matches = [bi for bi,row in original.iterrows() if bi not in used_bank and
                   int(round(float(row["VALOR"])*100))==value and
                   abs((pd.Timestamp(row["DATA"]).date()-item["date"]).days)==1]
        if len(matches)==1:
            replace(matches[0],idx,"Data auxiliar ±1 dia; valor único")
    for idx,item in enumerate(ledger):
        if idx not in used_aux and not any(a.get("DATA AUXILIAR")==str(item["date"]) and
                                              a.get("HISTÓRICO AUXILIAR")==item["history"] and
                                              "revisão" in a.get("STATUS","") for a in audit):
            audit.append({"DATA EXTRATO":pd.NaT,"VALOR":item["cents"]/100,
                          "HISTÓRICO AUXILIAR":item["history"],
                          "STATUS":"Sem vínculo seguro", "DATA AUXILIAR":str(item["date"])})
    for column in ("DATA","VALOR","DÉBITO","CRÉDITO"):
        if bank[column].tolist()!=original[column].tolist():
            raise AssertionError(f"Coluna bancária {column} modificada indevidamente.")
    if len(bank)!=len(original):
        raise AssertionError("Quantidade de lançamentos bancários alterada.")
    return bank,pd.DataFrame(audit)


def workflow_1131(roles,options):
    from app.excel import gerar_modelo_abas
    from app.advanced import append_dataframe_sheets
    from app.migration_services import filter_frame
    extracts = roles.get("extrato") or []
    supporting = roles.get("auxiliar") or []
    if len(extracts)!=1 or len(supporting)!=1:
        raise ValueError("Envie um extrato Itaú PDF e um documento auxiliar PDF da mesma competência.")
    if not extracts[0][0].lower().endswith(".pdf") or not supporting[0][0].lower().endswith(".pdf"):
        raise ValueError("Os dois documentos da empresa 1131 devem ser PDF.")
    frame,audit = enrich(extracts[0][1],supporting[0][1])
    filtered = filter_frame(frame,options)
    if filtered.empty:
        raise ValueError("Nenhuma movimentação Itaú na competência selecionada.")
    workbook = gerar_modelo_abas({"Itaú":filtered},date_format="dd/mm/yyyy")
    if not audit.empty:
        # A auditoria usa DATA EXTRATO, mas mantém registros sem vínculo para revisão.
        workbook = append_dataframe_sheets(workbook,{"Identificações 1131":audit})
    return workbook,"EMPRESA_1131_ITAU_MODELO_DOMINIO.xlsx"

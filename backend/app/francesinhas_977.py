"""Replace Bradesco collection credits with validated VIMAN settlement details."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile

import pandas as pd
import pdfplumber

from app.santander_consolidado_1522 import lines

MONEY = re.compile(r"\d[\d.]*,\d{2}")
REPORT_ACCOUNT = re.compile(r"Agencia:\s*(\d+)\s*/\s*Conta:\s*(\d+)\s*/\s*(\d+)", re.I)
STATEMENT_ACCOUNT = re.compile(r"Extrato de:\s*Ag:\s*(\d+)\s*\|\s*CC:\s*(\d+)\s*-\s*(\d+)", re.I)
COLLECTION = re.compile(r"^(?:Recebido:\s*)?LIQUIDA[CÇ][AÃ]O DE COBRAN[CÇ]A(?=\b|VALOR DISPON[IÍ]VEL)", re.I)
LIMIT = 50 * 1024 * 1024


def _cents(value):
    return int(Decimal(value.replace(".", "").replace(",", ".")) * 100)


def _account(pattern, text):
    found = pattern.search(text)
    return tuple(map(int, found.groups())) if found else None


def _report(pdf):
    settlements = []
    batch = []
    active = False
    headers = {}
    with pdfplumber.open(BytesIO(pdf)) as document:
        text = "\n".join(page.extract_text() or "" for page in document.pages)
        identity = _account(REPORT_ACCOUNT, text)
        if not identity or not re.search(r"LISTA DA MOVIMENTACAO DE RETORNO DE COBRANCA\s+Bradesco", text, re.I):
            raise ValueError("O PDF do ZIP precisa ser um retorno de cobrança VIMAN do Bradesco.")
        for page in document.pages:
            for row in lines(page.extract_words()):
                tokens = [word["text"] for word in row]
                joined = " ".join(tokens)
                if joined.startswith("RESUMO DA MOVIMENTACAO"):
                    if active:
                        raise ValueError("Faltou o subtotal de uma liquidação na francesinha.")
                    break
                if "Vr.recebido" in tokens:
                    headers = {word["text"]: word for word in row}
                if tokens[:2] == ["06-LIQUIDACAO", "NORMAL"]:
                    if active:
                        raise ValueError("Faltou o subtotal de uma liquidação na francesinha.")
                    active = True
                    batch = []
                    continue
                if not active or tokens[0] != "|":
                    continue
                if "Vr.recebido" in tokens or "Ocorrencia:" in tokens or "Observacao:" in tokens:
                    continue
                if not {"Vr.recebido", "Dt.cred.", "Agenc", "-----------Sacado-----------"} <= headers.keys():
                    raise ValueError("Colunas de liquidação ausentes na francesinha.")
                received = [word["text"] for word in row
                            if abs(word["x1"] - headers["Vr.recebido"]["x1"]) < 3 and MONEY.fullmatch(word["text"])]
                if len(received) != 1:
                    raise ValueError("Valor recebido ausente ou ambíguo na liquidação da francesinha.")
                value = _cents(received[0])
                if joined.startswith("| Sub-total"):
                    count = re.search(r"\(\s*(\d+)\s*\)", joined)
                    if not count or int(count[1]) != len(batch) or value != sum(item[2] for item in batch):
                        raise ValueError("O subtotal da francesinha diverge dos títulos lidos.")
                    for day in dict.fromkeys(item[0] for item in batch):
                        settlements.append((identity, day, tuple(item[1:] for item in batch if item[0] == day)))
                    active = False
                    continue
                date = [word["text"] for word in row
                        if abs(word["x0"] - headers["Dt.cred."]["x0"]) < 3]
                payer = " ".join(word["text"] for word in row
                                 if word["x0"] < headers["Agenc"]["x0"] - 2
                                 and word["x0"] >= headers["-----------Sacado-----------"]["x0"] - 2)
                if len(date) != 1 or not payer.strip("? ") or value <= 0:
                    raise ValueError("Título liquidado sem data de crédito, sacado ou valor válido.")
                day = datetime.strptime(date[0], "%d/%m/%y").date()
                batch.append((day, tokens[2], value, payer, tokens[1]))
    if active:
        raise ValueError("Faltou o subtotal de uma liquidação na francesinha.")
    return identity, settlements


def read_zip(content):
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = [entry for entry in archive.infolist()
                       if not entry.is_dir() and entry.filename.lower().endswith(".pdf")
                       and not entry.filename.startswith("__MACOSX/")]
            if not entries or len(entries) > 150 or sum(entry.file_size for entry in entries) > LIMIT:
                raise ValueError("Envie um ZIP com até 150 PDFs de francesinhas, somando até 50 MB.")
            accounts, groups = set(), set()
            for entry in entries:
                identity, settlements = _report(archive.read(entry))
                accounts.add(identity)
                groups.update(settlements)
    except (BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError("Não foi possível abrir o ZIP das francesinhas.") from exc
    return accounts, groups


def read_bradesco(content):
    from app.engine import PdfReader, processar_pdf_bradesco_mensal

    reader = PdfReader(BytesIO(content), strict=False)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    identity = _account(STATEMENT_ACCOUNT, text)
    period = re.search(r"Entre\s+(\d{2}/\d{2}/\d{4})\s+e\s+(\d{2}/\d{2}/\d{4})", text, re.I)
    totals = re.search(r"(?m)^\s*Total\s+([\d.]+,\d{2})\s+-([\d.]+,\d{2})\s+", text)
    if not identity or not period or not totals:
        raise ValueError("Agência, conta, período ou totais não encontrados no extrato mensal Bradesco.")
    start, end = [datetime.strptime(value, "%d/%m/%Y") for value in period.groups()]
    rows = [row for row in processar_pdf_bradesco_mensal(reader) if start <= row["DATA"] <= end]
    values = [round(Decimal(str(row["VALOR"])) * 100) for row in rows]
    if not rows or (sum(v for v in values if v > 0), -sum(v for v in values if v < 0)) != tuple(map(_cents, totals.groups())):
        raise ValueError("Os lançamentos do período não conferem com os totais do extrato Bradesco.")
    return pd.DataFrame(rows), identity


def bank_frames(bank, uploads, zip_uploads=()):
    from app.bb_consultas import ler_extrato_bb_consultas

    if len({content for _, content in uploads}) != len(uploads):
        raise ValueError("O mesmo extrato foi enviado mais de uma vez.")
    if bank == "banco_brasil":
        if zip_uploads:
            raise ValueError("Envie o ZIP no campo do Bradesco.")
        return pd.concat([pd.DataFrame(ler_extrato_bb_consultas(content)) for _, content in uploads], ignore_index=True)
    if bank != "bradesco":
        raise ValueError("Banco indisponível para a empresa 977.")
    if len(zip_uploads) > 1:
        raise ValueError("Envie somente um ZIP com as francesinhas do período.")
    statements = defaultdict(list)
    for _, content in uploads:
        frame, identity = read_bradesco(content)
        statements[identity].append(frame)
    accounts, groups = read_zip(zip_uploads[0][1]) if zip_uploads else (set(), set())
    if accounts - statements.keys():
        raise ValueError("A agência e a conta das francesinhas precisam corresponder ao extrato Bradesco.")
    frames = [expand(pd.concat(parts, ignore_index=True), identity, groups) for identity, parts in statements.items()]
    return pd.concat(frames, ignore_index=True)


def expand(frame, identity, groups):
    candidates = defaultdict(list)
    for account, day, items in groups:
        if account == identity:
            candidates[(day, sum(item[1] for item in items))].append(items)
    keys = defaultdict(list)
    records = frame.to_dict("records")
    for index, row in enumerate(records):
        if row["VALOR"] > 0 and COLLECTION.match(row["HISTÓRICO"]):
            day = pd.to_datetime(row["DATA"], dayfirst=True).date()
            cents = round(Decimal(str(row["VALOR"])) * 100)
            keys[(day, cents)].append(index)
    replacements = {}
    for key, indices in keys.items():
        matches = candidates.get(key, [])
        if len(indices) == len(matches) == 1:
            replacements[indices[0]] = matches[0]
    result = []
    for index, row in enumerate(records):
        if index in replacements:
            result.extend({**row, "VALOR": value / 100,
                           "HISTÓRICO": f"Recebido: {payer} - Título {title}"}
                          for _, value, payer, title in replacements[index])
        else:
            result.append(row)
    return pd.DataFrame(result, columns=frame.columns)

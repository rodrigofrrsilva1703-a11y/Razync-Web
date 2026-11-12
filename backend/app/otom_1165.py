"""Organize the Otom monthly workbook by bank and card liability."""
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
import re
import unicodedata

import pandas as pd
from openpyxl import load_workbook

from app.excel import gerar_modelo_abas
from app.registry import CAPABILITIES

BANKS = {"bco itau": ("itau", "Itaú"), "nubank": ("nubank", "Nubank"), "bco cef": ("caixa", "Caixa")}
CARD = "Cartão de Crédito"
COLUMNS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value or "").casefold())
                   if not unicodedata.combining(c)).strip()


def competence(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", value):
        raise ValueError("Informe o mês e o ano da competência.")
    year, month = map(int, value.split("-"))
    if not 1900 <= year <= 9999:
        raise ValueError("Informe um ano válido para a competência.")
    return date(year, month, monthrange(year, month)[1])


def cell_text(cell):
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, (int, float)) and int(value) == value:
        width = len(cell.number_format) if re.fullmatch(r"0+", cell.number_format) else 0
        return str(int(value)).zfill(width)
    return " ".join(str(value).split())


def sheet_rows(sheet):
    rows = sheet.iter_rows(min_row=3, max_col=5)
    header = [normalized(cell.value) for cell in next(rows, ())]
    if (len(header) != 5 or header[0] != "data" or "fornecedor" not in header[1]
            or header[2:] != ["tipo de documento", "no doc.", "valor (r$)"]):
        raise ValueError(f"Colunas da aba {sheet.title} não reconhecidas.")
    for cells in rows:
        when, supplier, kind, document, amount = cells
        if amount.value is None:
            continue
        try:
            raw = str(amount.value).strip()
            if "," in raw:
                raw = raw.replace(".", "").replace(",", ".")
            number = Decimal(raw)
            cents = int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError, OverflowError) as exc:
            raise ValueError(f"Valor inválido em {sheet.title}, linha {amount.row}.") from exc
        label = cell_text(supplier)
        if not cents or normalized(label) in {"saldo anterior", "saldo inicial", "saldo final", "total"}:
            continue
        day = when.value
        if isinstance(day, datetime):
            day = day.date()
        elif isinstance(day, str):
            try:
                day = datetime.strptime(day.strip(), "%d/%m/%Y").date()
            except ValueError:
                day = None
        if not isinstance(day, date) or not label:
            raise ValueError(f"Data ou histórico inválido em {sheet.title}, linha {amount.row}.")
        yield day, cents, label, cell_text(kind), cell_text(document)


def read_workbook(content):
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("Envie a planilha mensal da Otom em formato XLSX.") from exc
    banks, cards = {}, []
    try:
        for sheet in book.worksheets:
            title = normalized(sheet.title)
            if title in BANKS:
                key, _ = BANKS[title]
                banks[key] = list(sheet_rows(sheet))
            elif title.startswith("c.credito "):
                match = re.match(r"c\.credito\s+(itau|nubank)\b", title)
                if not match:
                    raise ValueError(f"Banco do cartão não reconhecido na aba {sheet.title}.")
                cards.extend((match[1], row) for row in sheet_rows(sheet))
    finally:
        book.close()
    if not banks:
        raise ValueError("Não encontrei as abas bancárias da planilha mensal da Otom.")
    return banks, cards


def movement(label, account, day, cents, history, counterpart=""):
    paid = cents < 0
    return (label, day, cents / 100, counterpart if paid else account,
            account if paid else counterpart, history)


FISCAL_DOCUMENTS = {
    "nf": "NF", "nota fiscal": "NF", "nfe": "NF-e", "nf-e": "NF-e",
    "nfse": "NFS-e", "nfs-e": "NFS-e", "danfe": "DANFE",
}


def bank_history(supplier, kind, document, cents):
    fiscal_type = FISCAL_DOCUMENTS.get(normalized(kind))
    history = f"{supplier} {fiscal_type} {document}" if fiscal_type and document else supplier
    return ("Pago: " if cents < 0 else "Recebido: ") + history


def bank_frame(bank, rows, transfers=()):
    label = next(name for key, name in BANKS.values() if key == bank)
    account = CAPABILITIES[1165]["banks"][bank]
    return pd.DataFrame([
        movement(label, account, day, cents, bank_history(supplier, kind, document, cents),
                 "581" if index in transfers else "")
        for index, (day, cents, supplier, kind, document) in enumerate(rows)
    ], columns=COLUMNS)


def statement(bank, content, filename):
    from app.company_1058 import read_caixa
    from app.company_1151 import read_itau, read_nubank

    if not filename.lower().endswith(".pdf"):
        raise ValueError("Empresa 1165: envie o extrato bancário em PDF.")
    if bank == "itau":
        return read_itau(content, holder=r"OTOM\s+ENGENHARIA", agency="1514", account="0053524-2")
    if bank == "nubank":
        return read_nubank(content, holder=r"OTOM\s+TECNOLOGIA\s+E\s+SERVI[CÇ]OS\s+LTDA",
                           account="761916503-5")
    if bank == "caixa":
        return read_caixa(content, holder="OTOM TECNOLOGIA E SERVICOS LTDA",
                          agency="7634", account="000579052579-9")
    raise ValueError("Banco não configurado para a empresa 1165.")


def workflow(roles, options):
    end = competence(options.get("competencia"))
    uploads = roles.get("movimento", [])
    if len(uploads) != 1 or not uploads[0][0].lower().endswith(".xlsx"):
        raise ValueError("Envie uma planilha mensal da Otom em XLSX.")
    banks, cards = read_workbook(uploads[0][1])
    start = end.replace(day=1)
    banks = {key: [row for row in rows if start <= row[0] <= end] for key, rows in banks.items()}
    if not any(banks.values()) and not any(start <= row[0] <= end for _, row in cards):
        raise ValueError("A competência selecionada não aparece nos lançamentos da planilha.")

    candidates = defaultdict(list)
    for bank, rows in banks.items():
        for index, (day, cents, supplier, kind, document) in enumerate(rows):
            if cents < 0 and re.match(r"^(?:pagto|pagamento)\s+cartao(?:\s+de)?\s+credito\b", normalized(supplier)):
                candidates[bank, day, -cents].append(index)
    transfers = defaultdict(set)
    card_rows = []
    for bank, (day, cents, supplier, kind, document) in cards:
        if normalized(supplier) in {"pagamento fatura", "pagamento de fatura", "pagamento da fatura"}:
            if not start <= day <= end:
                continue
            matches = candidates[bank, day, cents]
            if len(matches) != 1 or matches[0] in transfers[bank]:
                raise ValueError(f"Pagamento de fatura de {day:%d/%m/%Y} sem débito bancário único correspondente.")
            transfers[bank].add(matches[0])
            continue
        if day > end:
            raise ValueError("A planilha contém lançamento de cartão posterior à competência selecionada.")
        history = f"{supplier} NF {document}" if normalized(kind) == "nf" and document else supplier
        card_rows.append(movement(CARD, "581", end, cents, history))

    sheets = {
        label: bank_frame(bank, banks[bank], transfers[bank]).sort_values("DATA", kind="stable")
        for bank, label in BANKS.values() if banks.get(bank)
    }
    if card_rows:
        sheets[CARD] = pd.DataFrame(card_rows, columns=COLUMNS)
    return gerar_modelo_abas(sheets, date_format="dd/mm/yyyy"), f"OTOM_1165_{end:%Y-%m}_MODELO_DOMINIO.xlsx"

"""Extratos da RT Moto, com as duas contas BB na escrituração da matriz."""
import io
import re

import pandas as pd
from pypdf import PdfReader

from app.bb_consultas import ler_extrato_bb_consultas
from app.itau_1399 import PRIVATE, read_statement as read_itau
from app.registry import CAPABILITIES

BB_ACCOUNTS = {"240-2": "banco_brasil", "563-0": "bb_filial"}
LABELS = {"itau": "Itaú", "banco_brasil": "Banco do Brasil Matriz",
          "bb_filial": "Banco do Brasil Filial"}


def read_bb(content):
    if not content.startswith(b"%PDF") or len(content) > 25 * 1024 * 1024:
        raise ValueError("Envie um extrato Banco do Brasil em PDF de até 25 MB.")
    reader = PdfReader(io.BytesIO(content))
    if not 1 <= len(reader.pages) <= 50:
        raise ValueError("Envie o extrato Banco do Brasil completo, com até 50 páginas.")
    headers = [(page.extract_text() or "").split("Lançamentos", 1)[0] for page in reader.pages]
    accounts = {account for header in headers
                for account in re.findall(r"Conta\s+corrente\s*(\d+-\d)", header, re.I)}
    if len(accounts) != 1 or not accounts <= BB_ACCOUNTS.keys():
        raise ValueError("O extrato BB deve conter uma única conta corrente da RT Moto: 240-2 ou 563-0.")
    bank = BB_ACCOUNTS[accounts.pop()]
    account = CAPABILITIES[1130]["banks"][bank]
    frame = pd.DataFrame(ler_extrato_bb_consultas(
        content, preserve_columns=True, skip_blocked_deposits=True))
    frame["DESCRIÇÃO"] = LABELS[bank]
    incoming = frame["VALOR"] > 0
    frame.loc[incoming, "DÉBITO"] = account
    frame.loc[~incoming, "CRÉDITO"] = account
    frame["HISTÓRICO"] = [
        ("Recebido: " if credit else "Pago: ") + " ".join(PRIVATE.sub("", history).split())
        for credit, history in zip(incoming, frame["HISTÓRICO"])
    ]
    return bank, frame


def statement(bank, content, filename):
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Envie o extrato da RT Moto em PDF.")
    if bank == "itau":
        return read_itau(content, holder=r"RT\s+MOTO\s+PECAS\s+LTDA",
                         tax_id="37.866.525/0001-14", agency="7111", account="0030378-5",
                         include_blocked_balance=True)
    detected, frame = read_bb(content)
    if bank != detected:
        raise ValueError(f"O PDF pertence ao {LABELS[detected]}. Anexe no campo correspondente.")
    return frame


def workflow(roles, options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame

    groups = {}
    seen = set()
    for role in ("itau", "bb"):
        for filename, content in roles.get(role, []):
            if not filename.lower().endswith(".pdf"):
                raise ValueError("Envie os extratos da RT Moto em PDF.")
            bank, frame = ("itau", statement("itau", content, filename)) if role == "itau" else read_bb(content)
            keys = {(bank, month) for month in frame["DATA"].dt.to_period("M").unique()}
            if seen & keys:
                raise ValueError(f"Envie somente um extrato por competência para {LABELS[bank]}.")
            seen.update(keys)
            groups.setdefault(bank, []).append(frame)
    sheets = {}
    for bank, frames in groups.items():
        frame = filter_frame(pd.concat(frames, ignore_index=True), options)
        if not frame.empty:
            sheets[LABELS[bank]] = frame.sort_values("DATA", kind="stable")
    if not sheets:
        raise ValueError("Envie pelo menos um extrato com lançamentos no período selecionado.")
    return gerar_modelo_abas(sheets, date_format="dd/mm/yyyy"), "RT_MOTO_1130_MODELO_DOMINIO.xlsx"

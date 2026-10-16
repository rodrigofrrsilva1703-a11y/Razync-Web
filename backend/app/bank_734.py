"""BTG Pactual PJ da empresa 734: extrato Conta Corrente + Remunera+.

Extrai as linhas da coluna Entradas/Saídas, preserva o histórico multiline,
ignora somente os saldos e valida totais e saldo de abertura/fechamento.
A conta 510 é contábil; a agência e conta bancária não são presumidas.
"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import fitz
import pandas as pd

from app import engine

COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
ACCOUNT = "510"
SHEET = "BTG 510"
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_MONEY = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")


_CPF_LINE = re.compile(r"\s*\|?\s*CPF\s*[:\-]?\s*\*{0,3}[\d.*\- ]{5,20}", re.I)
_CPF_NUMBER = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)|(?<!\d)\d{11}(?!\d)")


def _clean_history(history: str) -> str:
    """Remove CPF completo ou mascarado sem apagar pessoa, banco ou mensagem."""
    history = _CPF_LINE.sub(" ", history)
    history = _CPF_NUMBER.sub(" ", history)
    history = re.sub(r"\s*\|\s*\|\s*", " | ", history)
    history = re.sub(r"\s*\|\s*$", "", history)
    return re.sub(r"\s+", " ", history).strip()



def _cents(value: str) -> int:
    amount = Decimal(value.replace(".", "").replace(",", "."))
    if not amount.is_finite():
        raise ValueError("BTG: valor monetário inválido.")
    return int(amount * 100)


def _parse_pdf(data: bytes):
    if not data.startswith(b"%PDF") or len(data) > 25 * 1024 * 1024:
        raise ValueError("BTG 510: envie o PDF original válido de até 25 MB.")
    try:
        document = fitz.open(stream=data, filetype="pdf")
        if not 0 < document.page_count <= 80:
            raise ValueError("BTG 510: extrato PDF vazio ou muito extenso.")
        pages = [page.get_text("text") for page in document]
        document.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("BTG 510: não foi possível abrir o extrato PDF.") from exc

    first = pages[0]
    classic = "Conta corrente - PJ" in first and "Período do extrato:" in first
    modern = "Extrato conta corrente" in first and "Entradas/Saídas" in first
    if not (classic or modern):
        raise ValueError("BTG 510: layout não reconhecido. Envie o extrato original do BTG.")
    if modern:
        begin = re.search(r"Saldo de abertura\s+\d{2}/\d{2}/\d{4}\s+R\$\s*([\d.,]+)", first)
        end = re.search(r"Saldo de fechamento\s+\d{2}/\d{2}/\d{4}\s+R\$\s*([\d.,]+)", first)
    else:
        begin = re.search(r"Saldo de abertura em \d{2}/\d{2}/\d{4}:\s*R\$\s*([\d.,]+)", first)
        end = re.search(r"Saldo de fechamento em \d{2}/\d{2}/\d{4}:\s*R\$\s*([\d.,]+)", first)
    entries = re.search(r"Total de entradas\s*R\$\s*([\d.,]+)", first)
    exits = re.search(r"Total de saídas\s*R\$\s*([\d.,]+)", first)
    if any(match is None for match in (begin, end, entries, exits)):
        raise ValueError("BTG 510: saldos ou totais do cabeçalho não foram identificados.")

    movements = []
    for page in pages:
        if modern:
            table = re.split(r"Entradas/Saídas\s+Saldo\s*", page, maxsplit=1)
            if len(table) != 2:
                raise ValueError("BTG 510: página sem tabela de movimentos.")
            body = table[1].split("Extrato conta corrente", 1)[0].split("Fale com nossa central", 1)[0]
        else:
            table = page.split("Data lançamento", 1)
            if len(table) != 2:
                raise ValueError("BTG 510: página sem a tabela de lançamentos.")
            body = table[1].split("Fale com nossa central", 1)[0]
        # As datas iniciam cada linha; descrição multiline fica dentro do grupo.
        current = None

        def consume(item):
            if item is None:
                return
            parts = item["parts"]
            if parts and parts[0].casefold().startswith(("saldo de abertura", "saldo de fechamento")):
                return
            if modern:
                # Modern PDF includes currency symbol and negative amounts.
                money = [(i, re.sub(r"\s*R\x24\s*", "", value).replace(" ", ""))
                         for i, value in enumerate(parts)
                         if re.fullmatch(r"-?\s*R\x24\s*[\d.,]+", value)]
                if len(money) > 2:
                    money = money[:2]
            else:
                money = [(i, value) for i, value in enumerate(parts) if _MONEY.fullmatch(value)]
            if len(money) != 2:
                raise ValueError(f"BTG 510: lançamento incompleto em {item['date']}.")
            value_index, value_text = money[0]
            saldo_index, _ = money[1]
            if saldo_index <= value_index:
                raise ValueError("BTG 510: colunas Valor e Saldo invertidas.")
            history = _clean_history(" ".join(parts[:value_index]).strip())
            if not history:
                raise ValueError("BTG 510: histórico vazio em lançamento.")
            value_cents = _cents(value_text)
            if not value_cents:
                return
            movements.append({
                "DESCRIÇÃO": "BANCO BTG",
                "DATA": datetime.strptime(item["date"], "%d/%m/%Y"),
                "VALOR": value_cents / 100,
                "DÉBITO": ACCOUNT if value_cents > 0 else "",
                "CRÉDITO": ACCOUNT if value_cents < 0 else "",
                "HISTÓRICO": history,
            })

        for raw in body.splitlines():
            line = raw.strip()
            if not line:
                continue
            if _DATE.fullmatch(line):
                consume(current)
                current = {"date": line, "parts": []}
            elif current is not None:
                # Modern PDF has two monetary columns with independent lines.
                # Keep complete history, including text split onto multiple rows.
                current["parts"].append(line)
        consume(current)

    if not movements:
        raise ValueError("BTG 510: nenhum lançamento encontrado.")
    total_in = sum(round(row["VALOR"] * 100) for row in movements if row["VALOR"] > 0)
    total_out = -sum(round(row["VALOR"] * 100) for row in movements if row["VALOR"] < 0)
    opening, closing = _cents(begin.group(1)), _cents(end.group(1))
    if (total_in != _cents(entries.group(1))
            or total_out != _cents(exits.group(1))
            or opening + total_in - total_out != closing):
        raise ValueError(
            "BTG 510: movimentos não conferem com entradas, saídas ou saldos do extrato. "
            "O arquivo pode estar incompleto ou ter outro layout."
        )
    return movements


_EXCLUDED_MOVEMENT = re.compile(
    r"^\s*(?:d[eé]bito|cr[eé]dito)\s+na\s+conta\s+corrente\b",
    re.IGNORECASE,
)


def _skip_current_account_transfer(history: str) -> bool:
    """Ignora as duas naturezas solicitadas sem afetar outros movimentos."""
    return bool(_EXCLUDED_MOVEMENT.match(history or ""))


def read_bank_pdf(bank: str, data: bytes, filename: str) -> pd.DataFrame:
    if bank != "btg":
        raise ValueError("Na empresa 734, por enquanto somente o BTG 510 está habilitado.")
    if not str(filename).lower().endswith(".pdf"):
        raise ValueError("BTG 510: envie o extrato original em PDF.")
    # O leitor valida TODOS os lançamentos contra os saldos do PDF antes de
    # retirar as naturezas que não devem ir para o Modelo Domínio.
    frame = pd.DataFrame(_parse_pdf(data), columns=COLUNAS)
    history = frame["HISTÓRICO"].fillna("").str.lower()
    skip = frame["HISTÓRICO"].map(_skip_current_account_transfer)
    skip |= history.str.contains("rendimento remunera", regex=False)
    skip |= history.str.contains("rendimentos remunerados", regex=False)
    frame = frame.loc[~skip].copy()
    history = frame["HISTÓRICO"].fillna("").str.lower()
    invert = history.str.startswith("aplicação conta remunerada") | history.str.startswith("resgate conta remunerada")
    frame.loc[invert, "VALOR"] = -frame.loc[invert, "VALOR"]
    frame["DÉBITO"] = frame["VALOR"].apply(lambda value: ACCOUNT if value > 0 else "")
    frame["CRÉDITO"] = frame["VALOR"].apply(lambda value: ACCOUNT if value < 0 else "")
    if frame.empty:
        raise ValueError("BTG 510: apenas movimentos de débito/crédito na conta corrente encontrados; nenhum lançamento para importar.")
    return frame.reset_index(drop=True)


def workflow_734(roles: dict, options: dict):
    from app.migration_services import filter_frame

    if any(name != "btg" and files for name, files in roles.items()):
        raise ValueError("A empresa 734 está configurada somente para o BTG neste momento.")
    files = roles.get("btg") or []
    if not files:
        raise ValueError("Envie ao menos um extrato BTG em PDF.")
    hashes = set()
    parts = []
    for filename, data in files:
        digest = hashlib.sha256(data).digest()
        if digest in hashes:
            raise ValueError("BTG 510: mesmo extrato enviado mais de uma vez.")
        hashes.add(digest)
        parts.append(read_bank_pdf("btg", data, filename))

    frame = filter_frame(pd.concat(parts, ignore_index=True), options)
    if frame.empty:
        raise ValueError("BTG 510: nenhum lançamento no período selecionado.")
    frame = frame.sort_values("DATA", kind="stable").reset_index(drop=True)
    book = engine.gerar_excel_nova_geracao({
        SHEET: {"principal": frame, "retirados": pd.DataFrame()}
    }, prefixar_historicos=True)
    return book, "RAZYNC_734_BTG_510_MODELO_DOMINIO.xlsx"

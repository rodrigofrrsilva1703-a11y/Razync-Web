"""Leitor do extrato BB 'Consultas - Extrato de conta corrente' da empresa 266.

A conta bancária é 200076-8, com conta contábil 8. O leitor usa a
coluna Valor R$ e o indicador C/D, nunca a coluna Documento ou Saldo.
Os saldos são conferidos em centavos; movimentos de 01/09 com data de
balancete de 31/08 permanecem em agosto.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from decimal import Decimal

from pypdf import PdfReader

CONTA_BANCARIA = "200076-8"
_MAX_BYTES = 25 * 1024 * 1024
_MONEY = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_DATE = r"\d{2}/\d{2}/\d{4}"
_ROW = re.compile(
    rf"^(?P<data>{_DATE})\s+(?:(?P<data_mov>{_DATE})\s+)?"
    rf"(?P<ag>\d{{4}})\s+(?P<lote>\d{{5}})\s+(?P<cod>\d{{3}})\s+"
    rf"(?P<historico>.*?)\s+(?P<documento>[\d.\-/]+)\s+"
    rf"(?P<valor>{_MONEY})\s*(?P<natureza>[CD])\s*$", re.I
)
_ROW_START = re.compile(rf"^{_DATE}\s")
_MONEY_END = re.compile(rf"(?P<valor>{_MONEY})\s*(?P<natureza>[CD])\s*$", re.I)
_ACCOUNT = re.compile(r"^Conta\s+corrente\s+(?P<conta>[\d.\-]+)", re.I | re.M)


def _cents(text: str, nature: str) -> int:
    amount = int(Decimal(text.replace(".", "").replace(",", ".")) * 100)
    return amount if nature.upper() == "C" else -amount


def parece_extrato_bb_consultas_266(content: bytes) -> bool:
    """Distingue este PDF dos layouts BB Autorizável e CRJ 47."""
    if not content or not content.startswith(b"%PDF"):
        return False
    try:
        text = PdfReader(io.BytesIO(content), strict=False).pages[0].extract_text() or ""
        return bool(re.search(r"Consultas\s*-\s*Extrato de conta corrente", text, re.I))
    except Exception:
        return False


def ler_extrato_bb_consultas_266(content: bytes) -> list[dict]:
    """Retorna lançamentos reais e falha se a conta ou saldo não fechar."""
    if not content or not content.startswith(b"%PDF") or len(content) > _MAX_BYTES:
        raise ValueError("Banco do Brasil 266: envie um PDF válido de até 25 MB.")
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if not reader.pages or len(reader.pages) > 50:
            raise ValueError("Banco do Brasil 266: PDF vazio ou com mais de 50 páginas.")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Não foi possível abrir o extrato PDF do Banco do Brasil.") from exc

    if not re.search(r"Consultas\s*-\s*Extrato de conta corrente", text, re.I):
        raise ValueError("Banco do Brasil 266: layout do extrato não reconhecido.")
    if not re.search(r"Dt\.\s*balancete\s*Dt\.\s*movimento", text, re.I):
        raise ValueError("Banco do Brasil 266: colunas do extrato não reconhecidas.")
    account = _ACCOUNT.search(text)
    if not account or re.sub(r"\D", "", account.group("conta")) != "2000768":
        raise ValueError("Banco do Brasil 266: extrato não pertence à conta 200076-8.")

    records = []
    opening = closing = None
    current = None
    in_table = False
    for original in text.splitlines():
        line = re.sub(r"\s+", " ", original).strip()
        if not line:
            continue
        if line == "Lançamentos":
            in_table = True
            current = None
            continue
        if not in_table:
            continue
        if line.startswith(("Dt. balancete", "Lançamentos")):
            current = None
            continue
        if line.startswith(("BB, sou eu", "Transação efetuada", "Central de Atendimento")):
            break
        if _ROW_START.match(line):
            if "Saldo Anterior" in line:
                match = _MONEY_END.search(line)
                if not match:
                    raise ValueError("Banco do Brasil 266: saldo inicial não reconhecido.")
                if opening is not None or records:
                    raise ValueError("Banco do Brasil 266: saldo inicial repetido ou fora de ordem.")
                opening = _cents(match.group("valor"), match.group("natureza"))
                current = None
                continue
            if re.search(r"S\s+A\s+L\s+D\s+O\s+", line, re.I):
                match = _MONEY_END.search(line)
                if not match:
                    raise ValueError("Banco do Brasil 266: saldo final não reconhecido.")
                closing = _cents(match.group("valor"), match.group("natureza"))
                current = None
                break
            match = _ROW.fullmatch(line)
            if not match:
                raise ValueError(
                    "Banco do Brasil 266: lançamento incompleto ou não reconhecido: " + line[:100]
                )
            date = datetime.strptime(match.group("data"), "%d/%m/%Y")
            cents = _cents(match.group("valor"), match.group("natureza"))
            history = match.group("historico").strip()
            document = match.group("documento")
            current = {
                "DESCRIÇÃO": "BANCO DO BRASIL", "DATA": date,
                "VALOR": cents / 100, "DÉBITO": "", "CRÉDITO": "",
                "HISTÓRICO": f"{history} (Doc. {document})",
            }
            records.append(current)
        elif current is not None:
            # O complemento da TED pertence ao lançamento anterior.
            if not line.startswith((
                "Saldo ", "Conta corrente", "Período do extrato",
                "Consultas -", "Cliente -", "Agência ",
                "Serviço de Atendimento", "Ouvidoria",
                "Para deficientes", "G338",
            )):
                current["HISTÓRICO"] += " " + line

    if not records:
        raise ValueError("Banco do Brasil 266: nenhum lançamento válido localizado.")
    if opening is None or closing is None:
        raise ValueError(
            "Banco do Brasil 266: saldos inicial ou final ausentes; envie o extrato completo."
        )
    total = sum(int(Decimal(str(row["VALOR"])) * 100) for row in records)
    if opening + total != closing:
        raise ValueError(
            "Banco do Brasil 266: saldo do extrato não confere com os lançamentos. "
            "Verifique se todas as linhas e páginas foram lidas."
        )
    return records

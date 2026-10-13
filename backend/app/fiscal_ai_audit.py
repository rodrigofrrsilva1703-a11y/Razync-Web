"""Auditoria determinística de pareceres de IA fiscal.

A auditoria NÃO aprova o mérito contábil. Compara somente valores citados
com os dados da própria conta e de suas evidências, acrescentando avisos.
Nenhum dado é enviado a outro serviço e nenhuma chamada de IA é executada.
"""
from decimal import Decimal, InvalidOperation
import re

_MONEY = re.compile(r"R\\$\\s*(-?\\s*\\d[\\d.,]*)", flags=re.IGNORECASE)


def _number(value):
    try:
        if isinstance(value, bool) or value is None:
            return None
        raw = str(value).strip().replace("R$", "").replace(" ", "")
        if not raw:
            return None
        negative = raw.startswith("-")
        raw = raw.lstrip("-")
        if "," in raw and "." in raw:
            separator = "," if raw.rfind(",") > raw.rfind(".") else "."
            raw = raw.replace("." if separator == "," else ",", "")
            raw = raw.replace(separator, ".")
        elif "," in raw:
            raw = raw.replace(",", ".")
        elif raw.count(".") > 1:
            raw = raw.replace(".", "")
        elif "." in raw and len(raw.split(".")[-1]) == 3:
            raw = raw.replace(".", "")
        number = Decimal(raw)
        return abs(-number if negative else number).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def audit_analysis(item):
    """Gera revisão independente; nunca altera os valores contábeis."""
    if not isinstance(item, dict):
        raise ValueError("Análise inválida")
    amounts = set()
    for value in (item.get("valores") or {}).values():
        parsed = _number(value)
        if parsed is not None:
            amounts.add(parsed)
    evidence = item.get("evidencias") or []
    for row in evidence:
        if not isinstance(row, dict):
            continue
        for field in ("debito", "credito", "debito_brl", "credito_brl"):
            parsed = _number(row.get(field))
            if parsed is not None:
                amounts.add(parsed)
    cited = set()
    for text in (item.get("explicacao") or "", item.get("verificar") or ""):
        for raw in _MONEY.findall(str(text)):
            parsed = _number(raw)
            if parsed is not None:
                cited.add(parsed)
    unexpected = sorted(cited - amounts)
    alerts = []
    if unexpected:
        alerts.append("A resposta cita valores que não foram confirmados nos totais ou evidências desta conta.")
    if not evidence:
        alerts.append("Sem lançamentos referenciados na resposta; conferir no Razão antes de concluir.")
    return {
        "situacao": "revisao_necessaria" if alerts else "conferencia_assistida",
        "valores_citados": len(cited),
        "valores_sem_comprovacao": len(unexpected),
        "lancamentos_citados": len(evidence),
        "alertas": alerts,
        "aviso": "Parecer automatizado: não substitui a revisão contábil humana.",
    }

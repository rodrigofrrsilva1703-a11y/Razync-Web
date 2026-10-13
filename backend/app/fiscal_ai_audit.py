"""Auditoria determinística de pareceres de IA fiscal.

A auditoria NÃO aprova o mérito contábil. Compara somente valores citados
com os dados da própria conta e de suas evidências, acrescentando avisos.
Nenhum dado é enviado a outro serviço e nenhuma chamada de IA é executada.
"""
from decimal import Decimal, InvalidOperation
import re

_MONEY = re.compile(r"R\$\s*(-?\s*\d(?:[\d.,]*\d)?)", flags=re.IGNORECASE)


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
    declared = {str(row.get("referencia", "")).upper() for row in evidence if isinstance(row, dict)}
    quoted = set(re.findall(r"\bL\d+\b", (str(item.get("explicacao") or "") + " " + str(item.get("verificar") or "")).upper()))
    unlinked = quoted - declared
    if unlinked:
        alerts.append("O texto cita referências sem evidência vinculada: " + ", ".join(sorted(unlinked)) + ".")
    return {
        "referencias_sem_evidencia": sorted(unlinked),
        "situacao": "revisao_necessaria" if alerts else "conferencia_assistida",
        "valores_citados": len(cited),
        "valores_sem_comprovacao": len(unexpected),
        "lancamentos_citados": len(evidence),
        "alertas": alerts,
        "aviso": "Parecer automatizado: não substitui a revisão contábil humana.",
    }


ANALYSIS_VERSION = "grounded-v1"


def structured_analysis(item, rows, *, sent=None, shortened=False, documentary=False):
    """Os fatos vêm do relatório; a narrativa do modelo permanece interpretação."""
    text = str(item.get("explicacao") or "").replace("\\n", "\n")
    parts = re.split(r"(?:\*\*)?(Fatos|Diferença|Hipóteses|Limitações)(?:\*\*)?\s*:", text, flags=re.I)
    sections = {parts[i].lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    total = len(rows)
    sent = total if sent is None else sent
    facts = []
    for label, key in (("Fiscal", "fiscal"), ("Contábil considerado", "contabil"),
                       ("Total do Razão", "total_conta"), ("Diferença (contábil − fiscal)", "diferenca")):
        facts.append({"rotulo": label, "valor": (item.get("valores") or {}).get(key, 0),
                      "origem": "Conferência calculada a partir dos relatórios"})
    missing = ["A causa do alerta ou da diferença exige conferir os documentos e a natureza dos lançamentos."]
    if not documentary:
        missing.append("O resumo por acumulador não contém documentos fiscais individuais para comprovar omissão ou duplicidade.")
    if sections.get("limitações"):
        missing.append("Limitação indicada pela IA: " + sections["limitações"])
    return {"versao": ANALYSIS_VERSION, "fatos": facts,
            "hipoteses": sections.get("hipóteses") or "A IA não separou as hipóteses. Revise a interpretação completa antes de concluir.",
            "informacoes_faltantes": missing,
            "cobertura": {"disponiveis": total, "enviados": sent,
                          "parcial": sent < total, "historicos_abreviados": shortened},
            "aviso": "Fatos numéricos calculados localmente. Hipóteses não comprovam a causa do alerta ou da diferença."}

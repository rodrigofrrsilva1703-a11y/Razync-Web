"""Auditoria determinística de pareceres de IA fiscal.

A auditoria NÃO aprova o mérito contábil. Compara somente valores citados
com os dados da própria conta e de suas evidências, acrescentando avisos.
Nenhum dado é enviado a outro serviço e nenhuma chamada de IA é executada.
"""
from decimal import Decimal, InvalidOperation
import re
import unicodedata

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


def contradicts_existing_entries(item):
    text = str(item.get("explicacao") or "")
    cited = set(re.findall(r"\bL\d+\b", text.upper()))
    declared = {str(row.get("referencia", "")).upper() for row in item.get("evidencias", []) if isinstance(row, dict)}
    return bool(cited & declared and re.search(
        r"não (?:foi|foram) (?:devidamente )?(?:lançad[oa]s?|registrad[oa]s?|contabilizad[oa]s?)", text, re.I))


_TAX_CAUSE = re.compile(r"cr[eé]ditos? (?:de impostos?|tribut[aá]rios?)|ajustes? de apura[çc][aã]o", re.I)


def ungrounded_tax_explanation(item):
    """Uma causa tributária precisa aparecer nas fontes, não apenas no texto da IA."""
    narrative = str(item.get("explicacao") or "") + " " + str(item.get("verificar") or "")
    if not _TAX_CAUSE.search(narrative):
        return False
    sources = " ".join(str(row.get("historico") or "") for row in item.get("evidencias", []) if isinstance(row, dict))
    sources += " " + " ".join(str(row.get("historico") or row.get("descricao") or "")
                               for row in item.get("documentos_evidencias", []) if isinstance(row, dict))
    return not bool(_TAX_CAUSE.search(sources))


def grounded_review_steps(item):
    """Plano local para comparar documentos quando a narrativa contém causa sem suporte."""
    codes = str(item.get("acumuladores") or "da conta")
    refs = ", ".join(str(row.get("referencia")) for row in item.get("evidencias", []) if isinstance(row, dict))
    account = str(item.get("conta") or "selecionada")
    return (f"1. Abra o detalhamento fiscal dos acumuladores {codes} e identifique as notas, datas e valores que compõem o resumo.\n"
            f"2. Compare cada nota com os históricos, datas, valores e contrapartidas da conta {account}"
            + (f", começando pelas referências {refs}.\n" if refs else ".\n")
            + "3. Separe documentos pareados e ainda não vinculados; confirme o período e a conta usada antes de atribuir a causa ou propor ajuste.")


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
    for doc in (item.get("parecer") or {}).get("comparacoes_documentais", []):
        for field in ("valor_brl", "valor_razao_candidato_brl", "diferenca_candidato_brl"):
            parsed = _number(doc.get(field))
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
    unsupported = re.search(r"não (?:foi|foram) (?:lançad[oa]s?|registrad[oa]s?)|confirmar (?:a )?(?:omissão|duplicidade)",
                            str(item.get("explicacao") or ""), re.I)
    if contradicts_existing_entries(item):
        alerts.append("Os lançamentos citados já constam no Razão. A sugestão de ausência de contabilização não foi confirmada; confira os documentos fiscais.")
    if ungrounded_tax_explanation(item):
        alerts.append("A explicação sugere créditos tributários ou ajustes de apuração sem registro explícito nas evidências; essa causa não foi sustentada.")
    if unsupported:
        alerts.append("A resposta sugere omissão ou duplicidade como conclusão. A diferença de totais não comprova essa causa; confira os documentos.")
    return {
        "referencias_sem_evidencia": sorted(unlinked),
        "situacao": "revisao_necessaria" if alerts else "conferencia_assistida",
        "valores_citados": len(cited),
        "valores_sem_comprovacao": len(unexpected),
        "lancamentos_citados": len(evidence),
        "alertas": alerts,
        "aviso": "Parecer automatizado: não substitui a revisão contábil humana.",
    }


ANALYSIS_VERSION = "grounded-depth-v7"


def narrative_sections(value):
    """Aceita títulos em Markdown, numerados, com/sem acento e aliases comuns."""
    text = str(value or "").replace("\\n", "\n").replace("\r\n", "\n").strip()
    labels = (r"Fatos(?: observados| dos relatórios| demonstrados)?|"
              r"Diferen[cç]a(?: encontrada)?|Hip[oó]teses?(?: da IA)?|"
              r"Poss[ií]veis causas|Causas prov[aá]veis|"
              r"Limita[cç](?:[aã]o|[oõ]es)(?: dos dados)?|Informa[cç][oõ]es faltantes")
    pattern = re.compile(r"(?:^|(?<=\s))(?:#{1,6}\s*|[-•]\s*|\d+[.)]\s*)?"
                         r"[*_]{0,2}(" + labels + r")[*_]{0,2}"
                         r"(?:\s*:[*_]{0,2}\s*|[ \t]*\n|[ \t]*$)", re.I)
    matches = list(pattern.finditer(text))
    sections = {}
    for i, match in enumerate(matches):
        label = "".join(c for c in unicodedata.normalize("NFD", match.group(1).lower()) if not unicodedata.combining(c))
        key = "hipoteses" if label.startswith(("hipot", "poss", "causas")) else "limitacoes" if label.startswith(("limit", "inform")) else "fatos" if label.startswith("fatos") else "diferenca"
        content = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip()
        if content:
            sections[key] = "\n\n".join(filter(None, [sections.get(key), content]))
    return text, sections


def structured_analysis(item, rows, *, sent=None, shortened=False, documentary=False):
    """Os fatos vêm do relatório; a narrativa do modelo permanece interpretação."""
    text, sections = narrative_sections(item.get("explicacao"))
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
    if sections.get("limitacoes") and not ungrounded_tax_explanation(item):
        missing.append("Limitação indicada pela IA: " + sections["limitacoes"])
    hypothesis = sections.get("hipoteses")
    tax_without_source = ungrounded_tax_explanation(item)
    if tax_without_source:
        hypothesis = "A causa está indeterminada: os lançamentos disponíveis não sustentam uma explicação por créditos tributários ou ajustes de apuração. Compare as notas que compõem o fiscal com os registros da conta para identificar a origem da diferença."
    if contradicts_existing_entries(item):
        hypothesis = "Os lançamentos citados já constam no Razão. A diferença entre os totais não identifica a causa; compare os documentos fiscais com a escrituração para confirmá-la."
    return {"versao": ANALYSIS_VERSION, "fatos": facts,
            "observacoes": "" if tax_without_source and _TAX_CAUSE.search(sections.get("fatos", "")) else sections.get("fatos", ""),
            "verificacoes": grounded_review_steps(item) if tax_without_source else str(item.get("verificar") or ""),
            "hipoteses": hypothesis or "A resposta não identifica hipóteses separadamente. Confira a interpretação da IA abaixo.",
            "interpretacao": text if not sections.get("hipoteses") and not tax_without_source else "",
            "informacoes_faltantes": missing,
            "cobertura": {"disponiveis": total, "enviados": sent,
                          "parcial": sent < total, "historicos_abreviados": shortened},
            "aviso": "Fatos numéricos calculados localmente. Hipóteses não comprovam a causa do alerta ou da diferença."}

"""Auditoria determinística de pareceres de IA fiscal.

A auditoria NÃO aprova o mérito contábil. Compara somente valores citados
com os dados da própria conta e de suas evidências, acrescentando avisos.
Nenhum dado é enviado a outro serviço e nenhuma chamada de IA é executada.
"""
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from collections import Counter
from datetime import datetime
from app.fiscal_investigation import explain_cases
from app.fiscal_review_outcomes import executive_summary, review_outcome

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
        r"não (?:foi|foram|tenha(?:m)? sido|tem sido|foram ainda|foi ainda) (?:devidamente )?(?:lançad[oa]s?|registrad[oa]s?|contabilizad[oa]s?)", text, re.I))


_TAX_CAUSE = re.compile(r"cr[eé]ditos? (?:de impostos?|tribut[aá]rios?)|ajustes? de apura[çc][aã]o|reten[çc][oõ]es", re.I)


def ungrounded_tax_explanation(item):
    """Uma causa tributária precisa aparecer nas fontes, não apenas no texto da IA."""
    narrative = str(item.get("explicacao") or "") + " " + str(item.get("verificar") or "")
    if not _TAX_CAUSE.search(narrative):
        return False
    sources = " ".join(str(row.get("historico") or "") for row in item.get("evidencias", []) if isinstance(row, dict))
    sources += " " + " ".join(str(row.get("historico") or row.get("descricao") or "")
                               for row in item.get("documentos_evidencias", []) if isinstance(row, dict))
    return not bool(_TAX_CAUSE.search(sources))


def invalid_accumulator_lookup(item):
    text = str(item.get("verificar") or "")
    return bool(re.search(r"(?:localiz|procur|busc|confer|verific)\w*[^.\n]{0,140}no raz[aã]o[^.\n]{0,100}acumulador|"
                          r"(?:localiz|procur|busc)\w*[^.\n]{0,100}acumulador[^.\n]{0,100}no raz[aã]o", text, re.I))


def grounded_review_steps(item):
    """Plano local para comparar documentos quando a narrativa contém causa sem suporte."""
    codes = str(item.get("acumuladores") or "da conta")
    refs = ", ".join(str(row.get("referencia")) for row in item.get("evidencias", []) if isinstance(row, dict))
    account = str(item.get("conta") or "selecionada")
    return (f"1. Abra o detalhamento fiscal dos acumuladores {codes} e identifique as notas, datas e valores que compõem o resumo.\n"
            f"2. Compare cada nota com os históricos, datas, valores e contrapartidas da conta {account}"
            + (f", começando pelas referências {refs}.\n" if refs else ".\n")
            + "3. Separe documentos pareados e ainda não vinculados; confirme o período e a conta usada antes de atribuir a causa ou propor ajuste.")


_NOTE_NUMBERS = re.compile(
    r"\b(?:NF(?:-?E)?|N\.?\s*F\.?|NOTAS?(?:\s+FISCA(?:L|IS))?|CTRC|CT\s*-?\s*E)"
    r"\s*(?:N[º°.]\s*)?[:#.-]*\s*(\d+(?:[./]\d+)*(?:\s*(?:,|e)\s*\d+(?:[./]\d+)*)*)", re.I)


def note_numbers(text):
    return {re.sub(r"\D", "", number).lstrip("0") or "0" for match in _NOTE_NUMBERS.finditer(str(text or ""))
            for number in re.findall(r"\d+(?:[./]\d+)*", match.group(1))}


def local_review_sufficient(report):
    """Caso objetivo: fiscal conciliado; só pagamentos fora da comparação.

    Não conclui a natureza dos pagamentos nem propõe lançamentos. Se a cobertura
    ou qualquer condição for incerta, deixa a conta seguir para a IA.
    """
    if len(report.get("contas", [])) != 1:
        return False
    account = report["contas"][0]
    key = f'{account["conta"]}:{account["tipo"]}'
    summary = report.get("resumo_documental", {}).get(key, {})
    coverage = report.get("cobertura_documental", {}).get(key, {})
    composition = summary.get("composicao", {})
    rows = report.get("lancamentos", [])
    if not (account.get("situacao") == "CONFERE COM ALERTAS" and account.get("diferenca") == 0
            and summary.get("documentos_lidos", 0) > 0 and summary.get("conciliados") == summary.get("documentos_lidos")
            and summary.get("documentos_pendentes") == 0 and coverage.get("amostra") is False
            and coverage.get("lancamentos_enviados") == coverage.get("lancamentos_pendentes") == len(rows)
            and rows and composition.get("confere_com_inicial") is True):
        return False
    if not all(re.search(r"\bpag[oa]|\bbaixa|\bliquida", str(row.get("historico", "")), re.I) for row in rows):
        return False
    values = {p["codigo"]: Decimal(str(p.get("valor", 0))) for p in composition.get("itens", [])}
    return (all(values.get(k) == 0 for k in ("vinculados", "fiscal_sem_vinculo", "cobertura"))
            and values.get("razao_sem_vinculo", 0) > 0
            and values.get("fora_inicial") == -values["razao_sem_vinculo"])


def _protect_fragment(item, rows, documents):
    """Remove alegações inseguras localmente, sem repetir chamadas externas.

    Fatos escritos pelo modelo não são publicados nem persistidos: a interface
    e a exportação usam exclusivamente fatos calculados a partir das fontes.
    """
    raw = str(item.get("explicacao") or "")
    _, sections = narrative_sections(raw)
    source_notes = {str(d.get("nota", "")).lstrip("0") or "0" for d in documents if d.get("nota")}
    source_notes |= {note for row in rows for note in note_numbers(row.get("historico", ""))}
    quoted = raw + " " + str(item.get("verificar") or "")
    unknown = note_numbers(quoted) - source_notes
    reasons = list((item.get("checagem_semantica") or {}).get("motivos", []))
    interpretation = sections.get("hipoteses", "") + " " + str(item.get("verificar") or "")
    if _MONEY.search(interpretation) or (not sections.get("hipoteses") and _MONEY.search(raw)):
        reasons.append("Valores monetários da narrativa foram retirados; consulte as diferenças e evidências calculadas pelo sistema.")
    if unknown:
        reasons.append("A resposta cita notas não comprovadas nas fontes desta conta: " + ", ".join(sorted(unknown)) + ".")
    quoted_refs = set(re.findall(r"\bL\d+\b", quoted.upper()))
    valid_refs = {str(row.get("referencia") or row.get("_referencia_ia") or "").upper() for row in rows}
    if quoted_refs - valid_refs:
        reasons.append("A resposta cita lançamentos fora das evidências desta conta.")
    summary = item.get("resumo_documental") or {}
    if summary.get("conciliados", 0) and re.search(r"nenhum[^.\n]{0,50}conciliad|(?:zero|0)\s+documentos?\s+conciliad", quoted, re.I):
        reasons.append("A resposta contradiz documentos já conciliados pelo sistema.")
    if summary.get("conciliados", 0) and summary.get("documentos_pendentes") == 0 and re.search(
        r"documentos?[^.\n]{0,60}(?:ainda n[aã]o|n[aã]o foram|sem v[ií]nculo|n[aã]o vinculad)", quoted, re.I):
        reasons.append("Os documentos fiscais desta conta já foram conciliados; o item em revisão é um movimento do Razão.")
    reasons.extend(unsupported_scenarios(item, rows))
    if contradicts_existing_entries(item):
        reasons.append("A resposta sugere ausência de registros que já constam no Razão.")
    if ungrounded_tax_explanation(item):
        reasons.append("A causa tributária não está apoiada nas fontes da conta.")
    if invalid_accumulator_lookup(item):
        reasons.append("A instrução confunde acumulador fiscal com conta do Razão.")
    hypothesis = sections.get("hipoteses") or raw
    if re.search(r"\bCFOP\s+\d{4}\s*[(—–]", hypothesis, re.I):
        reasons.append("A definição normativa de um CFOP não está comprovada pelos relatórios desta conferência.")
    if re.search(r"\b(?:deve[m]?|deveria[m]?)\s+(?:ter\s+(?:a\s+)?contrapartida|ser\s+(?:contabilizad|lan[çc]ad))", hypothesis, re.I):
        reasons.append("Uma contrapartida ou lançamento obrigatório não pode ser determinado apenas por estes indícios.")
    if re.search(r"comprovad[oa]s?\s+por\s+(?:notas|documentos)\s+fiscais", hypothesis, re.I) and not re.search(r"n[aã]o[^.]{0,25}comprovad", hypothesis, re.I):
        reasons.append("A referência à nota no relatório não comprova o documento original nem sua natureza contábil.")
    if any(d.get("conta_razao_candidato") for d in documents) and re.search(
        r"documentos fiscais n[aã]o foram contabilizados|aus[eê]ncia de correspond[eê]ncia (?:direta )?(?:entre|por)", hypothesis, re.I
    ) and not re.search(r"nesta conta|desta conta|amostra|sele[çc][aã]o|n[aã]o (?:comprova|demonstra|confirma|significa)", hypothesis, re.I):
        reasons.append("Há candidatos documentais em outras contas; a falta de vínculo nesta conta não pode ser generalizada à escrituração.")
    histories = " ".join(str(row.get("historico") or "") for row in rows)
    for cause, evidence in (
        (r"fretes?|encargos|despesas acess[oó]rias", r"frete|encargo|despesa acess[oó]ria"),
        (r"arredondamento", r"arredond"),
        (r"descontos?|abatimentos?", r"desconto|abatimento"),
        (r"cancelamento|estorno", r"cancel|estorn"),
    ):
        if re.search(cause, hypothesis, re.I) and not re.search(evidence, histories, re.I):
            reasons.append("A hipótese inclui uma causa sem registro correspondente nas fontes desta conta.")
    if re.search(r"mapeamento|conta distinta|outra conta|contas distintas", hypothesis, re.I) and not any(
        d.get("conta_razao_candidato") for d in documents
    ) and not re.search(r"reclassifica|transfer[eê]ncia", histories, re.I):
        reasons.append("Não há candidato em outra conta ou registro de reclassificação que sustente essa hipótese.")
    # Nunca aceitar somas recalculadas pelo modelo, mesmo quando o número
    # coincide com um total legítimo da conta (ex.: pagamentos da conta 361).
    if re.search(r"totaliz\w*|somam\b|somando\b|soma (?:de|dos|das)", quoted, re.I):
        reasons.append("As somas da narrativa foram retiradas; os totais exibidos são calculados pelo sistema.")
    if reasons:
        item["explicacao"] = ("Hipóteses: A causa ainda não está comprovada pelas evidências desta conta. "
                              "Limitações: confirme os documentos e os vínculos apresentados pelo sistema antes de propor ajustes.")
        item["verificar"] = grounded_review_steps(item)
    elif sections.get("hipoteses"):
        item["explicacao"] = "Hipóteses: " + sections["hipoteses"]
        if sections.get("limitacoes"):
            item["explicacao"] += "\n\nLimitações: " + sections["limitacoes"]
    elif sections.get("fatos"):
        item["explicacao"] = "Hipóteses: A resposta não forneceu uma interpretação separada dos fatos. Limitações: confira as evidências calculadas pelo sistema."
    item["checagem_semantica"] = {"interpretacao_retirada": bool(reasons), "motivos": list(dict.fromkeys(reasons))}
    return item


def readable_analysis(text):
    """Traduz nomes internos sem alterar referências ou fatos validados."""
    labels = {
        "CORRESPONDENCIA_EM_ANALISE": "vínculo em análise",
        "CONTA_DIFERENTE": "possível lançamento em outra conta",
        "VALOR_DIFERENTE": "valor diferente entre documento e candidato",
        "SEM_LANCAMENTO_IDENTIFICADO": "documento sem correspondência identificada",
        "SEM_DOCUMENTO_IDENTIFICADO": "movimento sem documento identificado",
        "DOCUMENTOS_NAO_IDENTIFICAVEIS": "documentos não identificáveis no relatório",
        "ESTORNO_EM_ANALISE": "possível estorno a conferir",
        "vinculos_incertos": "vínculos a confirmar",
        "DATA_DIFERENTE": "datas diferentes",
    }
    for code, label in labels.items():
        text = re.sub(r"\b" + code + r"\b", label, str(text), flags=re.I)
    return text


def protect_publication(item, rows, documents):
    """Valida cada afirmação separadamente e conserva os trechos sustentados."""
    _, sections = narrative_sections(item.get("explicacao"))
    prior = item.get("checagem_semantica") or {}
    reasons = list(prior.get("motivos", []))
    retained = {}
    removed = int(prior.get("trechos_retirados", 0))
    parts = {"hipoteses": sections.get("hipoteses") or ("" if sections.get("fatos") else item.get("explicacao", "")),
             "limitacoes": sections.get("limitacoes", ""), "verificar": item.get("verificar", ""),
             "fatos": sections.get("fatos", "")}
    for section, value in parts.items():
        safe = []
        # Ponto decimal e abreviações sem espaço não separam afirmações.
        pattern = r"\n+" if section == "verificar" else r"\n+|(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9])"
        for fragment in re.split(pattern, str(value or "")):
            if not fragment.strip():
                continue
            probe = {**item, "explicacao": "Hipóteses: " + fragment, "verificar": ""}
            probe.pop("checagem_semantica", None)
            _protect_fragment(probe, rows, documents)
            flags = probe["checagem_semantica"]["motivos"]
            if flags:
                reasons.extend(flags)
                removed += 1
            elif section != "fatos":
                safe.append(readable_analysis(fragment.strip()))
        retained[section] = safe
    # Se a hipótese foi retirada, não deixe apenas frases que dependem dela
    # ("a evidência que enfraquece essa hipótese...") como interpretação solta.
    dependent = re.compile(r"^(?:A evid[eê]ncia que enfraquece|O resultado que (?:descartaria|confirmaria)|Essa hip[oó]tese|Esta hip[oó]tese)", re.I)
    if removed and retained["hipoteses"] and all(dependent.search(s) for s in retained["hipoteses"]):
        retained["hipoteses"] = []
    hypotheses = " ".join(retained["hipoteses"])
    item["explicacao"] = "Hipóteses: " + (hypotheses or "A causa ainda não está comprovada pelas evidências desta conta.")
    if retained["limitacoes"]:
        item["explicacao"] += "\n\nLimitações: " + " ".join(retained["limitacoes"])
    item["verificar"] = "\n".join(retained["verificar"]) or grounded_review_steps(item)
    item["checagem_semantica"] = {"interpretacao_retirada": bool(reasons),
        "motivos": list(dict.fromkeys(reasons)), "trechos_retirados": removed}
    return item


def link_text_evidence(item, rows):
    """Vincula referências citadas somente quando pertencem às fontes da própria conta."""
    quoted = set(re.findall(r"\bL\d+\b", (str(item.get("explicacao") or "") + " " + str(item.get("verificar") or "")).upper()))
    evidence = list(item.get("evidencias") or [])
    linked = {str(row.get("referencia", "")).upper() for row in evidence if isinstance(row, dict)}
    for row in rows:
        if len(evidence) >= 8:
            break
        ref = str(row.get("_referencia_ia") or row.get("referencia") or "").upper()
        if ref in quoted - linked and str(row.get("conta")) == str(item.get("conta")):
            evidence.append({key: value for key, value in dict(row, referencia=ref).items() if key != "_referencia_ia"})
            linked.add(ref)
    item["evidencias"] = evidence


def unsupported_scenarios(item, rows):
    """Uma possibilidade concreta precisa de um indício nas fontes da conta."""
    _, sections = narrative_sections(item.get("explicacao"))
    hypothesis = sections.get("hipoteses") or str(item.get("explicacao") or "")
    source = " ".join(str(row.get("historico") or "") for row in rows if isinstance(row, dict))
    reasons = []
    if re.search(r"pagamentos? antecipados?|adiantamentos?", hypothesis, re.I) and not re.search(r"antecip|adiant", source, re.I):
        reasons.append("Os históricos não indicam antecipação ou adiantamento; essa hipótese foi retirada.")
    if re.search(r"ajustes? internos?", hypothesis, re.I) and not re.search(r"ajuste|reclassifica|transfer[eê]ncia interna", source, re.I):
        reasons.append("Não há registro explícito de ajuste interno nos históricos; essa hipótese foi retirada.")
    duplication_claim = any("duplic" in sentence.lower() and not re.search(r"não|sem (?:prova|comprova)|não comprova", sentence, re.I)
                            for sentence in re.split(r"(?<=[.!?])\s+", hypothesis))
    if duplication_claim:
        notes = Counter()
        signatures = Counter()
        for row in rows:
            history = str(row.get("historico") or "").strip().casefold()
            for number in re.findall(r"\b(?:nf|nfe|nota fiscal)\s*[:#.-]?\s*(\d+)\b", history, re.I):
                notes[(number, str(row.get("contrapartida") or ""))] += 1
            if history:
                signatures[(history, str(row.get("data") or ""), str(row.get("debito") or 0), str(row.get("credito") or 0), str(row.get("contrapartida") or ""))] += 1
        if not any(count > 1 for count in (*notes.values(), *signatures.values())):
            reasons.append("Não foi encontrado um par repetido de nota ou movimento nas fontes enviadas; a hipótese de duplicidade foi retirada.")
        elif any("duplic" in sentence.lower() and re.search(r"\b(?:há|houve|existe|ocorreu|confirmad[oa]|comprovad[oa]|constatad[oa]|confirmam|comprovam)\b", sentence, re.I)
                 and not re.search(r"pode|poss[ií]vel|hip[oó]tese|ind[ií]cio|não", sentence, re.I)
                 for sentence in re.split(r"(?<=[.!?])\s+", hypothesis)):
            reasons.append("Um par de registros é indício para revisão, não comprovação de duplicidade; a conclusão afirmativa foi retirada.")
    return reasons


def _record_date(value):
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), pattern)
        except ValueError:
            pass
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
    for doc in (item.get("parecer") or {}).get("comparacoes_documentais", []):
        for field in ("valor_brl", "valor_fiscal_grupo_brl", "valor_razao_candidato_brl", "diferenca_candidato_brl"):
            parsed = _number(doc.get(field))
            if parsed is not None:
                amounts.add(parsed)
    local = item.get("resumo_documental") or {}
    for part in (local.get("composicao") or {}).get("itens", []):
        parsed = _number(part.get("valor"))
        if parsed is not None:
            amounts.add(parsed)
    for field in ("total", "documentos_lidos", "razao_completo_conta"):
        parsed = _number((local.get("composicao") or {}).get(field))
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
    if invalid_accumulator_lookup(item):
        alerts.append("O acumulador pertence ao resumo fiscal; no Razão, a conferência deve localizar a conta e os lançamentos.")
    if ungrounded_tax_explanation(item):
        alerts.append("A explicação sugere créditos tributários, retenções ou ajustes de apuração sem registro explícito nas evidências; essa causa não foi sustentada.")
    if unsupported:
        alerts.append("A resposta sugere omissão ou duplicidade como conclusão. A diferença de totais não comprova essa causa; confira os documentos.")
    alerts.extend((item.get("checagem_semantica") or {}).get("motivos", []))
    return {
        "referencias_sem_evidencia": sorted(unlinked),
        "situacao": "revisao_necessaria" if alerts else "conferencia_assistida",
        "valores_citados": len(cited),
        "valores_sem_comprovacao": len(unexpected),
        "lancamentos_citados": len(evidence),
        "alertas": alerts,
        "aviso": "Parecer automatizado: não substitui a revisão contábil humana.",
    }


ANALYSIS_VERSION = "clear-documentary-review-v14"


def narrative_sections(value):
    """Aceita títulos em Markdown, numerados, com/sem acento e aliases comuns."""
    text = str(value or "").replace("\\n", "\n").replace("\r\n", "\n").strip()
    labels = (r"Fatos(?: observados| dos relatórios| demonstrados)?|"
              r"Diferen[cç]a(?: encontrada)?|Hip[oó]teses?(?: da IA)?|"
              r"Poss[ií]veis causas|Causas prov[aá]veis|"
              r"Limita[cç](?:[aã]o|[oõ]es)(?: dos dados)?|Informa[cç][oõ]es faltantes")
    pattern = re.compile(r"(?:^|(?<=\s))(?:#{1,6}\s*|[-•]\s*|(?:^|(?<=\n))\d+[.)]\s*)?"
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


def _signed_amount(value):
    try:
        number = Decimal(str(value or 0))
        return number.quantize(Decimal("0.01")) if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _brl(value):
    number = _signed_amount(value)
    if number is None:
        return "valor não disponível"
    body = f"{abs(number):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("-" if number < 0 else "") + "R$ " + body


def comparison_reading(item, rows, periodo_fiscal=None):
    """Explica a regra aplicada aos relatórios, sem pedir ao modelo que a adivinhe."""
    values = item.get("valores") or {}
    if any(key not in values for key in ("fiscal", "contabil", "total_conta")):
        return {"explicacoes": [], "excluidos": [], "orientacoes": []}
    fiscal, considered, total = (_signed_amount(values.get(key)) for key in ("fiscal", "contabil", "total_conta"))
    if any(value is None for value in (fiscal, considered, total)) or not values:
        return {"explicacoes": [], "excluidos": [], "orientacoes": []}
    outgoing = item.get("tipo") == "SAÍDAS"
    side, field, opposite = ("créditos", "credito", "débitos") if outgoing else ("débitos", "debito", "créditos")
    selected = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        nature = "".join(c for c in unicodedata.normalize("NFD", str(row.get("natureza") or "").upper()) if not unicodedata.combining(c))
        if nature and ("CREDITO" if outgoing else "DEBITO") not in nature:
            continue
        amount = _signed_amount(row.get(field))
        if amount is not None and abs(amount) >= Decimal("0.005"):
            selected.append((row, amount))
    excluded = [(row, amount) for row, amount in selected if row.get("classificacao") == "ALERTA - NÃO FISCAL"]
    probable = [row for row, _ in selected if row.get("classificacao") == "FISCAL PROVÁVEL"]
    value_only = [row for row, _ in selected if row.get("classificacao") == "FECHAMENTO POR VALOR - VALIDAR"]
    paragraphs = [f"Nesta conta, a comparação usa os {side} das {'saídas' if outgoing else 'entradas/serviços'}. "
                  f"Os {opposite} do lado oposto não participam; valores negativos no lado escolhido reduzem o total como estorno."]
    if selected and len(excluded) + len(probable) + len(value_only) == len(selected):
        paragraphs.append(f"Dos {len(selected)} movimentos desse lado, {len(probable)} foram considerados por indícios fiscais no histórico, "
                          f"{len(excluded)} ficaram fora da comparação e {len(value_only)} entraram apenas por fechamento de valor, ainda sujeitos a validação.")
    if excluded:
        delta = total - considered
        if abs(sum((amount for _, amount in excluded), Decimal(0)) - delta) <= Decimal("0.01"):
            paragraphs.append(f"O total do Razão é {_brl(total)}, mas a comparação usa {_brl(considered)}. "
                              f"Os movimentos fora da comparação representam {_brl(delta)}; eles não foram apagados da conta, apenas separados nesta conferência.")
        else:
            paragraphs.append(f"O total do Razão ({_brl(total)}) e o contábil considerado ({_brl(considered)}) têm escopos diferentes. "
                              "Confira os movimentos separados antes de interpretar a diferença.")
        paragraphs.append("Históricos que começam com Pago, Pagamento, Recebido, Recebimento ou Baixa são separados pela regra da ferramenta, "
                          "assim como históricos sem indício fiscal reconhecido. Esse filtro não prova que o movimento seja indevido: "
                          "um pagamento pode liquidar uma despesa já registrada, e a natureza deve ser confirmada no documento.")
    elif probable and len(probable) == len(selected):
        paragraphs.append("Todos os movimentos desse lado foram considerados porque seus históricos contêm indícios fiscais. "
                          "Isso permite comparar os valores, mas não comprova que todas as notas do resumo estejam vinculadas ao Razão.")
    if not excluded and abs(total - considered) > Decimal("0.01"):
        paragraphs.append(f"O total do Razão ({_brl(total)}) é diferente do contábil considerado ({_brl(considered)}). "
                          "O primeiro reúne os movimentos do lado analisado; o segundo é o conjunto selecionado para a comparação fiscal. "
                          "As classificações disponíveis neste contexto não permitem detalhar todos os movimentos dessa separação.")
    if value_only:
        paragraphs.append("O fechamento por valor inclui movimentos mesmo sem indício fiscal suficiente no histórico. "
                          "A soma bater não substitui a confirmação da natureza de cada documento.")
    difference = considered - fiscal
    if abs(difference) <= Decimal("0.01"):
        paragraphs.append(f"O fiscal e o contábil considerado coincidem em {_brl(fiscal)}. "
                          "O resultado fecha para os movimentos selecionados; os alertas permanecem para revisar a classificação e a ligação com as notas.")
    else:
        paragraphs.append(f"O contábil considerado está {_brl(abs(difference))} {'abaixo' if difference < 0 else 'acima'} do fiscal. "
                          "Essa diferença informa quanto falta conciliar entre os dois conjuntos, sem demonstrar sozinha omissão, duplicidade ou erro.")
    codes = str(item.get("acumuladores") or "vinculados a esta conta")
    account = str(item.get("conta") or "selecionada")
    movements = []
    for row, amount in excluded:
        history = str(row.get("historico") or "Histórico não informado")
        payment = bool(re.match(r"^(PAGO|PAGAMENTO|RECEBIDO|RECEBIMENTO|BAIXA)\b", history, re.I))
        movements.append({"referencia": row.get("_referencia_ia") or row.get("referencia") or "—", "data": row.get("data", ""),
                          "historico": history, "contrapartida": str(row.get("contrapartida") or "—"), "valor_brl": _brl(amount),
                          "motivo": "Histórico de pagamento/recebimento/baixa" if payment else "Sem indício fiscal reconhecido no histórico"})
    steps = []
    if excluded or value_only:
        steps.append({"categoria": "SELECAO_HISTORICO" if excluded else "VINCULO_POR_VALOR", "acao": f"Revise os {len(excluded)} movimentos fora da comparação" if excluded else "Revise os movimentos incluídos apenas pelo valor",
                      "objetivo": "Compare o comprovante com o documento de origem e com o reconhecimento na conta. Isso esclarece se o movimento pertence à operação fiscal ou à sua liquidação; o alerta não confirma duplicidade."})
    steps.append({"categoria":"DETALHAMENTO_NECESSARIO", "acao": f"Abra o detalhamento dos acumuladores {codes} e identifique as notas que compõem o fiscal",
                  "objetivo": "Separe número da nota, data e valor. Assim você transforma o total fiscal em documentos que podem ser comparados individualmente, em vez de procurar o código do acumulador no Razão."})
    steps.append({"acao": f"Compare essas notas com os lançamentos da conta {account}",
                  "objetivo": "Use histórico, data, valor e contrapartida para confirmar o vínculo. Se uma nota não for localizada, confira período, filial e conta usada antes de concluir ausência; valores parecidos, sozinhos, não provam correspondência."})
    included = []
    for row, amount in selected:
        if row.get("classificacao") not in {"FISCAL PROVÁVEL", "FECHAMENTO POR VALOR - VALIDAR"}:
            continue
        history = str(row.get("historico") or "Histórico não informado")
        included.append({"referencia": row.get("_referencia_ia") or row.get("referencia") or "—", "data": row.get("data", ""),
                         "historico": history, "contrapartida": str(row.get("contrapartida") or "—"), "valor_brl": _brl(amount),
                         "motivo": "Indício fiscal no histórico" if row.get("classificacao") == "FISCAL PROVÁVEL" else "Fechamento de valor; validar documento"})
    relations = []
    def invoice_number(history):
        found = re.search(r"\b(?:NF|NFE|NOTA FISCAL)\s*[:#.-]?\s*(\d+)\b", history, re.I)
        return (found.group(1).lstrip("0") or "0") if found else None
    payment_index = {}
    for row in movements:
        number = invoice_number(row["historico"])
        if number and row["motivo"] == "Histórico de pagamento/recebimento/baixa":
            payment_index.setdefault((number,row["valor_brl"]), []).append(row)
    total_relations = 0
    for considered_row in included:
        number = invoice_number(considered_row["historico"])
        if not number: continue
        candidates = payment_index.get((number,considered_row["valor_brl"]), [])
        total_relations += len(candidates)
        for paid_row in candidates[:max(0,20-len(relations))]:
            relations.append({"nota": number, "registro": considered_row["referencia"], "pagamento": paid_row["referencia"],
                              "data_registro": considered_row["data"], "data_pagamento": paid_row["data"], "valor_brl": paid_row["valor_brl"],
                              "contrapartida_registro": considered_row["contrapartida"], "contrapartida_pagamento": paid_row["contrapartida"]})
    observations = []
    if probable or value_only or excluded:
        parts = []
        if probable: parts.append(f"{len(probable)} com indício fiscal no histórico")
        if excluded: parts.append(f"{len(excluded)} fora da comparação")
        if value_only: parts.append(f"{len(value_only)} incluídos apenas por fechamento de valor, sem comprovação da natureza")
        observations.append(f"Foram examinados {len(selected)} movimentos: " + "; ".join(parts) + ".")
    notes = list(dict.fromkeys(number for row in included for number in re.findall(r"\b(?:NF|NFE|NOTA FISCAL)\s*[:#.-]?\s*(\d+)\b", row["historico"], re.I)))
    if notes:
        observations.append("Os movimentos considerados citam as notas " + ", ".join(notes[:8]) + (f" e outras {len(notes)-8}" if len(notes)>8 else "") + ". A presença da nota no histórico não confirma, sozinha, o vínculo com o acumulador.")
    if excluded:
        observations.append(f"Os movimentos fora da comparação somam {_brl(sum((amount for _,amount in excluded),Decimal(0)))}. "
                            "Históricos de pagamento ou baixa podem representar liquidação de uma obrigação; confira o documento de origem antes de somá-los novamente ao fiscal.")
    for pair in relations[:6]:
        observations.append(f"A nota {pair['nota']} aparece em {pair['registro']} ({pair['data_registro']}, contrapartida {pair['contrapartida_registro']}) "
                            f"e em {pair['pagamento']} ({pair['data_pagamento']}, contrapartida {pair['contrapartida_pagamento']}), pelo mesmo valor de {pair['valor_brl']}. "
                            "O primeiro entrou na comparação; o segundo tem histórico de pagamento e ficou fora. É um vínculo candidato entre registros, a confirmar nos documentos.")
    if total_relations > 6:
        observations.append(f"Foram encontrados {total_relations} pares candidatos; os seis primeiros estão descritos acima. A relação não confirma que sejam a mesma operação.")
    if relations:
        pairs = ", ".join(f"{pair['registro']}/{pair['pagamento']}" for pair in relations[:6])
        steps.insert(0, {"acao": "Confronte os pares " + pairs, "objetivo": "Confira emissor, número da nota, valor, comprovante e contrapartidas. Isso esclarece se os registros representam a mesma operação em etapas diferentes ou um registro adicional; coincidência de número e valor não confirma duplicidade ou liquidação."})
    fiscal_begin = _record_date((periodo_fiscal or {}).get("inicio"))
    competence_refs = {}
    for row in movements:
        match = re.search(r"\bref\.?\s*(\d{2})/(\d{4})\b", row['historico'], re.I)
        if match and fiscal_begin:
            month, year = int(match.group(1)), int(match.group(2))
            if 1 <= month <= 12 and (year,month) < (fiscal_begin.year,fiscal_begin.month):
                competence_refs.setdefault(f"{month:02d}/{year}", []).append(row['referencia'])
    for competence, refs in competence_refs.items():
        observations.append(f"Os pagamentos {', '.join(refs)} trazem referência a {competence}, anterior ao início do período fiscal. "
                            "A data do pagamento e a competência descrita no histórico são diferentes; confira o documento de origem antes de incluí-los no fiscal deste período.")
    dates = [_record_date(row.get("data")) for row,_ in selected]
    dates = [date for date in dates if date]
    if dates:
        observations.append(f"Os movimentos deste lado no contexto vão de {min(dates):%d/%m/%Y} a {max(dates):%d/%m/%Y}.")
    period = periodo_fiscal or {}
    begin, end = _record_date(period.get("inicio")), _record_date(period.get("fim"))
    missing_months = []
    if begin and end and 0 <= (end.year-begin.year)*12+end.month-begin.month <= 24:
        expected = range(begin.year*12+begin.month-1, end.year*12+end.month)
        present = {date.year*12+date.month-1 for date in dates}
        missing_months = [f"{month%12+1:02d}/{month//12}" for month in expected if month not in present]
    if missing_months and selected and len(dates) == len(selected):
        observations.append("O período fiscal inclui " + ", ".join(missing_months) + ", sem movimentos desse lado no contexto da conta. "
                            "Verifique se há notas desses meses no acumulador e onde foram escrituradas; isso não comprova ausência de lançamento.")
        steps.append({"acao": "Confira as competências " + ", ".join(missing_months), "objetivo": "Localize as notas desses meses no detalhamento fiscal e confira conta, filial e data de escrituração. O resumo cobre um período maior que as datas dos movimentos enviados."})
    if abs(difference) <= Decimal("0.01"):
        result = f"Os valores comparados fecham em {_brl(fiscal)}. " + ("Os alertas vêm dos movimentos separados ou incluídos apenas por valor; a natureza ainda precisa ser validada." if excluded or value_only else "A confirmação documental continua necessária para comprovar a origem dos valores.")
    else:
        result = f"O contábil considerado está {_brl(abs(difference))} {'abaixo' if difference < 0 else 'acima'} do fiscal. A origem dessa diferença ainda não está confirmada."
    return {"explicacoes": paragraphs, "resultado": result,
            "criterio": f"Comparação pelo lado dos {side}; o lado oposto não entra. A seleção por histórico é um indício, não uma validação documental.",
            "observacoes": observations, "relacoes": relations, "considerados": included, "excluidos": movements, "orientacoes": steps}


def structured_analysis(item, rows, *, sent=None, shortened=False, documentary=False, periodo_fiscal=None):
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
    scenario_issues = unsupported_scenarios(item, rows)
    unsafe_narrative = ungrounded_tax_explanation(item) or contradicts_existing_entries(item) or bool(scenario_issues)
    if sections.get("limitacoes") and not unsafe_narrative:
        missing.append(("Para confirmar: " if item.get("provedor") == "local" else "Limitação indicada pela IA: ") + sections["limitacoes"])
    hypothesis = sections.get("hipoteses")
    tax_without_source = ungrounded_tax_explanation(item)
    if tax_without_source:
        hypothesis = "A causa está indeterminada: os lançamentos disponíveis não sustentam uma explicação por créditos tributários ou ajustes de apuração. Compare as notas que compõem o fiscal com os registros da conta para identificar a origem da diferença."
    if contradicts_existing_entries(item):
        hypothesis = "Os lançamentos citados já constam no Razão. A diferença entre os totais não identifica a causa; compare os documentos fiscais com a escrituração para confirmá-la."
    validation = audit_analysis(item)
    text_issues = validation["referencias_sem_evidencia"] or validation["valores_sem_comprovacao"]
    display_text = hypothesis or (text if not sections.get("hipoteses") else "")
    if scenario_issues or text_issues or not sections.get("hipoteses"):
        display_text = "Os dados disponíveis não sustentam uma causa específica. A investigação deve partir dos movimentos identificados abaixo e dos documentos que compõem o fiscal."
    reading = comparison_reading(item, rows, periodo_fiscal)
    local = item.get("resumo_documental") or {}
    if local:
        from app.fiscal_ai_documental_reading import documentary_reading
        docs = (item.get("parecer") or {}).get("comparacoes_documentais", [])
        reading = documentary_reading(item, docs, reading)
    if (scenario_issues or text_issues) and reading.get("relacoes"):
        display_text = "Há pares com número de nota e valor coincidentes entre os registros considerados e os pagamentos. Isso sustenta investigar se correspondem à mesma operação em etapas diferentes; não confirma duplicidade nem liquidação. Valide o emissor, os comprovantes e as contrapartidas desses pares."
    # As orientações mais concretas vêm de indícios estruturados do Razync,
    # não de uma nova inferência da IA. Preserva as verificações já existentes.
    dossier = item.get("dossie_contabil") or {}
    priorities = dossier.get("prioridades_de_investigacao") or []
    if priorities and not reading.get("documental_especifico"):
        specific_steps = []
        for step in priorities[:3]:
            if not isinstance(step, dict):
                continue
            ref = str(step.get("referencia") or "").strip()
            action = str(step.get("acao") or "").strip()
            goal = str(step.get("como_verificar") or "").strip()
            if action and goal:
                specific_steps.append({"acao": action + (f" ({ref})" if ref else ""),
                                       "objetivo": goal, "categoria": step.get("categoria", "")})
        if specific_steps:
            reading["orientacoes"] = (specific_steps + list(reading.get("orientacoes") or []))[:3]
    # Regera orientações práticas também ao reabrir um parecer cacheado.
    reading["orientacoes"] = [dict(step, **review_outcome(step.get("categoria", "")))
                              for step in reading.get("orientacoes", [])]
    for limit in (dossier.get("limites_das_fontes") or [])[:2]:
        if isinstance(limit, str) and limit and limit not in missing:
            missing.append(limit)
    cases = explain_cases(item.get("investigacoes_locais", []), display_text, item.get("verificar"))
    if cases:
        reading["orientacoes_ia"] = str(item.get("verificar") or "")
    return {"versao": ANALYSIS_VERSION, "fatos": facts,
            "resumo_executivo": executive_summary(item, reading, partial=sent < total),
            "pendencias_explicadas": cases,
            "composicao": (local.get("composicao") or {}),
            "analise_exibicao": display_text, "sugestoes_retiradas": scenario_issues,
            "leitura_comparacao": reading,
            "observacoes": "",
            "verificacoes": grounded_review_steps(item) if unsafe_narrative or invalid_accumulator_lookup(item) else str(item.get("verificar") or ""),
            "hipoteses": hypothesis or "A resposta não identifica hipóteses separadamente. Confira a interpretação da IA abaixo.",
            "interpretacao": text if not sections.get("hipoteses") and not tax_without_source else "",
            "informacoes_faltantes": missing,
            "cobertura": {"disponiveis": total, "enviados": sent,
                          "parcial": sent < total, "historicos_abreviados": shortened},
            "aviso": "Fatos numéricos calculados localmente. Hipóteses não comprovam a causa do alerta ou da diferença."}

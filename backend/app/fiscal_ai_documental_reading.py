"""Leitura documental específica por conta para o parecer fiscal-contábil.

Nenhuma causa é inferida a partir de totais. Cada destaque é extraído das
pendências reais, preservando notas, valores e contas candidatas sem declarar
vínculos não confirmados. Os totais completos são os calculados pelo Razync.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation

PRIORITY = (
    "VALOR_DIFERENTE", "CONTA_DIFERENTE", "ESTORNO_EM_ANALISE",
    "DATA_DIFERENTE", "SEM_LANCAMENTO_IDENTIFICADO",
    "AMBIGUO", "PROVAVEL",
)
LABELS = {
    "VALOR_DIFERENTE": "Valor divergente",
    "CONTA_DIFERENTE": "Possível lançamento em outra conta",
    "ESTORNO_EM_ANALISE": "Estorno em análise",
    "DATA_DIFERENTE": "Data ou competência diferente",
    "SEM_LANCAMENTO_IDENTIFICADO": "Correspondência não identificada",
    "AMBIGUO": "Mais de uma correspondência possível",
    "PROVAVEL": "Correspondência provável, sem confirmação",
}
CHECKS = {
    "VALOR_DIFERENTE": "Compare o total da nota, o valor contábil candidato e eventuais parcelas/estornos.",
    "CONTA_DIFERENTE": "Confirme número, série, parceiro, histórico e contrapartida nas duas contas antes de alterar o vínculo.",
    "ESTORNO_EM_ANALISE": "Localize o registro original e o estorno e verifique o efeito na competência.",
    "DATA_DIFERENTE": "Compare data de emissão, competência fiscal e data efetiva de contabilização.",
    "SEM_LANCAMENTO_IDENTIFICADO": "Pesquise nota e série no Razão completo e em outras contas; não presuma omissão.",
    "AMBIGUO": "Diferencie os candidatos por número, série, valor, parceiro e período.",
    "PROVAVEL": "Confirme o vínculo pelo documento e a contrapartida antes de considerar a conciliação concluída.",
}


def _text(value, length=120):
    return str(value or "").strip()[:length]


def _amount(value):
    try:
        number = Decimal(str(value or 0))
        return number if number.is_finite() else Decimal(0)
    except (TypeError, InvalidOperation, ValueError):
        return Decimal(0)


def _brl(value):
    number = _amount(value)
    return ("-" if number < 0 else "") + "R$ " + f"{abs(number):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _extract_highlights(documents, maximum=4):
    grouped = {}
    for doc in documents:
        status = _text(doc.get("situacao")).upper()
        if status not in LABELS:
            continue
        grouped.setdefault(status, []).append(doc)
    # Cobrir mecanismos diferentes primeiro; amostras da mesma situação
    # só entram caso sobrem espaços e sempre com referência real.
    ordered = []
    for status in PRIORITY:
        if status in grouped:
            ordered.append(grouped[status][0])
    for status in PRIORITY:
        ordered.extend(grouped.get(status, [])[1:])
    seen = set()
    highlights = []
    for doc in ordered:
        status = _text(doc.get("situacao")).upper()
        ref = _text(doc.get("referencia"), 48)
        key = (ref, status)
        if not ref or key in seen:
            continue
        seen.add(key)
        code = _text(doc.get("nota"), 48)
        acc = _text(doc.get("acumulador"), 45)
        title = f"NF {code}" if code else f"Documento {ref}"
        if acc:
            title += f" · acumulador {acc}"
        cand = _text(doc.get("conta_razao_candidato"), 30)
        value = _text(doc.get("valor_brl"), 48)
        difference = _text(doc.get("diferenca_candidato_brl"), 48)
        candidate_value = _text(doc.get("valor_razao_candidato_brl"), 48)
        record = {
            "referencia": ref, "situacao": status, "tipo": LABELS[status],
            "documento": title, "data": _text(doc.get("data"), 20),
            "valor_fiscal": value, "conta_candidata": cand,
            "valor_razao_candidato": candidate_value,
            "diferenca_candidata": difference,
            "como_verificar": CHECKS[status],
        }
        if doc.get("vinculo_confirmado") is False:
            record["vinculo_confirmado"] = False
        highlights.append(record)
        if len(highlights) == maximum:
            break
    return highlights


def documentary_reading(item, docs, old_reading):
    summary = item.get("resumo_documental") or {}
    if not summary:
        return old_reading
    coverage = item.get("cobertura_documental") or {}
    composition = summary.get("composicao") or {}
    all_statuses = summary.get("situacoes") or {}
    pending = max(0, int(summary.get("documentos_pendentes") or 0))
    ledger = max(0, int(summary.get("movimentos_pendentes") or 0))
    total = max(0, int(summary.get("documentos_lidos") or 0))
    reconciled = max(0, int(summary.get("conciliados") or 0))
    highlights = _extract_highlights(docs)
    statuses = [
        {"codigo": status, "tipo": LABELS[status], "quantidade": int(all_statuses[status])}
        for status in PRIORITY if int(all_statuses.get(status, 0) or 0) > 0
    ]
    if not statuses and docs:
        count = Counter(_text(doc.get("situacao")).upper() for doc in docs)
        statuses = [
            {"codigo": status, "tipo": LABELS[status], "quantidade": count[status]}
            for status in PRIORITY if count[status]
        ]

    if pending and ledger:
        headline = f"{pending} documento(s) fiscais e {ledger} movimento(s) contábeis ainda exigem verificação de vínculo."
    elif pending:
        headline = f"{pending} documento(s) fiscais continuam sem vínculo confirmado nesta conta."
    elif ledger:
        headline = f"{ledger} movimento(s) do Razão permanecem para identificar ou justificar nesta conta."
    else:
        headline = "Os documentos fiscais foram conciliados no cruzamento local."
    if statuses:
        main = statuses[0]
        headline += f" A primeira prioridade é: {main['tipo'].lower()} ({main['quantidade']})."

    findings = []
    for entry in statuses[:4]:
        findings.append(f"{entry['quantidade']} documento(s): {entry['tipo'].lower()}.")
    if pending and not highlights:
        findings.append("O resumo registra pendências, mas não há documentos individualizados suficientes para apontar notas específicas.")

    impacts = [
        {"descricao": _text(part.get("descricao"), 120),
         "valor": _brl(part.get("valor"))}
        for part in composition.get("itens", [])
        if isinstance(part, dict) and abs(_amount(part.get("valor"))) >= Decimal("0.005")
    ][:5]

    actions = []
    for entry in highlights[:3]:
        parts = [entry["documento"]]
        if entry["conta_candidata"]:
            parts.append("possível conta " + entry["conta_candidata"])
        if entry["data"]:
            parts.append(entry["data"])
        actions.append({
            "acao": "Verifique " + " · ".join(parts) + f" ({entry['referencia']})",
            "objetivo": entry["como_verificar"],
        })
    if not actions and pending:
        actions.append({
            "acao": "Identifique as notas ainda pendentes dos acumuladores " + str(item.get("acumuladores") or "da conta"),
            "objetivo": "Levante número, série, data e valor dos documentos pendentes e pesquise os registros correspondentes nas contas do Razão.",
        })
    if ledger and len(actions) < 3:
        actions.append({
            "acao": f"Revise os {ledger} movimentos contábeis sem vínculo confirmado",
            "objetivo": "Separe reconhecimento da operação, liquidações e eventuais estornos usando os históricos e contrapartidas.",
        })
    if not actions:
        actions = list(old_reading.get("orientacoes") or [])[:2]

    sample_partial = bool(coverage.get("amostra"))
    return {
        "resultado": headline,
        "observacoes": findings,
        "orientacoes": actions[:3],
        "destaques": highlights,
        "impactos": impacts,
        "resumo_conciliacao": {"total": total, "conciliados": reconciled,
                             "documentos_pendentes": pending, "movimentos_pendentes": ledger},
        "cobertura_documental": {"amostra": sample_partial,
                                 "documentos_enviados": coverage.get("documentos_enviados"),
                                 "documentos_pendentes": coverage.get("documentos_pendentes")},
        "considerados": old_reading.get("considerados", []),
        "excluidos": old_reading.get("excluidos", []),
        "criterio": ("Prioridades geradas a partir do cruzamento local. "
                    "Documentos e contas candidatas são indícios, não vínculos comprovados."
                    + (" Foram exibidos exemplos de uma amostra de pendências." if sample_partial else "")),
        "documental_especifico": True,
    }

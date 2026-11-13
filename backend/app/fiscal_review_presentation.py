"""Prioridades e referências locais: nenhum fato é extraído da narrativa da IA."""
from decimal import Decimal, InvalidOperation
import re


def amount(value):
    if value is None or value == "":
        return None
    try:
        text = str(value).replace("R$", "").replace(" ", "")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        result = Decimal(text)
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


ORDER = {name: index for index, name in enumerate(("VALOR_DIFERENTE", "CONTA_DIFERENTE",
    "ESTORNO_EM_ANALISE", "DATA_DIFERENTE", "SEM_LANCAMENTO_IDENTIFICADO", "AMBIGUO", "PROVAVEL"))}
REASONS = {
    "VALOR_DIFERENTE": "O cruzamento identificou valores diferentes. Confira os maiores desvios disponíveis antes de investigar a causa.",
    "CONTA_DIFERENTE": "Há candidato em outra conta: confirmar esse vínculo pode esclarecer a seleção sem criar outro lançamento.",
    "ESTORNO_EM_ANALISE": "Um possível redutor exige relacionar a operação original e conferir seu efeito no período.",
    "DATA_DIFERENTE": "A divergência de data exige conferir emissão, entrada e competência antes de alterar o período.",
    "SEM_LANCAMENTO_IDENTIFICADO": "Falta identificar o vínculo. Os maiores valores fiscais disponíveis aparecem primeiro; não são perdas nem omissões comprovadas.",
    "AMBIGUO": "Há mais de um candidato; faltam identificadores para escolher o vínculo com segurança.",
    "PROVAVEL": "O vínculo ainda depende de confirmação documental, mesmo quando os valores coincidem.",
}


def impact(doc):
    fiscal, ledger = amount(doc.get("valor_brl")), amount(doc.get("valor_razao_candidato_brl"))
    difference = amount(doc.get("diferenca_candidato_brl"))
    if doc.get("situacao") == "VALOR_DIFERENTE":
        if difference is not None:
            return abs(difference)
        if fiscal is not None and ledger is not None:
            return abs(ledger-fiscal)
        return Decimal("-1")
    return abs(fiscal) if fiscal is not None else Decimal("-1")



def enrich_review(reading, item, rows):
    documents = (item.get("parecer") or {}).get("comparacoes_documentais", [])
    sources = {str(d.get("referencia")): d for d in documents if d.get("referencia")}
    ledger = {str(r.get("referencia") or r.get("_referencia_ia") or ""): r for r in rows}
    steps = reading.get("orientacoes") or []
    for step in steps:
        category = step.get("categoria", "")
        step["prioridade_motivo"] = REASONS.get(category, "Comece pelos registros identificados e confirme a origem antes de propor uma correção.")
        examples = step.get("documentos") or []
        if not examples:
            refs = [reference for reference in re.findall(r"\bL\d+\b", str(step.get("acao") or "")) if reference in ledger]
            step["onde_conferir"] = "Razão da conta " + str(item.get("conta") or "selecionada") + (", referências " + ", ".join(dict.fromkeys(refs)) if refs else "") + ". Detalhamento dos acumuladores " + str(item.get("acumuladores") or "vinculados") + "."

        examples.sort(key=lambda example: -impact(sources.get(str(example.get("referencia")), {})))
        for example in examples:
            doc = sources.get(str(example.get("referencia")), {})
            reference = str(doc.get("razao_id") or "")
            movement = ledger.get(reference, {})
            location = ["Detalhamento fiscal do acumulador " + str(doc.get("acumulador") or item.get("acumuladores") or "selecionado")]
            if reference or doc.get("conta_razao_candidato"):
                location.append("Razão: conta candidata " + str(doc.get("conta_razao_candidato") or item.get("conta") or "selecionada")
                                + (", referência " + reference if reference else ""))
            else:
                location.append("Razão completo: pesquise número, série, parceiro e competência; não há lançamento individual confirmado nesta seleção")
            example["onde_conferir"] = ". ".join(location) + "."
            example["campos_a_confirmar"] = "Confirme no documento original: número, série, parceiro e natureza da operação; depois confronte valor e competência."
            if movement.get("historico"):
                example["historico_candidato"] = str(movement["historico"])[:240]
            example["vinculo"] = "Candidato a confirmar; a referência no relatório não comprova a mesma operação."
    steps.sort(key=lambda step: (ORDER.get(step.get("categoria"), 99),
        -max((impact(sources.get(str(d.get("referencia")), {})) for d in step.get("documentos", [])), default=Decimal("-1"))))
    for index, step in enumerate(steps, 1):
        step["ordem_revisao"] = index
    reading["criterio_prioridade"] = "Diferenças de valor identificadas primeiro; depois vínculos em outra conta, redutores, datas e vínculos incertos. Dentro de cada situação, maior diferença disponível ou valor fiscal a conferir. A prioridade organiza a revisão, não mede certeza de erro."
    return reading

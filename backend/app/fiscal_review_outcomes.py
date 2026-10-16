"""Conclusões numéricas e critérios de revisão, sem inferir causa contábil."""
from decimal import Decimal, InvalidOperation


OUTCOMES = {
    "VALOR_DIFERENTE": (
        "Confirme que a nota e o lançamento candidato são da mesma operação e identifique no documento o componente que explica a diferença.",
        "Se a série, o parceiro ou a operação forem diferentes, descarte esse candidato e procure outro vínculo; não ajuste apenas para fechar o total."),
    "CONTA_DIFERENTE": (
        "Confirme o mesmo documento na conta candidata e confronte a natureza da operação com o mapeamento do acumulador.",
        "Se o lançamento pertencer a outra operação ou a classificação estiver correta, descarte a hipótese de mapeamento incorreto."),
    "DATA_DIFERENTE": (
        "Confirme emissão, entrada e competência nos documentos originais e determine em qual período a mesma operação foi escriturada.",
        "Se o registro não for da mesma operação, descarte o candidato; datas diferentes, sozinhas, não justificam mudar a competência."),
    "ESTORNO_EM_ANALISE": (
        "Vincule o redutor ao documento original e confirme motivo, valor e competência do estorno ou devolução.",
        "Se o redutor for de outra operação, descarte a compensação entre esses registros."),
    "AMBIGUO": (
        "Use série, parceiro e documento de origem para distinguir os candidatos e confirmar um vínculo individual ou um desdobramento documentado.",
        "Se mais de um candidato continuar compatível, mantenha a pendência; a semelhança não comprova duplicidade."),
    "PROVAVEL": (
        "Confira no documento de origem se o número do histórico representa a nota fiscal e se os demais campos identificam a mesma operação.",
        "Se o número representar outro documento, descarte essa correspondência e refaça a busca."),
    "SEM_LANCAMENTO_IDENTIFICADO": (
        "Pesquise a nota por número, série, parceiro e competência no Razão da filial; registre os critérios e a cobertura da busca.",
        "Se localizar a operação em outro histórico, conta ou período, descarte a hipótese de ausência baseada apenas nesta seleção."),
    "MOVIMENTO_SEM_VINCULO": (
        "Identifique o comprovante e confirme se o movimento reconhece uma operação, liquida obrigação anterior ou reduz outro lançamento.",
        "Se for liquidação de operação já reconhecida, não o some novamente ao fiscal; valide a contrapartida antes de alterar a comparação."),
}


def review_outcome(status):
    values = OUTCOMES.get(status)
    return {"para_concluir": values[0], "quando_reavaliar": values[1]} if values else {}


def executive_summary(item, reading, *, partial=False):
    values = item.get("valores") or {}
    if "diferenca" not in values:
        return {}
    try:
        difference = Decimal(str(values["diferenca"]))
        if not difference.is_finite():
            return {}
        difference = difference.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return {}
    amount = "R$ " + f"{abs(difference):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if difference:
        title = "Diferença identificada"
        direction = "acima" if difference > 0 else "abaixo"
        conclusion = f"O contábil considerado está {amount} {direction} do fiscal."
    else:
        title = "Totais iguais; confirme os vínculos"
        conclusion = "Não há diferença numérica entre o fiscal e o contábil considerado. Isso não confirma os vínculos individuais."
    steps = reading.get("orientacoes") or []
    first = steps[0] if steps else {}
    documents = first.get("documentos") or []
    coverage = item.get("cobertura_documental") or {}
    is_partial = partial or bool(coverage.get("amostra"))
    return {"titulo": title, "conclusao": conclusion,
        "foco": first.get("acao") or "Identifique os documentos e movimentos que compõem a comparação",
        "primeiro_passo": first.get("objetivo") or "Compare a origem dos registros antes de propor ajuste.",
        "exemplos": [str(d.get("titulo") or d.get("referencia")) for d in documents[:2] if d.get("titulo") or d.get("referencia")],
        "cobertura": "Contexto parcial da IA" if is_partial else "Contexto selecionado disponível",
        "parcial": is_partial, "origem": "Calculado pelo Razync a partir dos relatórios"}

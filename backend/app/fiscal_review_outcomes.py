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



# Orientações condicionais para pendências efetivamente identificadas no cruzamento.
# Não são conclusões do modelo nem autorização para alterar a escrituração.
PRACTICAL_GUIDES = {
    "VALOR_DIFERENTE": (
        "A nota tem um possível lançamento no Razão, mas os valores comparados são diferentes. Isso identifica a diferença de valor, ainda sem comprovar o motivo.",
        "Se o documento original comprovar erro no valor registrado, corrija o registro de origem com essa documentação. Se houver parcelas ou redutores da mesma operação, confirme e vincule o conjunto antes de tratar o saldo como erro. Não crie um ajuste só para igualar os totais.",
        "Refaça a conferência da nota e verifique se os valores documentados coincidem; explique qualquer diferença que permanecer."),
    "CONTA_DIFERENTE": (
        "A busca encontrou um lançamento compatível em outra conta. A operação pode estar registrada, embora não apareça na conta vinculada ao acumulador.",
        "Se for a mesma operação e a conta candidata estiver correta, revise o vínculo entre acumulador e conta. Se a revisão do documento e do plano de contas confirmar classificação incorreta, providencie a correção justificada na escrituração. Não registre a operação outra vez.",
        "Execute novamente a comparação e confirme que o documento aparece na conta validada, uma única vez."),
    "DATA_DIFERENTE": (
        "Há um possível lançamento para a nota com data diferente. A diferença pode ser de escrituração ou competência e precisa ser esclarecida no documento.",
        "Se a data registrada estiver errada conforme o documento e a revisão da competência, corrija o campo de origem. Se as datas forem válidas para etapas diferentes da operação, registre a justificativa e compare os períodos compatíveis, sem mudar a data apenas para fechar a conferência.",
        "Confira novamente documento, data e competência e veja se a diferença de período foi resolvida ou justificada."),
    "ESTORNO_EM_ANALISE": (
        "O cruzamento encontrou indício de estorno, cancelamento ou redutor. O efeito depende de confirmar a relação com a operação original.",
        "Depois de confirmar o documento original e o redutor, relacione os dois e confira o efeito líquido e a competência. Se o comprovante demonstrar valor ou período incorreto, corrija o registro de origem; se não houver vínculo, mantenha as operações separadas.",
        "A comparação deve refletir somente os efeitos documentados no período, sem contar o original ou o estorno em duplicidade."),
    "AMBIGUO": (
        "Mais de um lançamento pode corresponder ao documento. A ferramenta ainda não tem elementos suficientes para escolher um deles.",
        "Use série, parceiro e documento de origem para selecionar o vínculo correto ou comprovar um desdobramento. Se a dúvida continuar, mantenha a pendência; não exclua um registro como duplicado apenas pela semelhança.",
        "O vínculo precisa ficar individualizado e explicado pelos documentos, sem usar a mesma parcela em operações diferentes."),
    "PROVAVEL": (
        "O histórico sugere uma correspondência, mas o documento original ainda não confirmou o vínculo.",
        "Se número, série, parceiro e operação forem confirmados, valide a correspondência. Se o número do histórico representar outro documento, descarte esse candidato e refaça a busca.",
        "A nota deve ficar relacionada ao lançamento da mesma operação, com os campos de identificação conferidos."),
    "SEM_LANCAMENTO_IDENTIFICADO": (
        "A nota não foi associada a um lançamento pelos critérios usados. Isso ainda não significa que ela esteja ausente de todo o Razão.",
        "Se localizar o registro em outra conta ou período, revise o vínculo ou justifique a competência, sem lançar a operação outra vez. Só encaminhe um registro faltante para regularização após confirmar o documento e concluir a busca na escrituração completa.",
        "Refaça a busca e documente onde a operação foi localizada ou a evidência que sustenta a regularização."),
    "MOVIMENTO_SEM_VINCULO": (
        "Existe um movimento no Razão que ainda não foi relacionado aos documentos fiscais anexados.",
        "Se o comprovante mostrar pagamento ou baixa de operação já reconhecida, mantenha a liquidação separada do reconhecimento fiscal. Se corresponder a um documento do período ainda não vinculado, relacione-o após confirmar a origem. A falta de vínculo não autoriza excluir o movimento.",
        "O movimento deve ter origem identificada e tratamento explicado, sem duplicar o valor fiscal."),
    "SELECAO_HISTORICO": (
        "Há movimentos na conta que o filtro de históricos deixou fora do valor comparado. O alerta pode ser da seleção, e não de falta de escrituração.",
        "Se os documentos comprovarem que um movimento separado pertence à operação fiscal comparada, revise o critério de seleção ou identificação desse registro. Se for pagamento ou baixa de operação já reconhecida, preserve essa separação. Não altere o Razão para corrigir apenas um filtro.",
        "Confira novamente o total examinado, os movimentos separados e o valor selecionado; a diferença restante precisa corresponder aos documentos."),
    "VINCULO_POR_VALOR": (
        "Um ou mais movimentos entraram na comparação apenas porque os valores fecham. A igualdade, sozinha, ainda não comprova a relação com as notas.",
        "Confirme os documentos antes de validar esses vínculos. Se forem operações diferentes, desfaça a associação na conferência e procure o lançamento correto, preservando a escrituração até comprovar uma inconsistência de origem.",
        "Cada valor considerado precisa ter documento e operação identificados, além de igualdade numérica."),
    "REGISTROS_SEMELHANTES": (
        "Foram encontrados registros com campos repetidos. Eles podem representar operações distintas, parcelas ou um par de lançamento e estorno.",
        "Compare os documentos de origem antes de tratar repetição como erro. Somente se a revisão comprovar registro indevido, encaminhe a correção documentada; caso contrário, mantenha e explique os registros distintos.",
        "Cada registro deve ter origem comprovada ou uma correção justificada, sem exclusão por simples semelhança."),
    "DETALHAMENTO_NECESSARIO": (
        "O resumo mostra o total fiscal, mas não identifica sozinho quais documentos explicam a diferença.",
        "Obtenha o detalhamento dos acumuladores ou anexe Entradas e Saídas e localize as operações na conta. Com a evidência atual, a próxima ação é identificar a origem da diferença; ainda não há base para indicar um lançamento corretivo específico.",
        "A revisão deve produzir uma lista de documentos vinculados e pendências identificadas antes de propor qualquer ajuste."),
}


def review_outcome(status):
    values = OUTCOMES.get(status)
    result = {"para_concluir": values[0], "quando_reavaliar": values[1]} if values else {}
    guide = PRACTICAL_GUIDES.get(status)
    if guide:
        result.update(explicacao_simples=guide[0], solucao_condicional=guide[1], resultado_esperado=guide[2])
    return result


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
        conclusion = f"O valor do Razão usado nesta comparação está {amount} {direction} do fiscal."
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
        "cobertura": "Conferência local" if item.get("provedor") == "local" else "Contexto parcial da IA" if is_partial else "Contexto selecionado disponível",
        "parcial": is_partial, "origem": "Calculado pelo Razync a partir dos relatórios"}

"""Dossiê contábil determinístico por conta/tipo para a IA fiscal.

Transforma os cruzamentos JÁ realizados pelo Razync em pistas verificáveis.
Não concilia novos documentos, não infere causa por diferença e não altera
totais, seleção fiscal ou regras de classificação.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import re


def _text(value):
    return str(value or "").strip()


def _money(value):
    try:
        number = Decimal(str(value or 0))
        return number if number.is_finite() else Decimal(0)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _unique_append(items, item, max_items=4):
    if len(items) < max_items and item not in items:
        items.append(item)


def build_dossier(account, records, documents=None, documentary=None, coverage=None):
    """Não gera fatos novos: referências, padrões e contagens das fontes fornecidas."""
    documents = documents or []
    documentary = documentary or {}
    coverage = coverage or {}
    kind = _text(account.get("tipo"))
    side = "credito" if kind == "SAÍDAS" else "debito"
    refs = [str(row.get("_referencia_ia") or row.get("referencia") or "")
            for row in records]
    classification = Counter(_text(row.get("classificacao")) for row in records
                             if _text(row.get("classificacao")))
    # Contagens identificadas no universo recebido, não evidência de fraude.
    signal = Counter()
    notable = []
    signatures = Counter()
    for row, ref in zip(records, refs):
        history = _text(row.get("historico"))
        classification_name = _text(row.get("classificacao"))
        if classification_name == "ALERTA - NÃO FISCAL":
            signal["separados_na_comparacao"] += 1
            _unique_append(notable, {"referencia": ref, "indicio": "fora da comparação fiscal"}, 3)
        if classification_name == "FECHAMENTO POR VALOR - VALIDAR":
            signal["incluidos_so_por_valor"] += 1
            _unique_append(notable, {"referencia": ref, "indicio": "inclusão por valor sem vínculo documental comprovado"}, 3)
        if re.search(r"\b(estorn\w*|cancel\w*|devolu\w*)\b", history, re.I):
            signal["historicos_de_estorno_cancelamento"] += 1
            _unique_append(notable, {"referencia": ref, "indicio": "histórico menciona estorno ou cancelamento"}, 3)
        if history:
            signature = (_text(row.get("data")), history.casefold(),
                         _text(row.get("contrapartida")),
                         str(_money(row.get(side))))
            signatures[signature] += 1

    repeated = sum(1 for n in signatures.values() if n > 1)
    if repeated:
        signal["assinaturas_repetidas"] = repeated

    doc_counter = Counter(_text(doc.get("situacao")).upper() for doc in documents)
    candidates = []
    priorities = []
    for status, title, target in (
        ("VALOR_DIFERENTE", "Documento com diferença de valor", "Compare o valor da nota com o movimento candidato, considerando estornos e desdobramentos."),
        ("CONTA_DIFERENTE", "Documento com candidato em outra conta", "Confirme nota, parceiro e contrapartida antes de avaliar o mapeamento da conta."),
        ("DATA_DIFERENTE", "Documento com datas divergentes", "Compare emissão, competência e data de escrituração com o movimento candidato."),
        ("ESTORNO_EM_ANALISE", "Documento com estorno a conferir", "Identifique original, estorno e efeito no período antes de classificar o ajuste."),
        ("SEM_LANCAMENTO_IDENTIFICADO", "Documento sem candidato localizado", "Pesquise número e série da nota nas outras contas e no período correspondente; ausência aqui não prova omissão."),
        ("AMBIGUO", "Documento com correspondências ambíguas", "Diferencie candidatos pela série, emitente e valor da operação."),
    ):
        candidates_for_status = [doc for doc in documents if _text(doc.get("situacao")).upper() == status]
        if not candidates_for_status:
            continue
        selected = candidates_for_status[0]
        reference = _text(selected.get("referencia"))
        candidate = {
            "situacao": status, "referencia": reference,
            "nota": _text(selected.get("nota")),
            "acumulador": _text(selected.get("acumulador")),
        }
        if selected.get("conta_razao_candidato"):
            candidate["conta_razao_candidato"] = _text(selected["conta_razao_candidato"])
        if selected.get("razao_id"):
            candidate["razao_id"] = _text(selected["razao_id"])
        candidates.append(candidate)
        _unique_append(priorities, {
            "origem": "documento_pendente", "referencia": reference,
            "acao": title, "como_verificar": target,
        }, 3)

    for observed, title, action in (
        ("separados_na_comparacao", "Movimentos separados do total fiscal", "Verifique se o registro representa pagamento, baixa ou reconhecimento da operação, usando histórico e contrapartida."),
        ("incluidos_so_por_valor", "Movimentos incluídos apenas para fechamento", "Compare a nota e a natureza antes de tratá-los como fiscalmente vinculados."),
        ("historicos_de_estorno_cancelamento", "Estornos e cancelamentos mencionados", "Localize o lançamento original e identifique em qual período cada efeito foi registrado."),
        ("assinaturas_repetidas", "Assinaturas contábeis repetidas", "Compare documentos distintos ou lançamento/estorno antes de concluir duplicidade."),
    ):
        if signal[observed] and len(priorities) < 3:
            refer = next((item["referencia"] for item in notable
                          if (observed == "separados_na_comparacao" and "fora" in item["indicio"])
                          or (observed == "incluidos_so_por_valor" and "valor" in item["indicio"])
                          or (observed == "historicos_de_estorno_cancelamento" and "estorno" in item["indicio"])), "")
            _unique_append(priorities, {"origem": "razao", "referencia": refer,
                                        "acao": title, "como_verificar": action}, 3)

    if not priorities:
        # Direção útil mesmo quando a origem ainda não está demonstrada.
        acc = _text(account.get("acumuladores")) or "vinculados"
        priorities.append({"origem": "resumo_fiscal", "referencia": "",
            "acao": f"Identifique os documentos dos acumuladores {acc}",
            "como_verificar": "Obtenha número, série, competência e valor e compare com os registros da conta. O resumo por acumulador não comprova vínculo individual."})

    limits = []
    if not documents and not documentary:
        limits.append("O resumo fiscal não fornece notas individuais para estabelecer a origem da diferença.")
    if coverage.get("amostra"):
        limits.append("Há pendências fora da amostra enviada ao provedor; não generalize os exemplos.")
    if any(not _text(row.get("historico")) for row in records):
        limits.append("Existem movimentos sem histórico suficiente para identificar a operação.")
    if not records:
        limits.append("Não há lançamentos desta conta/natureza no contexto enviado.")
    details = account.get("detalhes_fiscais") or []
    return {
        "conta": _text(account.get("conta")),
        "tipo": kind,
        "lado_contabil_comparado": "CRÉDITO" if side == "credito" else "DÉBITO",
        "situacao": _text(account.get("situacao")),
        "acumuladores_fiscais": [
            {"codigo": _text(x.get("codigo")), "valor": x.get("valor")}
            for x in details[:8] if isinstance(x, dict)
        ],
        "razao": {"movimentos_recebidos": len(records), "classificacoes": dict(classification.most_common(5)),
                  "indicadores": dict(signal), "exemplos_referenciados": notable},
        "documentos": {"situacoes_na_amostra": dict(doc_counter),
                       "resumo_do_cruzamento_local": {
                           k: documentary.get(k) for k in
                           ("documentos_lidos", "conciliados", "documentos_pendentes", "movimentos_pendentes")
                           if k in documentary},
                       "composicao_local": documentary.get("composicao", {}),
                       "cobertura": coverage,
                       "candidatos_a_verificar": candidates[:4]},
        "prioridades_de_investigacao": priorities,
        "limites_das_fontes": limits,
    }

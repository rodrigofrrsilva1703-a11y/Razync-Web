"""Read-only account investigation. All amounts and conclusions originate locally."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import hmac
import json
import secrets
import threading
import time

from app import ai_result_cache

RULES_VERSION = "fiscal-hybrid-2"
_secret = secrets.token_bytes(32)
_guard = threading.RLock()
_cache = {}
_inflight = set()
CACHE_SECONDS = 1800
MAX_CACHE = 64
MAX_EVIDENCE = 120


def cents(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or abs(number) >= Decimal("1e15"):
            raise ValueError()
        return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Valor monetário inválido ou ausente; confira o relatório de origem.") from None


def money(value):
    return format(Decimal(value) / 100, ".2f")


def day(value):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def adjacent_ledger(content, name, report, account, tipo):
    """Read adjacent months from the SAME already-validated file, without changing totals."""
    from app.fiscal_242 import _csv_para_excel
    from razync.conferencia_fiscal import ler_razao
    import pandas as pd
    branch = str(report.get("filial_aplicada") or "")
    period = report.get("periodo_fiscal", {})
    start, end = day(period.get("inicio")), day(period.get("fim"))
    if not branch or not start or not end:
        return []
    raw, filename = _csv_para_excel(content, name)
    frame, _ = ler_razao(raw, filename)
    if "FILIAL" not in frame:
        return []
    selected = frame.loc[frame["FILIAL"].astype(str).eq(branch) & frame["CONTA"].astype(str).eq(account)]
    side = "CRÉDITO" if tipo == "SAÍDAS" else "DÉBITO"
    output = []
    for index, move in selected.iterrows():
        parsed = pd.to_datetime(move.get("DATA"), errors="coerce")
        if pd.isna(parsed):
            continue
        date = parsed.date()
        distance = min(abs(date.year*12+date.month - boundary.year*12-boundary.month) for boundary in (start,end))
        if start <= date <= end or distance != 1:
            continue
        amount = cents(move.get(side, 0))
        if amount:
            output.append({"referencia": f"A-{index}", "conta": account, "filial": branch,
                "data": date.strftime("%d/%m/%Y"), "valor": money(amount),
                "historico": str(move.get("HISTÓRICO", "")), "contrapartida": str(move.get("CONTRAPARTIDA", ""))})
    return output


def combinations(target, records):
    """Bounded signed cent arithmetic; coincidences never establish a document link."""
    selected = records
    found, seen = [], set()
    operations = 0
    def add(items):
        refs = tuple(sorted(r["referencia"] for r in items))
        if refs not in seen and len(found) < 5:
            seen.add(refs)
            found.append({"referencias": list(refs), "soma": money(sum(r["centavos"] for r in items)),
                          "residual": money(target - sum(r["centavos"] for r in items))})
    by_value = defaultdict(list)
    for item in selected:
        operations += 1
        if item["centavos"] == target:
            add([item])
        for previous in by_value.get(target - item["centavos"], [])[:5]:
            if previous["referencia"] != item["referencia"]:
                add([previous, item])
        if len(by_value[item["centavos"]]) < 5:
            by_value[item["centavos"]].append(item)
    # Singles and pairs scan the entire input in O(n). Only triple enumeration is bounded.
    triples = sorted(selected, key=lambda r: (min(abs(r["centavos"]),abs(target-r["centavos"])),r["referencia"]))[:60]
    for i, first in enumerate(triples):
        for j in range(i + 1, len(triples)):
            second = triples[j]
            operations += 1
            for third in by_value.get(target-first["centavos"]-second["centavos"], [])[:5]:
                if third["referencia"] not in {first["referencia"], second["referencia"]}:
                    add([first, second, third])
            if len(found) >= 5:
                break
        if len(found) >= 5:
            break
    return {"resultados": found, "candidatos_testados": len(selected), "candidatos_disponiveis": len(records),
            "operacoes": operations, "limite_candidatos_trios": 60, "max_parcelas": 3,
            "busca_limitada": len(records) > 60, "criterio": "Coincidência aritmética; vínculo documental a confirmar."}


def diagnostic_bridge(row, records, docs, documentary):
    """Independently verify the existing partition, never sum overlapping hypotheses."""
    fiscal, considered = cents(row["fiscal"]), cents(row["contabil"])
    difference = considered - fiscal
    read = sum(cents(d["valor"]) for d in docs)
    items = []
    composition = (documentary or {}).get("composicao", {})
    for item in composition.get("itens", []):
        items.append({"codigo": str(item["codigo"]), "descricao": str(item["descricao"]), "valor": money(cents(item["valor"]))})
    total = sum(cents(item["valor"]) for item in items)
    return {"disponivel": bool(items), "itens": items, "soma_componentes": money(total),
            "residual": money(difference-total), "fecha_aritmeticamente": bool(items) and total == difference,
            "documentos_lidos": money(read) if documentary else None,
            "lacuna_documental": money(fiscal-read) if documentary else None,
            "razao_examinado": money(sum(r["centavos"] for r in records)),
            "vinculos_incertos": bool(composition.get("vinculos_incertos")),
            "limite": "O fechamento explica a composição matemática, não comprova a causa ou a natureza contábil."}


def select_evidence(hypotheses, evidence):
    """Every displayed hypothesis must have ALL its original references displayed."""
    sources = {item["referencia"]: item for item in evidence}
    ordered = sorted(hypotheses, key=lambda h: (-h.get("impacto_centavos", 0), h["id"]))
    representatives, seen = [], set()
    for item in ordered:
        if item["categoria"] not in seen:
            representatives.append(item)
            seen.add(item["categoria"])
    chosen_ids = {h["id"] for h in representatives}
    ordered = representatives + [h for h in ordered if h["id"] not in chosen_ids]
    chosen, used = [], set()
    for item in ordered:
        refs = set(item["referencias"])
        if not refs or not refs.issubset(sources) or len(used | refs) > MAX_EVIDENCE or len(chosen) >= 80:
            continue
        chosen.append(item)
        used.update(refs)
    selected = [sources[ref] for ref in sorted(used)]
    selected.extend(e for ref,e in sources.items() if ref not in used and len(selected) < MAX_EVIDENCE)
    return chosen, selected, len(sources)


def investigate(report, scope, documentary=None):
    rows = [r for r in report.get("contas", []) if str(r.get("conta")) == scope["conta"] and r.get("tipo") == scope["tipo"]]
    if len(rows) != 1:
        raise ValueError("Conta e natureza não encontradas no relatório desta empresa.")
    row = rows[0]
    fiscal, ledger = cents(row.get("fiscal")), cents(row.get("contabil"))
    difference = ledger - fiscal
    limits = list(report.get("avisos", []))
    hypotheses, evidence, records = [], [], []
    examined = invalid_dates = 0
    side = "credito" if scope["tipo"] == "SAÍDAS" else "debito"
    def hypothesis(category, title, explanation, refs, confirmation, **extra):
        hypotheses.append({"id": f"H{len(hypotheses)+1}", "categoria": category, "titulo": title,
            "grau": "hipotese", "explicacao": explanation, "referencias": list(dict.fromkeys(refs)),
            "falta_confirmar": confirmation, **extra})
    def add_evidence(ref, source, data, amount=None):
        evidence.append({"referencia": ref, "origem": source, "data": str(data.get("data", "")),
            "historico": str(data.get("historico", "")), "nota": str(data.get("nota", "")),
            "serie": str(data.get("serie", "")), "conta": str(data.get("conta", scope["conta"])),
            "acumulador": str(data.get("acumulador", "")), "contrapartida": str(data.get("contrapartida", "")),
            "valor": money(amount) if amount is not None else None})
    # Accumulator-only selection cannot attribute unrelated account movements to this accumulator.
    allowed_refs = None
    if scope.get("acumulador") and documentary:
        allowed_refs = {m.get("id") for c in documentary.get("comparacoes", []) for m in c.get("lancamentos", [])
                        if str(m.get("conta", scope["conta"])) == scope["conta"]}
    for index, move in enumerate(report.get("lancamentos", []), 1):
        if str(move.get("conta")) != scope["conta"] or move.get("_tipo_ia", scope["tipo"]) != scope["tipo"]:
            continue
        if allowed_refs is not None and f"R-{index}" not in allowed_refs:
            continue
        if move.get("empresa_codigo") and str(move["empresa_codigo"]) != str(report.get("empresa", "")):
            raise ValueError("Lançamento de outra empresa detectado; a investigação foi interrompida.")
        if move.get("filial") and str(move["filial"]) != str(report.get("filial_aplicada", "")):
            raise ValueError("Lançamento de outra filial detectado; a investigação foi interrompida.")
        amount = cents(move.get(side, 0))
        if not amount:
            continue
        examined += 1
        ref = f"R-{index}"
        record = {**move, "referencia": ref, "centavos": amount}
        records.append(record)
        add_evidence(ref, "Razão", move, amount)
        if not day(move.get("data")):
            invalid_dates += 1
    if invalid_dates:
        limits.append(f"{invalid_dates} lançamento(s) com data inválida ou ausente; competência não confirmada nesses registros.")
    duplicate_groups = defaultdict(list)
    for record in records:
        # Equal values alone are deliberately insufficient even to flag repetition.
        if day(record.get("data")) and str(record.get("historico", "")).strip():
            duplicate_groups[(record.get("data"), record["centavos"], str(record.get("historico")).strip(),
                              str(record.get("contrapartida", "")))].append(record["referencia"])
    for refs in duplicate_groups.values():
        if len(refs) > 1:
            hypothesis("duplicidade", "Registros com os mesmos campos", "Data, valor, histórico e contrapartida se repetem. Isso pode representar parcelas ou operações legítimas; não comprova duplicidade.", refs,
                       "Compare o documento original, a série, o parceiro e a identificação de cada lançamento antes de excluir qualquer registro.")
    period = report.get("periodo_fiscal", {})
    start, end = day(period.get("inicio")), day(period.get("fim"))
    outside = [r["referencia"] for r in records if day(r.get("data")) and start and end and not start <= day(r["data"]) <= end]
    if outside:
        hypothesis("competencia", "Movimentos fora do período fiscal", "As datas dos registros indicados ficam fora do período fiscal informado. A competência correta ainda precisa ser validada.", outside,
                   "Confirme emissão, entrada e competência; envie também a competência adjacente se ela não estiver nos arquivos.")
    docs = documentary.get("documentos", []) if documentary else []
    counts = documentary.get("resumo", {}) if documentary else {}
    labels = {
        "VALOR_DIFERENTE": ("valor_diferente", "Documento com valor divergente"),
        "CONTA_DIFERENTE": ("classificacao", "Candidato em outra conta"),
        "DATA_DIFERENTE": ("competencia", "Documento com data diferente"),
        "SEM_LANCAMENTO_IDENTIFICADO": ("ausente", "Documento sem vínculo identificado"),
        "ESTORNO_EM_ANALISE": ("estorno", "Original e redutores a revisar"),
        "AMBIGUO": ("ambiguo", "Mais de uma correspondência possível"),
        "PROVAVEL": ("ambiguo", "Vínculo sugerido pelo histórico"),
    }
    for doc in docs:
        if doc.get("filial") and str(doc["filial"]) != str(report.get("filial_aplicada", "")):
            raise ValueError("Documento de outra filial detectado; confira o acompanhamento fiscal.")
        if doc.get("empresa_codigo") and str(doc["empresa_codigo"]) != str(report.get("empresa", "")):
            raise ValueError("Documento de outra empresa detectado; confira o acompanhamento fiscal.")
        if scope.get("acumulador") and str(doc.get("acumulador")) != scope["acumulador"]:
            raise ValueError("Documento de outro acumulador detectado no recorte.")
        add_evidence(doc["id"], "Fiscal", doc, cents(doc.get("valor")))
    for comparison in documentary.get("comparacoes", []) if documentary else []:
        status = comparison.get("situacao")
        if status not in labels:
            continue
        category, title = labels[status]
        fiscal_date = day(comparison.get("data"))
        ledger_dates = [day(m.get("data")) for m in comparison.get("lancamentos", [])]
        if status == "DATA_DIFERENTE" and fiscal_date and ledger_dates and all(
                date and (date.year,date.month) == (fiscal_date.year,fiscal_date.month) for date in ledger_dates):
            category, title = "data", "Datas diferentes na mesma competência"
        refs = [p["id"] for p in comparison.get("linhas_fiscais", [])]
        for movement in comparison.get("lancamentos", []):
            ref = str(movement.get("id", ""))
            if ref:
                refs.append(ref)
                add_evidence(ref, "Razão candidato", movement, cents(movement.get("valor")))
        delta = comparison.get("diferenca")
        confirmations = {
            "ausente": "Busque nota, série e parceiro no Razão completo da mesma filial. Se localizar a operação, descarte a hipótese de omissão e revise o vínculo.",
            "valor_diferente": "Compare o valor integral da nota, parcelas, descontos e redutores efetivamente documentados. Se os componentes fecharem o valor original, descarte a hipótese de erro no valor.",
            "classificacao": "Confirme nota, série, parceiro e natureza na conta candidata. Só proponha reclassificação se o vínculo e o mapeamento do acumulador forem confirmados.",
            "competencia": "Confirme emissão, entrada e competência de escrituração. Uma data de pagamento diferente não determina a competência da operação.",
            "data": "Confirme qual data cada relatório usa. Como o mês e o ano coincidem, a diferença de dia sozinha não explica deslocamento de competência.",
            "estorno": "Confira o vínculo de cada redutor com a nota original e some o efeito líquido antes de sugerir inclusão ou exclusão.",
            "ambiguo": "Distinga os candidatos por documento original, série e parceiro. Sem correspondência única, não escolha um lançamento só pelo valor.",
        }
        hypothesis(category, title,
            {"ausente": "O cruzamento não identificou correspondência nos dados disponíveis; isso não prova ausência na escrituração.",
             "competencia": "Há indício de vínculo com data diferente. Confirme a competência; uma data diferente não comprova erro.",
             "classificacao": "Há candidato em outra conta. O vínculo e o mapeamento do acumulador dependem de confirmação."}.get(category,
             "O cruzamento documental encontrou uma pendência nos campos indicados. O indício não determina a causa contábil."),
            refs, confirmations.get(category, "Confira o documento original antes de propor correção."),
            diferenca_documental=money(cents(delta)) if delta is not None else None,
            impacto_centavos=abs(cents(delta if delta is not None else comparison.get("valor_fiscal", 0))),
            comparacao={"nota": str(comparison.get("nota", "")), "serie": str(comparison.get("serie", "")),
                "data_fiscal": str(comparison.get("data", "")),
                "datas_razao": sorted({str(m.get("data", "")) for m in comparison.get("lancamentos", [])}),
                "contas_candidatas": sorted({str(m.get("conta", scope["conta"])) for m in comparison.get("lancamentos", [])}),
                "fiscal": money(cents(comparison.get("valor_fiscal", 0))),
                "contabil": money(cents(comparison["valor_razao"])) if comparison.get("valor_razao") is not None else None},
            criterio=str(comparison.get("criterio", "")))
    # Existing totals stay scoped to their original period. Adjacent candidates are separate evidence.
    if documentary and report.get("_competencia_adjacente"):
        from app.fiscal_documentos import _nota_historico
        adjacent = defaultdict(list)
        for movement in report["_competencia_adjacente"]:
            if str(movement.get("filial")) != str(report.get("filial_aplicada")) or str(movement.get("conta")) != scope["conta"]:
                continue
            note = _nota_historico(movement.get("historico", ""))
            if note:
                adjacent[(note.lstrip("0"), cents(movement["valor"]))].append(movement)
        for document in docs:
            if document.get("situacao") != "SEM_LANCAMENTO_IDENTIFICADO":
                continue
            matches = adjacent.get((str(document.get("nota", "")).lstrip("0"), cents(document["valor"])), [])
            if len(matches) != 1:
                continue
            movement = matches[0]
            add_evidence(movement["referencia"], "Razão de competência adjacente", movement, cents(movement["valor"]))
            hypothesis("competencia", "Mesma nota e valor em competência adjacente",
                "O mesmo arquivo contém um candidato de outro mês, na mesma conta e filial, com nota explícita e valor compatíveis. O candidato não foi somado à conferência.",
                [document["id"], movement["referencia"]],
                "Confirme série, parceiro e documento original, além de emissão, entrada e competência correta. Se for outra operação, descarte este candidato.",
                impacto_centavos=abs(cents(document["valor"])))
    if not documentary:
        limits.append("Sem acompanhamento de Entradas/Saídas nesta seleção: não há notas individuais para confirmar falta, duplicidade ou vínculo com acumuladores.")
    if not records and ledger:
        limits.append("O total contábil não possui movimentos detalhados suficientes nesta seleção.")
    if not start or not end:
        limits.append("Período fiscal incompleto: a investigação de competência não pode ser concluída.")
    if report.get("movimentos_fora_periodo"):
        limits.append(f"O leitor excluiu {report['movimentos_fora_periodo']} movimento(s) fora do período. Não foram reincorporados aos totais.")
    candidates = records
    if documentary:
        pending = {m["id"] for m in documentary.get("razao_sem_vinculo", [])}
        candidates = [r for r in records if r["referencia"] in pending]
    combo = combinations(difference, candidates) if difference else {"resultados": [], "operacoes": 0, "candidatos_testados": 0}
    for solution in combo["resultados"]:
        hypothesis("combinacao", "Valores que compõem a diferença", "A soma dos registros coincide em centavos com a diferença. É uma identidade aritmética, não prova de lançamento indevido ou de vínculo fiscal.",
                   solution["referencias"], "Confirme a origem e a classificação de cada parcela; não ajuste lançamentos somente pela soma.", soma=solution["soma"], residual=solution["residual"])
    if documentary and difference < 0:
        missing = [{"referencia": d["id"], "centavos": cents(d["valor"])} for d in docs
                   if d.get("situacao") == "SEM_LANCAMENTO_IDENTIFICADO"]
        fiscal_combo = combinations(-difference, missing)
        for solution in fiscal_combo["resultados"]:
            hypothesis("combinacao", "Documentos fiscais que compõem a falta aparente",
                       "A soma dos documentos sem vínculo coincide com o valor pelo qual o contábil está abaixo do fiscal. Isso não comprova omissão na escrituração.",
                       solution["referencias"], "Localize os documentos no Razão completo da mesma filial e confirme a competência antes de propor inclusão.",
                       soma=solution["soma"], residual=solution["residual"])
        combo["fiscal"] = fiscal_combo
    if combo.get("busca_limitada") or combo.get("fiscal", {}).get("busca_limitada"):
        limits.append("Valores individuais e pares foram examinados em todos os candidatos; a busca de trios é limitada a 60 candidatos-base e cinco exemplos. Ausência de solução não descarta outras combinações.")
    bridge = diagnostic_bridge(row, records, docs, documentary)
    if bridge["lacuna_documental"] is not None and cents(bridge["lacuna_documental"]):
        limits.append("Os documentos lidos não reproduzem o total fiscal do resumo. Revise a cobertura e os filtros do acompanhamento antes de atribuir toda a diferença ao Razão.")
    if bridge["disponivel"] and not bridge["fecha_aritmeticamente"]:
        limits.append("A composição documental não reproduz integralmente a diferença inicial; o residual permanece sem explicação aritmética.")
    if not difference and not hypotheses:
        conclusion = "Os totais comparados conferem. Isso não confirma individualmente os documentos nem autoriza ajustes."
        level = "sem_divergencia"
    elif hypotheses:
        conclusion = "Foram encontrados indícios para revisão humana. Nenhuma causa contábil está comprovada pelos arquivos disponíveis."
        level = "hipotese"
    else:
        conclusion = "A diferença foi confirmada aritmeticamente, mas a causa permanece inconclusiva. Complete os documentos e as competências indicados."
        level = "inconclusiva"
    # Only relevant sources are returned; the original reports remain untouched.
    displayed, selected, available = select_evidence(hypotheses, evidence)
    if len(selected) < available or len(displayed) < len(hypotheses):
        limits.append("A apresentação é limitada a 80 indícios e 120 evidências. As contagens locais abrangem os dados examinados; a relação integral permanece no cruzamento documental e nos arquivos originais.")
    return {"versao": RULES_VERSION, "resumo": {"empresa": report.get("empresa"), "empresa_nome": report.get("empresa_nome", ""),
            "filial": report.get("filial_aplicada", ""), "competencia": period, "conta": scope["conta"], "tipo": scope["tipo"],
            "acumulador": scope.get("acumulador") or row.get("acumuladores", ""),
            "fiscal": money(fiscal), "contabil": money(ledger), "diferenca": money(difference)},
        "verificacoes": ["Débito nas entradas / crédito nas saídas, inclusive valores negativos", "Identidade da conta, filial e acumulador",
            "Datas e competência disponíveis", "Repetição de campos no Razão", "Cruzamento documental existente, sem criar vínculos por valor",
            "Combinações limitadas em centavos"],
        "contagens": {"lancamentos_examinados": examined, "documentos_examinados": len(docs),
            "correspondencias": counts.get("conciliados", 0), "datas_invalidas": invalid_dates,
            "evidencias_disponiveis": available, "evidencias_exibidas": len(selected),
            "hipoteses_disponiveis": len(hypotheses)},
        "hipoteses": displayed, "evidencias": selected, "combinacoes": combo, "composicao_diferenca": bridge,
        "limitacoes": list(dict.fromkeys(limits)), "conclusao": {"grau": level, "texto": conclusion},
        "ia": {"estado": "dispensada", "chamadas": 0, "motivo": "Verificações locais concluídas; a IA não é necessária para os cálculos."}}


def run(report, scope, documentary=None, *, source_hash="", use_ai=True):
    from app.fiscal_hybrid_ai import interpret
    serialized = json.dumps({"version": RULES_VERSION, "report": report, "scope": scope,
        "documentary": documentary, "source_hash": source_hash, "use_ai": use_ai}, ensure_ascii=False, sort_keys=True, default=str)
    digest = ai_result_cache.stable_digest(serialized) or hmac.new(_secret, serialized.encode(), hashlib.sha256).hexdigest()
    with _guard:
        now = time.monotonic()
        for key in list(_cache):
            if _cache[key][0] <= now:
                del _cache[key]
        stored = deepcopy(_cache[digest][1]) if digest in _cache else ai_result_cache.read(digest)
        if stored:
            stored["cache_reutilizado"] = True
            stored["investigacao_hibrida"]["ia"]["chamadas_nesta_execucao"] = 0
            return stored
        if digest in _inflight:
            from fastapi import HTTPException
            raise HTTPException(409, "Esta seleção já está sendo investigada. Aguarde e consulte novamente.")
        _inflight.add(digest)
    try:
        result = investigate(report, scope, documentary)
        if use_ai and cents(result["resumo"]["diferenca"]) != 0 and len({h["categoria"] for h in result["hipoteses"]}) > 1 and documentary:
            result["ia"] = interpret(result)
        elif not use_ai:
            result["ia"].update(estado="desativada", motivo="Interpretação externa desativada nesta seleção.")
        row = report["contas"][0]
        output = {"conta": scope["conta"], "tipo": scope["tipo"], "descricao": row.get("descricao", ""),
            "situacao": row.get("situacao", "REVISAR"), "acumuladores": row.get("acumuladores", ""),
            "detalhes_fiscais": row.get("detalhes_fiscais", []),
            "valores": result["resumo"], "explicacao": result["conclusao"]["texto"],
            "verificar": "\n".join(f'{h["titulo"]}: {h["falta_confirmar"]}' for h in result["hipoteses"][:8]),
            "evidencias": [], "investigacao_hibrida": result, "provedor": result["ia"].get("provedor", "local")}
        with _guard:
            ttl = 60 if result["ia"]["estado"] in {"indisponivel", "limite", "invalida"} else CACHE_SECONDS
            _cache[digest] = (time.monotonic()+ttl, deepcopy(output))
            while len(_cache) > MAX_CACHE:
                del _cache[next(iter(_cache))]
        # Failed/limited provider results expire in memory; a later retry may recover.
        if result["ia"]["estado"] not in {"indisponivel", "limite", "invalida"}:
            ai_result_cache.write(digest, output)
        return output
    finally:
        with _guard:
            _inflight.discard(digest)

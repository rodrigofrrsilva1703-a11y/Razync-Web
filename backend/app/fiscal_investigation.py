"""Roteiros documentais locais: evidências e ações sem inferir causa contábil."""
from decimal import Decimal, ROUND_HALF_UP
import re
from app.fiscal_review_outcomes import review_outcome


def cents(value):
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_cases(group):
    cases = []
    for comparison in group.get("comparacoes", []):
        status = comparison.get("situacao")
        if status == "CONCILIADO":
            continue
        candidates = comparison.get("lancamentos", [])
        note = str(comparison.get("nota") or "não identificada")
        guidance = {
            "VALOR_DIFERENTE": ("Nota identificada com diferença de valor", "Candidato forte",
                "O número do documento indica uma correspondência, mas os valores divergem. Isso não identifica a causa da diferença.",
                "Confirme o valor integral da nota e eventuais parcelas ou componentes registrados separadamente.",
                "Compare o valor integral e as parcelas da nota com todos os lançamentos candidatos; identifique o componente que explica a diferença."),
            "CONTA_DIFERENTE": ("Possível correspondência em outra conta", "Candidato forte",
                "O cruzamento encontrou nota, data, valor e parceiro compatíveis em outra conta. O vínculo e a classificação precisam ser confirmados.",
                "Confirme o documento original, a natureza da operação e a conta prevista no mapeamento do acumulador.",
                "Abra a conta candidata, confira a mesma operação e compare o mapeamento do acumulador antes de propor reclassificação."),
            "DATA_DIFERENTE": ("Documento e valor compatíveis com data diferente", "Candidato forte",
                "O cruzamento encontrou a nota e o valor, mas as datas divergem. A diferença de data pode afetar a competência; não comprova erro.",
                "Confirme emissão, entrada e competência de escrituração no documento original.",
                "Compare a data fiscal com a data do lançamento e confirme em qual competência a operação deve ser reconhecida."),
            "ESTORNO_EM_ANALISE": ("Lançamento original e redutores em revisão", "Ambíguo",
                "Há movimento negativo relacionado à nota. O efeito líquido precisa ser confrontado com a origem do estorno ou devolução.",
                "Falta confirmar a relação do movimento redutor com o documento original.",
                "Confira o documento original e os redutores vinculados, suas datas e o motivo de estorno ou devolução."),
            "AMBIGUO": ("Mais de uma correspondência possível", "Ambíguo",
                "Os indícios disponíveis não permitem escolher uma correspondência única. Valores semelhantes não provam duplicidade.",
                "Confirme série, emissor ou destinatário e documento de origem para distinguir os candidatos.",
                "Compare série, parceiro, data e histórico de cada candidato e descarte os que pertencem a outra operação."),
            "PROVAVEL": ("Correspondência sugerida pelo histórico", "Ambíguo",
                "O número no histórico pode representar o documento fiscal, mas não está identificado explicitamente como nota.",
                "Confirme qual documento o número do histórico representa.",
                "Abra o comprovante que originou o lançamento e confirme número, série, parceiro e valor da nota."),
        }
        title, strength, reason, missing, action = guidance.get(status, (
            "Documento sem correspondência identificada", "Evidência insuficiente",
            "Os critérios disponíveis não identificaram um lançamento correspondente. Isso não comprova ausência na escrituração.",
            "É necessário localizar o documento de origem e verificar se o histórico permite reconhecer a nota.",
            "Busque a nota pelo número, parceiro, data e valor no Razão da filial e confira também a conta prevista no mapeamento."))
        refs = [str(p.get("id")) for p in comparison.get("linhas_fiscais", []) if p.get("id")]
        moves = [{"referencia": str(m.get("id", "")).replace("R-", "L", 1),
                  "conta": str(m.get("conta") or group["conta"]), "data": m.get("data", ""),
                  "historico": m.get("historico", ""), "contrapartida": m.get("contrapartida", ""),
                  "valor": m.get("valor", 0)} for m in candidates]
        fiscal = comparison.get("valor_fiscal", 0)
        difference = comparison.get("diferenca")
        equal, different, unknown = [], [], []
        checks = [
            ("Número da nota", [str(m.get("nota") or "").lstrip("0") for m in candidates], note.lstrip("0")),
            ("Data", [str(m.get("data") or "") for m in candidates], str(comparison.get("data") or "")),
            ("Série", [str(m.get("serie") or "").lstrip("0") for m in candidates], str(comparison.get("serie") or "").lstrip("0")),
            ("Conta", [c["conta"] for c in moves], str(group["conta"])),
        ]
        for label, values, expected in checks:
            if not values or not expected or any(not value for value in values):
                unknown.append(label)
            elif all(value == expected for value in values):
                equal.append(label)
            else:
                different.append(label)
        if difference is None:
            unknown.append("Valor do conjunto")
        else:
            (equal if cents(difference) == 0 else different).append("Valor do conjunto")
        # O leitor já validou parceiros em alguns critérios; a comparação textual
        # não substitui a confirmação do emissor/destinatário no documento original.
        unknown.append("Identidade do parceiro no documento original")
        cases.append({"id": "P-" + str(comparison["id"]), "titulo": title, "nota": note,
            "situacao": status, "grau_evidencia": strength, "explicacao_local": reason,
            "falta_confirmar": missing, "acao": action, "criterio": comparison.get("criterio", ""),
            "data_fiscal": comparison.get("data", ""), "serie": comparison.get("serie", ""),
            "parceiro": comparison.get("parceiro", ""), "referencias_fiscais": refs,
            "valor_fiscal": fiscal, "valor_razao": comparison.get("valor_razao"), "diferenca": difference,
            "campos_coincidentes": equal, "campos_divergentes": different, "campos_a_confirmar": unknown,
            "candidatos": moves, "impacto_priorizacao": abs(cents(difference if difference is not None else fiscal))})
    for movement in group.get("razao_sem_vinculo", []):
        cases.append({"id": "P-" + str(movement["id"]), "titulo": "Movimento do Razão sem vínculo identificado",
            "nota": "", "situacao": "MOVIMENTO_SEM_VINCULO", "grau_evidencia": "Evidência insuficiente",
            "explicacao_local": "O movimento não foi vinculado aos documentos fiscais desta conta. Sua presença não comprova lançamento indevido.",
            "falta_confirmar": "Confirme o documento de origem e a natureza da operação, inclusive se representa pagamento de registro anterior.",
            "acao": "Abra o comprovante do movimento e compare histórico, contrapartida e documento de origem antes de incluir ou excluir valores da comparação.",
            "referencias_fiscais": [], "valor_fiscal": None, "valor_razao": movement.get("valor", 0), "diferenca": None,
            "candidatos": [{"referencia": str(movement["id"]).replace("R-", "L", 1), "conta": str(group["conta"]),
                **{k: movement.get(k, "") for k in ("data", "historico", "contrapartida", "valor")}}],
            "impacto_priorizacao": abs(cents(movement.get("valor", 0)))})
    return sorted(cases, key=lambda c: (-c["impacto_priorizacao"], c["id"]))


def case_context(cases, docs, rows, account):
    """Até três casos completos, somente quando as referências constam no contexto enviado."""
    doc_refs = {d.get("referencia") for d in docs}
    row_refs = {r.get("referencia") for r in rows}
    eligible = []
    for case in cases:
        if not set(case["referencias_fiscais"]).issubset(doc_refs):
            continue
        if any(c["conta"] == str(account) and c["referencia"] not in row_refs for c in case["candidatos"]):
            continue
        eligible.append(case)
    ordered, seen = [], set()
    for case in eligible:
        if case["situacao"] not in seen:
            ordered.append(case)
            seen.add(case["situacao"])
    selected_ids = {case["id"] for case in ordered}
    ordered.extend(case for case in eligible if case["id"] not in selected_ids)
    selected = []
    for case in ordered[:3]:
        # As instruções locais completas ficam na tela/exportação, sem repetir
        # três textos padronizados por caso no prompt do provedor.
        selected.append({k: case[k] for k in ("id", "titulo", "nota", "grau_evidencia", "referencias_fiscais")})
        selected[-1]["candidatos"] = [{k: c[k] for k in ("referencia", "conta", "data", "contrapartida")}
                                       for c in case["candidatos"][:5]]
        for candidate in selected[-1]["candidatos"]:
            if candidate["conta"] != str(account):
                candidate["referencia"] = ""  # No contexto externo, cite o documento fiscal da própria conta.
        for field in ("campos_coincidentes", "campos_divergentes", "campos_a_confirmar"):
            selected[-1][field] = case.get(field, [])
        selected[-1]["criterios_de_revisao"] = review_outcome(case["situacao"])
    return selected


def explain_cases(cases, text, steps):
    """Associa somente trechos validados com referência explícita ao caso correto."""
    fragments = re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9])", str(text or ""))
    instructions = re.split(r"\n+", str(steps or ""))
    output = []
    for case in cases:
        allowed = set(case["referencias_fiscais"]) | {c["referencia"] for c in case["candidatos"]}
        def belongs(fragment):
            refs = set(re.findall(r"\b(?:[ES]-\d+|L\d+)\b", fragment.upper()))
            return bool(refs) and refs.issubset(allowed)
        output.append({**case, **review_outcome(case["situacao"]), "interpretacao_ia": [s for s in fragments if belongs(s)],
                       "verificacoes_ia": [s for s in instructions if belongs(s)]})
    return output

"""Ferramentas determinísticas, somente leitura, do agente fiscal-contábil.

Não aceita IDs de empresa/filial/conta de um modelo remoto: o recorte é fixado
pela sessão já validada. Respostas não incluem nomes, históricos ou documentos
integrais. Movimentos são apenas candidatos, nunca provas de vínculo.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import combinations
import re

MAX_ROWS = 15
MAX_SUBSET = 18
MAX_RESULT_BYTES = 7000


class ToolInputError(ValueError):
    pass


def _centavos(value):
    try:
        number = Decimal(str(value or 0))
        if not number.is_finite():
            raise ValueError()
        return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (ValueError, InvalidOperation, TypeError):
        raise ToolInputError("Valor monetário inválido.") from None


def _brl(cents):
    number = f"{abs(cents) // 100:,}".replace(",", ".")
    return ("-" if cents < 0 else "") + "R$ " + number + "," + str(abs(cents) % 100).zfill(2)


def _rows(data):
    scope = data["scope"]
    return [r for r in data["records"] if str(r.get("conta")) == str(scope["conta"])]


def _ref_index(data):
    return {str(r["referencia"]): r for r in _rows(data)}


def _validate_args(args):
    if not isinstance(args, dict) or len(str(args)) > 5000:
        raise ToolInputError("Argumentos inválidos ou extensos.")
    if any(k in args for k in ("empresa", "filial", "outra_conta", "executar", "codigo_python")):
        raise ToolInputError("A consulta não pode sair da conta, empresa e filial da sessão.")


def obter_contexto_conta(data, args):
    _validate_args(args)
    if args:
        raise ToolInputError("Esta ferramenta não recebe parâmetros.")
    totals = data["resumo"]
    records = _rows(data)
    return {
        "fiscal": _brl(_centavos(totals.get("fiscal"))),
        "razao": _brl(_centavos(totals.get("contabil"))),
        "diferenca_razao_menos_fiscal": _brl(_centavos(totals.get("diferenca"))),
        "tipo": data["scope"]["tipo"],
        "registros_razao": sum(r.get("origem") == "Razão" for r in records),
        "registros_fiscais": sum(r.get("origem") == "Fiscal" for r in records),
        "acompanhamento_fiscal_disponivel": bool(data.get("tem_documentos")),
        "indicios": len(data.get("hipoteses", [])),
        "limitacoes": [str(x)[:150] for x in data.get("limites", [])[:4]],
        "criterio": "Débitos no Razão para Entradas; créditos para Saídas. Diferença = Razão - Fiscal.",
    }


def cruzar_documentos_fiscais_razao(data, args):
    _validate_args(args)
    allowed = {"tolerancia_centavos"}
    if set(args) - allowed:
        raise ToolInputError("Parâmetros não reconhecidos.")
    tol = args.get("tolerancia_centavos", 0)
    if not isinstance(tol, int) or isinstance(tol, bool) or not 0 <= tol <= 5:
        raise ToolInputError("Tolerância permitida: 0 a 5 centavos, em número inteiro.")
    if not data.get("tem_documentos"):
        return {"situacao": "REQUER_ANEXO_FISCAL", "explicacao": "Acompanhamento fiscal individual não carregado; não é possível cruzar notas."}
    issues = []
    for c in data.get("comparacoes", []):
        if c.get("situacao") in ("OK", "CONFERE", "CONFERIDO"):
            continue
        refs = [ref for ref in c.get("referencias", []) if ref in _ref_index(data)]
        if c.get("diferenca") is not None and abs(_centavos(c["diferenca"])) <= tol and c.get("situacao") == "VALOR_DIFERENTE":
            continue
        issues.append({"situacao": c.get("situacao") or "PENDENTE",
                       "referencias": refs[:8],
                       "diferenca": _brl(_centavos(c.get("diferenca"))) if c.get("diferenca") is not None else None,
                       "vinculo_completo": bool(c.get("completo") and c.get("mesma_conta"))})
    return {"situacao": "CRUZAMENTO_EXISTENTE", "total_pendencias": len(issues),
            "pendencias": issues[:12], "truncado": len(issues) > 12,
            "ressalva": "São resultados do cruzamento fiscal já calculado. Não comprovam lançamento incorreto."}


def buscar_movimentos_razao(data, args):
    _validate_args(args)
    if set(args) - {"valor", "tolerancia_centavos", "termo_historico", "apenas_pendentes", "natureza"}:
        raise ToolInputError("Parâmetros não reconhecidos.")
    tol = args.get("tolerancia_centavos", 0)
    if not isinstance(tol, int) or isinstance(tol, bool) or not 0 <= tol <= 5:
        raise ToolInputError("Tolerância inválida.")
    natureza = args.get("natureza", "Razão")
    if natureza not in ("Razão", "Fiscal", "Ambos"):
        raise ToolInputError("Natureza inválida.")
    rows = _rows(data)
    if natureza != "Ambos":
        rows = [r for r in rows if r.get("origem") == natureza]
    if args.get("apenas_pendentes", False):
        rows = [r for r in rows if r.get("referencia") in data.get("pending", []) or r.get("situacao")]
    if args.get("valor") is not None:
        target = _centavos(args["valor"])
        rows = [r for r in rows if abs(abs(_centavos(r.get("valor"))) - abs(target)) <= tol]
    termo = str(args.get("termo_historico") or "").strip()[:75]
    if termo:
        rows = [r for r in rows if termo.casefold() in str(r.get("historico", "")).casefold()]
    rows.sort(key=lambda r: (r.get("referencia") not in data.get("pending", []),
                              -abs(_centavos(r.get("valor"))), str(r.get("referencia"))))
    return {"encontrados": len(rows), "limitado": len(rows) > MAX_ROWS,
            "movimentos": [{"referencia": str(r["referencia"]), "origem": r.get("origem"),
                            "data": str(r.get("data", ""))[:10],
                            "valor": _brl(_centavos(r.get("valor"))),
                            "situacao": str(r.get("situacao") or "")[:40]}
                           for r in rows[:MAX_ROWS]],
            "ressalva": "Mesmo valor não comprova correspondência documental."}


def testar_hipotese_matematica(data, args):
    _validate_args(args)
    if set(args) - {"tipo_teste", "referencias"}:
        raise ToolInputError("Parâmetros não reconhecidos.")
    kind = args.get("tipo_teste")
    if kind not in ("SOMA_DIRETA", "INVERSAO_DOBRO", "COMBINACAO_SUBCONJUNTO"):
        raise ToolInputError("Teste desconhecido.")
    refs = args.get("referencias")
    if not isinstance(refs, list) or not 1 <= len(refs) <= MAX_SUBSET or any(not isinstance(x, str) for x in refs):
        raise ToolInputError("Informe de 1 a 18 referências válidas da conta.")
    if len(set(refs)) != len(refs):
        raise ToolInputError("Referências repetidas.")
    index = _ref_index(data)
    if any(ref not in index for ref in refs):
        raise ToolInputError("A referência não pertence à conta selecionada.")
    values = [_centavos(index[ref].get("valor")) for ref in refs]
    target = _centavos(data["resumo"].get("diferenca"))
    # Um sinal oposto pode corresponder a lançamento invertido; ainda requer
    # prova documental e confirmação da natureza contábil.
    if kind == "SOMA_DIRETA":
        total = sum(values)
        return {"tipo_teste": kind, "referencias": refs, "soma": _brl(total),
                "diferenca_alvo": _brl(target), "fecha": abs(total) == abs(target),
                "provado": False}
    if kind == "INVERSAO_DOBRO":
        matches = [ref for ref, value in zip(refs, values) if 2 * abs(value) == abs(target)]
        return {"tipo_teste": kind, "candidatos": matches, "diferenca_alvo": _brl(target),
                "provado": False, "ressalva": "O dobro é um indício matemático, não confirma inversão de débito/crédito."}
    if len(refs) > MAX_SUBSET:
        raise ToolInputError("Combinações limitadas a 18 registros.")
    solutions = []
    # Até 2^18 = 262144 somas, executadas no backend, sem LLM fazendo cálculos.
    for count in range(1, len(values) + 1):
        for indices in combinations(range(len(values)), count):
            total = sum(values[i] for i in indices)
            if abs(total) == abs(target):
                solutions.append([refs[i] for i in indices])
                if len(solutions) == 3:
                    break
        if len(solutions) == 3:
            break
    return {"tipo_teste": kind, "diferenca_alvo": _brl(target), "combinacoes": solutions,
            "mais_combinacoes_possiveis": len(solutions) == 3,
            "provado": False, "ressalva": "Combinação matemática não é causa comprovada."}


def investigar_competencia(data, args):
    _validate_args(args)
    if args:
        raise ToolInputError("Esta ferramenta não recebe parâmetros.")
    issues = [h for h in data.get("hipoteses", []) if h.get("categoria") in ("competencia", "data")]
    return {"encontrados": len(issues), "indicios": [
        {"id": h.get("id"), "categoria": h.get("categoria"), "referencias": h.get("referencias", [])[:8]}
        for h in issues[:12]],
        "ressalva": "Datas distintas não provam mudança de competência. Outros meses só são consultados se enviados."}


def consultar_indicios(data, args):
    _validate_args(args)
    if args:
        raise ToolInputError("Esta ferramenta não recebe parâmetros.")
    hypotheses = data.get("hipoteses", [])
    return {"total": len(hypotheses), "indicios": [
        {"id": h.get("id"), "categoria": h.get("categoria"),
         "titulo": str(h.get("titulo") or "")[:100],
         "grau": str(h.get("grau") or "hipotese"),
         "referencias": h.get("referencias", [])[:8]}
        for h in hypotheses[:12]],
        "limitacoes": [str(v)[:120] for v in data.get("limites", [])[:4]],
        "ressalva": "Causas exigem documento original; os indícios não autorizam ajustes."}


HANDLERS = {
    "obter_contexto_conta": obter_contexto_conta,
    "cruzar_documentos_fiscais_razao": cruzar_documentos_fiscais_razao,
    "buscar_movimentos_razao": buscar_movimentos_razao,
    "testar_hipotese_matematica": testar_hipotese_matematica,
    "investigar_competencia": investigar_competencia,
    "consultar_indicios": consultar_indicios,
}


def execute(data, name, args):
    if name not in HANDLERS:
        raise ToolInputError("Ferramenta não autorizada.")
    result = HANDLERS[name](data, args)
    if len(str(result).encode("utf-8")) > MAX_RESULT_BYTES:
        raise ToolInputError("Resultado excedeu o limite de tamanho.")
    return result


TOOL_SPEC = [
    ("obter_contexto_conta", "Consulte totais, diferença e cobertura documental da conta atual.", {}),
    ("cruzar_documentos_fiscais_razao", "Consulte vínculos e discrepâncias já cruzados no período atual.",
     {"tolerancia_centavos": {"type": "integer", "minimum": 0, "maximum": 5}}),
    ("buscar_movimentos_razao", "Busque até 15 movimentos da conta, sem enviar históricos completos.",
     {"valor": {"type": "number"}, "tolerancia_centavos": {"type": "integer", "minimum": 0, "maximum": 5},
      "termo_historico": {"type": "string", "maxLength": 75},
      "apenas_pendentes": {"type": "boolean"},
      "natureza": {"type": "string", "enum": ["Razão", "Fiscal", "Ambos"]}}),
    ("testar_hipotese_matematica", "Teste soma, inversão (dobro) ou até 18 referências já identificadas.",
     {"tipo_teste": {"type": "string", "enum": ["SOMA_DIRETA", "INVERSAO_DOBRO", "COMBINACAO_SUBCONJUNTO"]},
      "referencias": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 18}}),
    ("investigar_competencia", "Consulte indícios de datas e competência no recorte disponível.", {}),
    ("consultar_indicios", "Liste hipóteses e limitações já calculadas com Python.", {}),
]


def openai_tools():
    tools = []
    for name, description, properties in TOOL_SPEC:
        required = ["tipo_teste", "referencias"] if name == "testar_hipotese_matematica" else []
        tools.append({"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}})
    return tools


def gemini_declarations():
    return [{"name": name, "description": desc,
             "parameters": {"type": "object", "properties": props,
                            "required": ["tipo_teste", "referencias"] if name == "testar_hipotese_matematica" else []}}
            for name, desc, props in TOOL_SPEC]

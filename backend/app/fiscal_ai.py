"""Revisão fiscal via OpenRouter (com fallback) ou Gemini legado."""
import copy
import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
import os
import re
import threading
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from app.fiscal_242 import conferencia_fiscal_preview
from app.ai_budget import request_slot, daily_report
from app.fiscal_ai_audit import audit_analysis, structured_analysis
from app.fiscal_ai_strategy import REVIEW_PROMPT, output_budget, compact_summary
from app.groq_fiscal import complete as _groq_completion, is_enabled as _groq_enabled, selected_model as _groq_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/conferencia-fiscal/ia")
legacy_router = APIRouter(prefix="/api/v1/conferencia-fiscal/242/ia")
lock = threading.Lock()
last_request = 0.0
model_rotation_index = 0
# Catálogo público verificado em 10/10/2026. Dots validado no Railway com
# lançamentos fictícios e evidências; reservas continuam sujeitas à validação.
FREE_FISCAL_MODELS = [
    "dots-studio/dots-3-note-preview:free",
    "apodex/apodex-1.1-mini:free",
    "liquid/lfm-2.5-2.6b:free",
    "openrouter/free",
]
STRUCTURED_FREE_MODELS = set(FREE_FISCAL_MODELS[:-1])
model_cooldowns = {}
gemini_cooldown_until = 0.0



def formatar_brl(valor):
    """Formata um valor numérico confiável com milhares e centavos brasileiros."""
    try:
        numero = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return "—"
    sinal = "-" if numero < 0 else ""
    valor_formatado = f"{abs(numero):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {valor_formatado}"


def padronizar_moeda(texto):
    """Padroniza exclusivamente valores explícitos em R$, sem tocar códigos de conta."""
    def converter(match):
        origem = match.group(1).replace(" ", "")
        corpo_sem_pontuacao = origem.rstrip(".,")
        pontuacao_final = origem[len(corpo_sem_pontuacao):]
        origem = corpo_sem_pontuacao
        negativo = origem.startswith("-")
        corpo = origem.lstrip("-")
        if not corpo or not re.fullmatch(r"\d[\d.,]*", corpo):
            return match.group(0)
        if "," in corpo and "." in corpo:
            decimal = "," if corpo.rfind(",") > corpo.rfind(".") else "."
            milhares = "." if decimal == "," else ","
            limpo = corpo.replace(milhares, "").replace(decimal, ".")
        elif "." in corpo or "," in corpo:
            sep = "." if "." in corpo else ","
            partes = corpo.split(sep)
            if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
                limpo = "".join(partes)
            else:
                limpo = corpo.replace(sep, ".")
        else:
            limpo = corpo
        try:
            quantidade = Decimal(limpo) * (-1 if negativo else 1)
        except InvalidOperation:
            return match.group(0)
        return formatar_brl(quantidade) + pontuacao_final
    return re.sub(r"R\$\s*(-?\s*\d[\d.,]*)", converter, texto)


def sanitized(report):
    """Allowlist only qualitative facts; identity, amounts and dates stay local."""
    groups, mapping = [], {}
    valid = {"CONFERE", "CONFERE COM ALERTAS", "REVISAR", "AUSENTE NO CONTÁBIL"}
    for row in report["contas"]:
        if row["situacao"] == "CONFERE":
            continue
        ident = f"G{len(groups) + 1}"
        mapping[ident] = {"conta": row["conta"], "tipo": row["tipo"]}
        groups.append({"grupo": ident,
            "situacao": row["situacao"] if row["situacao"] in valid else "REVISAR",
            "natureza": "credito" if row["tipo"] == "SAÍDAS" else "debito",
            "diferenca": "excesso" if row["diferenca"] > .01 else "falta" if row["diferenca"] < -.01 else "zero",
            "adicionais": bool(row["extras"])})
    return groups, mapping


def detailed_context(report):
    """Send extracted records with stable references and explicit coverage limits."""
    groups, mapping = sanitized(report)
    rows = report.get("lancamentos", [])
    references = {}
    indexed = {}
    for i, row in enumerate(rows, 1):
        indexed.setdefault(row.get("conta"), []).append((i, row))
    for group in groups:
        account = mapping[group["grupo"]]
        summary = next(r for r in report["contas"] if r["conta"] == account["conta"] and r["tipo"] == account["tipo"])
        group["resumo"] = {k: summary.get(k) for k in (
            "conta", "tipo", "descricao", "acumuladores", "detalhes_fiscais", "fiscal", "contabil", "total_conta", "diferenca", "extras", "sem_evidencia")}
        group["valores_brl"] = {campo: formatar_brl(summary.get(campo, 0))
            for campo in ("fiscal", "contabil", "total_conta", "diferenca")}
        candidates = indexed.get(account["conta"], [])
        selected = candidates
        group["lancamentos"] = []
        for i, row in selected:
            ref = row.get("_referencia_ia") or f"L{i}"
            record = {k: row.get(k, "") for k in (
                "conta", "data", "historico", "contrapartida", "debito", "credito", "natureza", "classificacao")}
            record["referencia"] = ref
            record["debito_brl"] = formatar_brl(record.get("debito", 0))
            record["credito_brl"] = formatar_brl(record.get("credito", 0))
            references[ref] = record
            group["lancamentos"].append(record)
        group["cobertura"] = {"enviados": len(selected), "existentes": len(candidates)}
        pendentes = report.get("documentos_pendentes")
        if isinstance(pendentes, dict):
            key = f'{account["conta"]}:{account["tipo"]}'
            group["pendencias_documentais"] = pendentes.get(key, [])
            group["cobertura_documental"] = report.get("cobertura_documental", {}).get(key, {})
    context = {
        "periodo_fiscal": report.get("periodo_fiscal", {}),
        "periodo_razao": report.get("periodo_razao", {}),
        "avisos_do_leitor": report.get("avisos", []),
        "grupos": groups,
        "fonte_fiscal": report.get("fonte_fiscal", "Resumo por acumulador, sem documentos fiscais individuais"),
        "escopo_razao": report.get("escopo_razao", "Lançamentos das contas vinculadas aos acumuladores, com filtro da filial aplicado"),
    }
    coverage = f"Analisados {len(groups)} de {sum(r['situacao'] != 'CONFERE' for r in report['contas'])} grupos com alertas/divergências; {len(references)} lançamentos distintos enviados. Sem corte por quantidade de grupos ou registros no contexto local."
    if isinstance(report.get("documentos_pendentes"), dict):
        coverage = (f"{len(groups)} grupos documentais; {len(references)} lançamentos enviados. "
                    "Seleção de até 30 documentos e 30 movimentos pendentes por conta/tipo, "
                    "priorizando diferenças de valor e data. A cobertura por grupo informa o total "
                    "local e a amostra enviada. Não concluir ausência ou duplicidade sobre registros não enviados.")
    if len(json.dumps(context, ensure_ascii=False).encode()) > 2_000_000:
        raise HTTPException(422, "Os históricos excedem o limite da análise com IA. Envie relatórios de um período menor.")
    return context, mapping, references, coverage


def provider_error(exc):
    """Translate provider failures without exposing provider text or credentials."""
    try:
        error = json.loads(exc.read(32768)).get("error", {})
        reasons = {item.get("reason") for item in error.get("details", []) if isinstance(item, dict)}
    except Exception:
        reasons = set()
    if reasons & {"API_KEY_INVALID", "API_KEY_EXPIRED"}:
        message = "O Google recusou a chave do Gemini. Substitua GEMINI_API_KEY no Railway por uma chave válida do Google AI Studio."
    elif reasons & {"API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED"}:
        message = "As restrições da chave bloqueiam o servidor Railway. Revise as permissões da chave para a API Generative Language no Google Cloud."
    elif exc.code == 403:
        message = "O Google negou acesso ao Gemini (403). Verifique as permissões da chave, a API Generative Language e a disponibilidade para o projeto."
    elif exc.code == 404:
        message = "O modelo configurado não está disponível no Gemini (404). Revise GEMINI_MODEL no Railway."
    elif exc.code == 429:
        message = "A cota do Gemini foi atingida (429). Aguarde a renovação do limite do seu projeto no Google AI Studio."
    elif exc.code == 400:
        message = "O Google rejeitou a solicitação ao Gemini (400). Verifique a validade da chave e a compatibilidade do modelo com respostas JSON estruturadas."
    else:
        message = f"O Gemini apresentou uma falha no serviço (HTTP {exc.code}). Tente novamente mais tarde."
    return HTTPException(429 if exc.code == 429 else 502, message)


def _openrouter_models():
    """Prioridades gratuitas explícitas; falhas acionam modelos de reserva."""
    configured = os.getenv("OPENROUTER_MODELS", ",".join(FREE_FISCAL_MODELS))
    requested = [m.strip() for m in configured.split(",")]
    models = list(dict.fromkeys(requested))
    if not 1 <= len(models) <= 8 or any(not m for m in requested) or any(
        model != "openrouter/free" and not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.-]*/[a-zA-Z0-9_.-]+:free", model
        )
        for model in models
    ):
        raise HTTPException(
            503,
            "OPENROUTER_MODELS aceita somente openrouter/free ou modelos terminados em :free. "
            "Modelos pagos estão bloqueados."
        )
    if models == ["openrouter/free"] and os.getenv("OPENROUTER_ROUTER_FIRST", "") != "1":
        models = list(FREE_FISCAL_MODELS)
    with lock:
        available = [m for m in models if model_cooldowns.get(m, 0) <= time.monotonic()]
    return available or ["openrouter/free"]


def _openrouter_completion(payload, models, key, *, _repair=False):
    payload = _compact_transport(payload)
    """Adapta formatos gratuitos sem reduzir a validação fiscal-contábil."""
    group_ids = payload["generationConfig"]["responseSchema"]["properties"]["analises"]["items"]["properties"]["grupo"]["enum"]
    # A resposta do modelo gratuito estava terminando em finish_reason=length.
    # Requisitar poucos grupos por vez evita um JSON enorme e truncado.
    # Todos os modelos gratuitos recebem lotes menores, não apenas o roteador.
    # Mantemos os lançamentos de cada grupo dentro do seu próprio lote.
    if len(group_ids) > 2:
        source = json.loads(payload["contents"][0]["parts"][0]["text"])
        all_analyses, used_models = [], []
        for start in range(0, len(group_ids), 2):
            ids = group_ids[start:start + 2]
            chunk = copy.deepcopy(payload)
            chunk["generationConfig"]["responseSchema"]["properties"]["analises"]["items"]["properties"]["grupo"]["enum"] = ids
            partial = dict(source)
            partial["grupos"] = [row for row in source["grupos"] if row["grupo"] in ids]
            chunk["contents"][0]["parts"][0]["text"] = json.dumps(partial, ensure_ascii=False, separators=(",", ":"))
            answer, used = _openrouter_completion(chunk, models, key)
            items = answer.get("analises", [])
            returned_ids = {
                item["grupo"].strip().upper()
                for item in items
                if isinstance(item, dict) and isinstance(item.get("grupo"), str)
            }
            if len(items) != len(ids) or returned_ids != set(ids):
                logger.warning("fiscal_openrouter_rejected category=incomplete_batch")
                raise ValueError("Parecer incompleto em lote gratuito")
            all_analyses.extend(items)
            used_models.append(used)
        return {"analises": all_analyses}, ", ".join(dict.fromkeys(used_models))

    converted_schema = {
        "type": "object",
        "properties": {
            "analises": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "grupo": {"type": "string", "enum": payload["generationConfig"]["responseSchema"]["properties"]["analises"]["items"]["properties"]["grupo"]["enum"]},
                        "explicacao": {"type": "string"},
                        "verificar": {"type": "string"},
                        "evidencias": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["grupo", "explicacao", "verificar", "evidencias"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["analises"],
        "additionalProperties": False,
    }
    source_context = json.loads(payload["contents"][0]["parts"][0]["text"])
    reference_lists = {group["grupo"]: [row["referencia"] for row in group.get("lancamentos", [])
                       if isinstance(row.get("referencia"), str)] for group in source_context.get("grupos", [])}
    allowed_references = sorted({ref for refs in reference_lists.values() for ref in refs})
    evidence_schema = converted_schema["properties"]["analises"]["items"]["properties"]["evidencias"]
    evidence_schema["maxItems"] = 3 if allowed_references else 0
    if allowed_references:
        evidence_schema["items"]["enum"] = allowed_references
    request_payload = {
        "messages": [
            {"role": "system", "content": payload["systemInstruction"]["parts"][0]["text"]},
            {"role": "user", "content": payload["contents"][0]["parts"][0]["text"]},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "razync_fiscal_review", "strict": True, "schema": converted_schema,
        }},
        "provider": {
            "allow_fallbacks": True,
            "require_parameters": True,
            "data_collection": "deny",
            "sort": "latency",
            # Proteção adicional: nem erro de configuração nem fallback pode
            # selecionar endpoint tarifado para entrada ou saída.
            "max_price": {"prompt": 0, "completion": 0},
        },
        "temperature": 0.2,
        # Limita o teto de geração sem retirar grupos ou lançamentos do contexto.
        "max_tokens": output_budget(len(group_ids)),
    }
    # O roteador gratuito recomenda 'model' para uma escolha única.
    # A lista 'models' é usada somente quando houver vários candidatos.
    request_payload["model"] = models[0]
    request_payload["messages"][0]["content"] += (
        "\nReferências permitidas por grupo: " + json.dumps(reference_lists, ensure_ascii=False) +
        ". Se a lista do grupo estiver vazia, devolva evidencias [] e não cite lançamentos L.")

    # openrouter/free pode rejeitar json_schema estrito (HTTP 400) ou ficar
    # aguardando um endpoint compatível. Peça JSON textual já na 1ª chamada;
    # validação contábil continua igualmente rígida no próprio Razync.
    def compatible_payload(base):
        candidate = dict(base)
        candidate.pop("response_format", None)
        candidate["provider"] = dict(base["provider"])
        candidate["provider"].pop("require_parameters", None)
        candidate["reasoning"] = {"enabled": False}
        candidate["messages"] = [dict(item) for item in base["messages"]]
        allowed = converted_schema["properties"]["analises"]["items"]["properties"]["grupo"]["enum"]
        candidate["messages"][0]["content"] += (
            chr(10) + "IMPORTANTE: responda APENAS JSON válido, sem markdown. "
            'Objeto: {"analises":[{"grupo":"G1","explicacao":"...","verificar":"1. ...",'
            '"evidencias":["L1"]}]}. '
            "Inclua todos os grupos: " + ", ".join(allowed) + ". "
            "Use somente referências de lançamento que existam nos dados. "
            "Não invente valores, grupos ou evidências."
        )
        if os.getenv("OPENROUTER_ROUTER_FIRST") == "1":
            # Prompt enxuto reduz tokens de raciocínio/saída em modelos gratuitos.
            candidate["messages"][0]["content"] = REVIEW_PROMPT + (
                " Inclua EXATAMENTE estes grupos: " + ", ".join(allowed) + ". "
                "Se JSON não for possível, use por grupo: GRUPO: G1\\nEXPLICACAO: texto\\nVERIFICAR: 1. passo\\nEVIDENCIAS: L1,L2."
            )
            candidate["reasoning"] = {"enabled": False}
            candidate["max_tokens"] = output_budget(len(allowed))
        if _repair:
            # O prompt resumido substitui a instrução original; por isso o
            # pedido de correção precisa ser preservado DEPOIS dessa troca.
            candidate["messages"][0]["content"] += (
                "\\nCORREÇÃO NECESSÁRIA: um item anterior continha formato incorreto "
                "ou referência inexistente. Responda todos os grupos, use apenas "
                "referências L enviadas com cada grupo e, se não houver certeza, "
                "não mencione L no texto e devolva evidencias []."
            )
        return candidate

    structured_payload = copy.deepcopy(request_payload)
    free_router = models[0] == "openrouter/free" or (
        models[0] in FREE_FISCAL_MODELS and models[0] not in STRUCTURED_FREE_MODELS)
    if free_router:
        request_payload = compatible_payload(request_payload)
    def send(body, seconds=18):
        chosen = str(body.get("model", "")).strip()
        if chosen != "openrouter/free" and not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.-]*/[a-zA-Z0-9_.-]+:free", chosen
        ):
            raise HTTPException(503, "Modo custo zero: modelo OpenRouter pago bloqueado.")
        if any(body.get(key) for key in ("tools", "plugins", "web_search_options", "transforms")):
            raise HTTPException(503, "Modo custo zero: ferramentas potencialmente pagas bloqueadas.")
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
                "HTTP-Referer": "https://rodrigofrrsilva1703-a11y.github.io/Razync-Web/",
                "X-Title": "Razync Fiscal",
            },
        )
        with request_slot("openrouter", "free", body) as usage:
            with urllib.request.urlopen(request, timeout=seconds) as response:
                raw = json.loads(response.read(200000))
            usage(raw)
            return raw

    def safe_upstream_category(exc):
        """Classifica falhas sem registrar corpo, nomes, extratos ou credenciais."""
        try:
            raw = json.loads(exc.read(16384))
            error = raw.get("error", {}) if isinstance(raw, dict) else {}
            detail = str(error.get("message", "")).lower() if isinstance(error, dict) else ""
        except (ValueError, UnicodeError, TypeError, AttributeError):
            detail = ""
        cases = [
            (("data policy", "privacy", "data collection", "zero data"), "politica_privacidade"),
            (("no endpoints", "no provider", "no available provider", "endpoint"), "sem_endpoint_compativel"),
            (("rate limit", "too many requests", "quota"), "limite_provedor"),
            (("context length", "context window", "too many tokens", "payload"), "contexto_excedido"),
            (("model not found", "unknown model", "model unavailable"), "modelo_indisponivel"),
            (("overloaded", "temporarily unavailable", "upstream"), "provedor_indisponivel"),
            (("json", "response_format", "schema", "parameters"), "formato_incompativel"),
        ]
        return next((label for tokens, label in cases
                     if any(token in detail for token in tokens)), "falha_nao_especificada")

    upstream_category = "falha_nao_especificada"
    # Modelos gratuitos podem devolver 502/503 mesmo com o backend saudável.
    # Tente até três modelos diferentes antes de usar o Gemini de reserva.
    # O mesmo contexto e as restrições gratuitas/privacidade são preservados.
    with lock:
        candidates = [model for model in models
                      if model_cooldowns.get(model, 0) <= time.monotonic()][:3]
    if not candidates:
        candidates = ["openrouter/free"]
    try:
        for attempt, model in enumerate(candidates):
            request = (copy.deepcopy(structured_payload) if model in STRUCTURED_FREE_MODELS
                       else dict(request_payload) if attempt == 0 else compatible_payload(request_payload))
            if model in STRUCTURED_FREE_MODELS:
                request["reasoning"] = {"enabled": False}
            request["model"] = model
            try:
                response_json = send(request)
                if attempt:
                    logger.info("fiscal_openrouter_recovered model=%s attempt=%d",
                                model, attempt + 1)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 400 and not free_router:
                    # Mantém a segunda tentativa com JSON compatível sem mudar
                    # de modelo nem relaxar limites e política dos dados.
                    exc.close()
                    response_json = send(compatible_payload(request), seconds=12)
                    break
                upstream_category = safe_upstream_category(exc)
                logger.warning(
                    "fiscal_openrouter_upstream status=%d model=%s category=%s attempt=%d",
                    exc.code, model, upstream_category, attempt + 1,
                )
                transient = exc.code in (400, 404, 408, 429, 500, 502, 503, 504, 529)
                if transient and attempt + 1 < len(candidates):
                    exc.close()
                    with lock:
                        model_cooldowns[model] = time.monotonic() + 90
                    continue
                raise
            except (TimeoutError, urllib.error.URLError) as exc:
                timeout = isinstance(exc, TimeoutError) or isinstance(
                    getattr(exc, "reason", None), TimeoutError)
                if not timeout or attempt + 1 >= len(candidates):
                    raise
                logger.warning("fiscal_openrouter_upstream status=timeout model=%s attempt=%d",
                               model, attempt + 1)
                with lock:
                    model_cooldowns[model] = time.monotonic() + 90
    except urllib.error.HTTPError as exc:
        # Não repassa mensagens do provedor: podem conter dados privados ou credenciais.
        if exc.code in (401, 403):
            detail = "O OpenRouter recusou a chave ou suas permissões. Confira OPENROUTER_API_KEY no Railway."
        elif exc.code == 402:
            detail = "Os créditos do OpenRouter terminaram ou o limite de gasto foi atingido. Recarregue créditos ou revise o teto da chave."
        elif exc.code == 429:
            detail = "Todos os modelos disponíveis atingiram limites de requisições. Tente novamente mais tarde ou configure modelos com cota disponível."
        elif exc.code in (400, 404):
            causes = {
                "politica_privacidade": "política de privacidade dos endpoints",
                "sem_endpoint_compativel": "seleção de endpoints",
                "limite_provedor": "limite de requisições",
                "contexto_excedido": "limite de contexto",
                "modelo_indisponivel": "seleção de modelos",
                "formato_incompativel": "formato dos parâmetros",
            }
            category = causes.get(upstream_category, "solicitação recusada pelo provedor")
            detail = f"O OpenRouter rejeitou a análise gratuita ({exc.code}): " + category + ". A conferência permanece disponível."
        else:
            detail = f"OpenRouter temporariamente indisponível (HTTP {exc.code}). A conferência contábil não foi alterada."
        raise HTTPException(429 if exc.code in (402, 429) else 403 if exc.code in (401, 403) else 400 if exc.code == 400 else 502, detail) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        if isinstance(exc, (TimeoutError,)) or isinstance(getattr(exc, "reason", None), TimeoutError):
            raise HTTPException(504, "A IA gratuita demorou além do limite de espera, mesmo após a tentativa de reserva. "
                "Tente novamente ou reduza a quantidade de contas analisadas. "
                "A conferência contábil permanece salva.") from None
        raise HTTPException(502, "Não foi possível conectar ao OpenRouter. A conferência contábil permanece salva.") from None
    # A resposta de um modelo gratuito pode chegar íntegra, mas conter
    # evidências que não existem no lote. Corrija UMA vez junto ao provedor;
    # nunca invente, remapeie ou silenciosamente descarte lançamentos.
    def repair_once(cause):
        logger.warning(
            "fiscal_openrouter_rejected category=%s model=%s repair=%s",
            cause, request_payload["model"], not _repair,
        )
        if _repair:
            raise ValueError({
                "invalid_evidence": "Invalid evidence reference",
                "missing_groups": "Resposta de OpenRouter com grupos ausentes",
                "invalid_json": "JSON ou blocos de texto inválidos do OpenRouter",
                "empty_content": "Resposta vazia do OpenRouter",
            }.get(cause, "Resposta inválida do OpenRouter"))
        corrected = copy.deepcopy(payload)
        corrected["systemInstruction"]["parts"][0]["text"] += (
            "\nCORREÇÃO NECESSÁRIA: a última resposta não atendeu ao contrato. "
            "Forneça um item para cada grupo solicitado, em JSON válido. "
            "Cite somente referências L presentes nos lançamentos do próprio grupo. "
            "Na dúvida use evidencias [] e NÃO cite referências inexistentes no texto. "
            "Não invente lançamentos, documentos ou valores; mantenha a explicação útil."
        )
        # Uma resposta inválida de um modelo não deve prender toda a reserva
        # nesse mesmo modelo. Há apenas uma nova geração de correção.
        reserve = [models[1]] if len(models) > 1 else models
        return _openrouter_completion(corrected, reserve, key, _repair=True)

    choices = response_json.get("choices") or []
    if not choices:
        # HTTP 200 pode vir com choices vazio em roteadores gratuitos.
        # Reexecutar apenas uma vez no modelo de reserva, com mesmo contexto
        # e validação integral de grupos/evidências.
        return repair_once("empty_content")
    choice = choices[0]
    reason = choice.get("finish_reason")
    if reason not in ("stop", "length"):
        logger.warning("fiscal_openrouter_rejected category=finish_reason reason=%s",
                       reason if reason in {"content_filter", "tool_calls", "error"} else "other")
        raise ValueError("Resposta não concluída do OpenRouter")
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, dict):
        content = content.get("text")
    if isinstance(content, list):
        content = chr(10).join(str(part.get("text", "")) for part in content
                           if isinstance(part, dict) and part.get("type") in ("text", "output_text"))
    if not isinstance(content, str) or not content.strip():
        parsed = message.get("parsed")
        content = json.dumps(parsed, ensure_ascii=False) if isinstance(parsed, dict) else ""
    if not content.strip():
        return repair_once("empty_content")
    result_text = content.strip()
    if result_text.startswith("```"):
        lines = result_text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            result_text = chr(10).join(lines[1:-1]).strip()
    try:
        answer = json.loads(result_text)
    except json.JSONDecodeError:
        # Alguns modelos gratuitos antepõem texto ao objeto JSON. Extraímos
        # somente um objeto íntegro; não fabricamos partes ausentes.
        decoder = json.JSONDecoder()
        answer = None
        for index, ch in enumerate(result_text):
            if ch != "{":
                continue
            try:
                candidate, end = decoder.raw_decode(result_text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and isinstance(candidate.get("analises"), list):
                answer = candidate
                break
        if answer is None:
            # Aceita também que um modelo envie os caracteres literais \\n.
            if "GRUPO:" in result_text and "\\n" in result_text:
                result_text = result_text.replace("\\n", chr(10))
            # Compatibilidade com modelos que não suportam modo JSON:
            # blocos textuais identificados por grupo, sem inferir valores.
            blocks = re.split(r"(?im)^\s*GRUPO\s*:\s*", result_text)
            parsed = []
            for block in blocks[1:]:
                matched = re.match(r"^[ \t]*(G\d+)[ \t]*\r?\n", block)
                if not matched:
                    continue
                ident = matched.group(1)
                text_body = block[matched.end():]
                sections = re.search(
                    r"(?is)\bEXPLICACAO\s*:\s*(.*?)\s*\bVERIFICAR\s*:\s*(.*?)"
                    r"\s*\bEVIDENCIAS\s*:\s*(.*)\Z", text_body)
                if not sections:
                    continue
                evidence_text = sections.group(3).strip()
                refs = re.findall(r"\bL\d+\b", evidence_text) if evidence_text.lower() not in ("nenhum", "nenhuma", "-", "") else []
                parsed.append({"grupo": ident, "explicacao": sections.group(1).strip(),
                    "verificar": sections.group(2).strip(), "evidencias": refs})
            if parsed:
                answer = {"analises": parsed}
            else:
                return repair_once("invalid_json")
    if not isinstance(answer, dict) or not isinstance(answer.get("analises"), list):
        return repair_once("missing_groups")
    # 'length' não basta para descartar um JSON já completo. Mas não
    # aceitamos qualquer grupo perdido: conferimos contra o lote solicitado.
    items = answer["analises"]
    if len(items) != len(group_ids) or {row.get("grupo", "").strip().upper() for row in items if isinstance(row, dict) and isinstance(row.get("grupo"), str)} != set(group_ids):
        return repair_once("missing_groups")
    # Referências são locais e específicas por grupo. A revisão não pode usar
    # um L de outra conta, nem alegar evidências inexistentes no texto.
    context = json.loads(payload["contents"][0]["parts"][0]["text"])
    permitted = {
        group["grupo"]: {
            str(row["referencia"]).upper()
            for row in group.get("lancamentos", [])
            if isinstance(row, dict) and isinstance(row.get("referencia"), str)
        }
        for group in context.get("grupos", [])
        if isinstance(group, dict) and isinstance(group.get("grupo"), str)
    }
    for item in items:
        group_id = item["grupo"].strip().upper()
        evidence = item.get("evidencias", [])
        if isinstance(evidence, str):
            evidence = [] if evidence.strip().lower() in ("", "nenhum", "nenhuma", "[]", "-") else evidence.split(",")
        if not isinstance(evidence, list):
            return repair_once("invalid_evidence")
        allowed = permitted.get(group_id, set())
        declared = {x.strip().upper() for x in evidence if isinstance(x, str)}
        quoted = set(re.findall(r"\bL\d+\b", (
            str(item.get("explicacao", "")) + " " + str(item.get("verificar", ""))
        ).upper()))
        if len(evidence) > 8 or any(not isinstance(x, str) for x in evidence) or not declared.issubset(allowed) or not quoted.issubset(allowed):
            return repair_once("invalid_evidence")
    return answer, str(response_json.get("model") or "")



def _gemini_free_key():
    """Somente usa a API direta quando o projeto foi confirmado como free tier."""
    if os.getenv("GEMINI_FREE_TIER_CONFIRMED", "") != "1":
        return ""
    return os.getenv("GEMINI_API_KEY", "").strip()


def _compact_transport(payload):
    payload = copy.deepcopy(payload)
    context = json.loads(payload["contents"][0]["parts"][0]["text"])
    for group in context.get("grupos", []):
        group["resumo"] = compact_summary(group.get("resumo"))
        for record in group.get("lancamentos", []):
            # A conta está no resumo; os valores exatos permanecem em BRL.
            record.pop("conta", None)
            for redundant in ("debito", "credito"):
                if redundant + "_brl" in record:
                    record.pop(redundant, None)
    # Redação local de identificadores óbvios antes de transmitir texto.
    # Mantém valores, datas e referências intactos para a análise contábil.
    def redact(value):
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        if not isinstance(value, str):
            return value
        value = re.sub(r"\b\d{2}[.]?\d{3}[.]?\d{3}[/]?\d{4}[-]?\d{2}\b", "[CNPJ]", value)
        value = re.sub(r"\b\d{3}[.]?\d{3}[.]?\d{3}[-]?\d{2}\b", "[CPF]", value)
        return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    context = redact(context)
    payload["contents"][0]["parts"][0]["text"] = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    return payload


def _gemini_completion(payload, key, model, *, legacy=False):
    payload = _compact_transport(payload)
    with request_slot("gemini", model, payload) as usage:
        answer, used_model, raw = _gemini_send(payload, key, model, legacy=legacy)
        usage(raw)
        return answer, used_model


def _gemini_send(payload, key, model, *, legacy=False):
    """Envia ao Gemini o mesmo contexto e schema usado no OpenRouter."""
    if legacy or os.getenv("GEMINI_FREE_TIER_CONFIRMED") != "1":
        raise HTTPException(503, "Modo custo zero: Gemini pago/legado ou projeto não confirmado como gratuito bloqueado.")
    if model not in {"gemini-3.1-flash-lite", "gemini-2.5-flash-lite"}:
        raise HTTPException(503, "Modo custo zero: somente modelos Gemini Flash-Lite gratuitos são permitidos.")
    if payload.get("tools") or payload.get("toolConfig") or payload.get("cachedContent"):
        raise HTTPException(503, "Modo custo zero: ferramentas externas e cache cobrado estão bloqueados.")
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}
    )
    try:
        try:
            response = urllib.request.urlopen(request, timeout=45)
        except urllib.error.HTTPError as exc:
            if not legacy or exc.code != 404 or model == "gemini-3.1-flash-lite":
                raise
            exc.close()
            model = "gemini-3.1-flash-lite"
            response = urllib.request.urlopen(
                urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    data=request.data,
                    headers={"Content-Type":"application/json", "x-goog-api-key": key},
                ), timeout=45
            )
        with response:
            raw = json.loads(response.read(150000))
    except urllib.error.HTTPError as exc:
        raise provider_error(exc) from None
    except (urllib.error.URLError, TimeoutError):
        raise HTTPException(502, "Gemini indisponível. A conferência contábil permanece salva.") from None
    candidate = raw["candidates"][0]
    if candidate.get("finishReason") != "STOP":
        raise ValueError("Resposta Gemini incompleta")
    text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
    return json.loads(text), model, raw


def _validar_resposta_ia(result, report, mapping, references, *, groq=False, provider=None, model=None):
    """Converte e confere contas, valores e referências sem depender do provedor."""
    output, seen = [], set()
    for item in result["analises"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid analysis item")
        original = item.get("grupo")
        ident = original.strip().upper() if isinstance(original, str) else ""
        if ident not in mapping or ident in seen:
            raise ValueError("Unknown or repeated group")
        if not all(isinstance(item.get(k), str) and 0 < len(item[k]) <= 6000 for k in ("explicacao", "verificar")):
            raise ValueError("Invalid explanation")
        evidence = item.get("evidencias", [])
        if isinstance(evidence, str):
            evidence = [] if evidence.strip().lower() in ("", "nenhum", "nenhuma", "[]", "-") else [
                ref.strip() for ref in evidence.split(",")]
        if not isinstance(evidence, list):
            raise ValueError("Invalid evidence reference")
        evidence = [ref.strip().upper() if isinstance(ref, str) else ref for ref in evidence]
        if len(evidence) > 8 or any(
            not isinstance(ref, str) or ref not in references
            or references[ref]["conta"] != mapping[ident]["conta"] for ref in evidence
        ):
            raise ValueError("Invalid evidence reference")
        seen.add(ident)
        conta_atual = next(row for row in report["contas"]
            if row["conta"] == mapping[ident]["conta"] and row["tipo"] == mapping[ident]["tipo"])
        docs = report.get("documentos_pendentes", {}).get(
            f'{mapping[ident]["conta"]}:{mapping[ident]["tipo"]}', [])
        documented = {str(d.get("referencia", "")).upper(): d for d in docs}
        cited_docs = set(re.findall(r"\b[ES]-\d+\b", (item["explicacao"] + " " + item["verificar"]).upper()))
        if cited_docs - documented.keys():
            raise ValueError("Invalid evidence reference")
        valores = {campo: conta_atual.get(campo, 0)
            for campo in ("fiscal", "contabil", "total_conta", "diferenca")}
        output.append({**mapping[ident],
                       "descricao": conta_atual.get("descricao", ""),
                       "acumuladores": conta_atual.get("acumuladores", ""),
                       "detalhes_fiscais": conta_atual.get("detalhes_fiscais", []),
                       "situacao": conta_atual.get("situacao", "REVISAR"),
                       "valores": valores,
                       "explicacao": padronizar_moeda(item["explicacao"]),
                       "verificar": padronizar_moeda(item["verificar"]),
                       "evidencias":[references[ref] for ref in dict.fromkeys(evidence)],
                       "documentos_evidencias": [documented[ref] for ref in sorted(cited_docs)]})
        rows = [row for row in report.get("lancamentos", []) if row.get("conta") == mapping[ident]["conta"]]
        output[-1]["parecer"] = structured_analysis(output[-1], rows,
            sent=min(10, len(rows)) if groq else len(rows),
            shortened=groq and any(len(str(row.get("historico") or "")) > 180 for row in rows),
            documentary=report.get("documentos_pendentes") is not None)
        output[-1]["parecer"]["comparacoes_documentais"] = docs
        output[-1]["auditoria"] = audit_analysis(output[-1])
        output[-1].update(provedor=provider, modelo_usado=model)
    if seen != set(mapping):
        raise ValueError("Empty answer")
    return output


def explain(report, preferred_provider=None, *, only_openrouter=False, only_provider=None):
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    gemini_key = _gemini_free_key()
    provider_choice = preferred_provider or os.getenv("RAZYNC_AI_PRIMARY", "openrouter")
    groq_ready = _groq_enabled() and provider_choice == "groq"
    legacy = os.getenv("RAZYNC_AI_LEGACY_GEMINI", "") == "1"
    legacy_direct = False  # Segurança obrigatória: não há fallback para Gemini legado/pago.
    if only_provider not in (None, "gemini", "groq", "openrouter"):
        raise HTTPException(422, "Provedor inválido.")
    if only_provider:
        # Sessões coordenam as reservas: cada chamada usa só um provedor
        # aprovado como gratuito, sem voltar ao Gemini legado.
        legacy_direct = False
        provider_choice = only_provider
        groq_ready = _groq_enabled() and only_provider == "groq"
        if only_provider != "gemini":
            gemini_key = ""
        if only_provider != "openrouter":
            openrouter_key = ""
    if only_openrouter:
        if not openrouter_key:
            raise HTTPException(503, "OpenRouter não configurado no servidor.")
        gemini_key = ""
        legacy_direct = False
        groq_ready = False
    if not (openrouter_key or gemini_key or groq_ready):
        raise HTTPException(503, "IA gratuita indisponível. Configure um provedor gratuito aprovado.")
    context, mapping, references, coverage = detailed_context(report)
    if not mapping:
        return {"analises": [], "aviso": "Nenhuma divergência ou alerta para explicar."}
    gemini_model = (os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        if legacy_direct else os.getenv("GEMINI_FREE_MODEL", "gemini-3.1-flash-lite"))
    if legacy_direct:
        if not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+", gemini_model):
            raise HTTPException(503, "Revise GEMINI_MODEL no Railway.")
    elif gemini_key and gemini_model not in {"gemini-3.1-flash-lite", "gemini-2.5-flash-lite"}:
        raise HTTPException(503, "GEMINI_FREE_MODEL deve ser um Flash-Lite gratuito permitido.")
    models = _openrouter_models() if openrouter_key else []
    global last_request, model_rotation_index
    with lock:
        if legacy_direct:
            if time.monotonic() - last_request < 15:
                raise HTTPException(429, "Aguarde 15 segundos antes de analisar novamente.")
            last_request = time.monotonic()
        if models:
            # Prioridade estável evita consumir uma chamada em modelos menos
            # confiáveis. Cooldowns e falhas ainda acionam as reservas.
            models = [m for m in models if m != "openrouter/free"] + [m for m in models if m == "openrouter/free"]
    schema = {"type":"OBJECT", "properties":{"analises":{"type":"ARRAY", "items":{
        "type":"OBJECT", "properties":{
            "grupo":{"type":"STRING", "enum":list(mapping)},
            "explicacao":{"type":"STRING"}, "verificar":{"type":"STRING"},
            "evidencias":{"type":"ARRAY", "items":{"type":"STRING"}}},
        "required":["grupo","explicacao","verificar","evidencias"]}}}, "required":["analises"]}
    payload = {"systemInstruction":{"parts":[{"text":REVIEW_PROMPT}]},
        "contents":[{"role":"user","parts":[{"text":json.dumps(context, ensure_ascii=False, separators=(",", ":"))}]}],
        "generationConfig":{"responseMimeType":"application/json", "responseSchema":schema,
                            "temperature":0.2, "maxOutputTokens":output_budget(len(mapping))}}
    if report.get("documentos_pendentes") is not None:
        payload["systemInstruction"]["parts"][0]["text"] += (
            " ETAPA DOCUMENTAL: pendencias_documentais contém apenas registros não conciliados ou ambíguos; "
            "os conciliados foram removidos. Use nota, acumulador, CFOP, data e valor como indícios. "
            "cobertura_documental informa enviados/total pendente local; declare amostras sem generalizar. "
            "Datas diferentes exigem confirmar o período. Ausência neste contexto não prova omissão."
        )
    # Gemini/OpenRouter usam o contexto abaixo; Groq compacta os registros e adapta o prompt.
    # Um resultado só é aceito após validação integral das contas e evidências.
    # Groq permanece desativada até confirmação explícita de plano gratuito,
    # Zero Data Retention e seleção como provedor principal.
    groq_failed = False
    if groq_ready:
        try:
            groq_model = _groq_model()
            answer, used_model = _groq_completion(payload, os.getenv("GROQ_API_KEY", "").strip(), groq_model)
            analyses = _validar_resposta_ia(answer, report, mapping, references, groq=True, provider="groq", model=used_model)
            logger.info("fiscal_ia_groq_success model=%s groups=%d", used_model, len(analyses))
            return {
                "analises": analyses,
                "aviso": "Sugestões da IA para revisão humana. Nenhum cálculo ou arquivo foi alterado.",
                "limite": coverage + " Groq recebeu até 10 históricos por grupo, limitados a 180 caracteres, e indicadores calculados localmente nos registros disponíveis antes da seleção da amostra. Não representa leitura integral dos lançamentos pela IA.", "provedor": "groq", "modelo_usado": used_model,
                "gratuito": True, "fallback_usado": False,
            }
        except HTTPException as exc:
            logger.warning("fiscal_ia_groq_failure status=%d backup_available=%s",
                           exc.status_code, bool(gemini_key or openrouter_key))
            # Erro permanente de chave/permissão: nunca ocultar com Gemini.
            # Reserva automática só para indisponibilidade temporária da Groq.
            if exc.status_code not in (429, 502, 503, 504) or not (gemini_key or openrouter_key):
                raise
            groq_failed = True
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            # Categoria técnica fixa; nunca expor prompts, respostas brutas,
            # identificadores fiscais ou mensagens arbitrárias da API.
            allowed = {
                "Groq output limited by tokens",
                "Groq output filtered",
                "Groq did not complete JSON output",
                "Groq returned empty content",
                "Groq returned invalid JSON",
                "Groq returned missing groups",
                "Groq returned invalid item",
                "Groq returned invalid groups",
                "Groq returned invented evidence",
                "Groq cited nonexistent transactions",
                "Groq returned incomplete batch",
                "Invalid analysis item",
                "Unknown or repeated group",
                "Invalid explanation",
                "Invalid evidence reference",
                "Empty answer",
            }
            cause = str(exc) if isinstance(exc, ValueError) and str(exc) in allowed else type(exc).__name__
            logger.warning("fiscal_ia_groq_invalid_response category=%s backup_available=%s",
                           cause, bool(gemini_key or openrouter_key))
            if not (gemini_key or openrouter_key):
                raise HTTPException(502, "A Groq retornou análise inválida. A conferência permanece disponível.") from None
            groq_failed = True

    gemini_attempted = False
    prefer_gemini = (provider_choice == "gemini" or groq_failed) and bool(gemini_key)
    global gemini_cooldown_until
    if prefer_gemini:
        gemini_attempted = True
        with lock:
            available = time.monotonic() >= gemini_cooldown_until
        if available:
            try:
                answer, used_model = _gemini_completion(payload, gemini_key, gemini_model, legacy=False)
                analyses = _validar_resposta_ia(answer, report, mapping, references, provider="gemini", model=used_model)
                logger.info("fiscal_ia_gemini_success model=%s groups=%d fallback=%s",
                            used_model, len(analyses), groq_failed)
                return {"analises":analyses,
                    "aviso":"Sugestões da IA para revisão humana. Nenhum cálculo ou arquivo foi alterado.",
                    "limite":coverage, "provedor":"gemini", "modelo_usado":used_model,
                    "gratuito":True, "fallback_usado":groq_failed}
            except HTTPException as exc:
                logger.warning("fiscal_ia_gemini_failure status=%d fallback_available=%s",
                               exc.status_code, bool(openrouter_key))
                if not openrouter_key:
                    raise
                if exc.status_code in (429, 502, 503, 504):
                    with lock:
                        gemini_cooldown_until = time.monotonic() + 60
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                logger.warning("fiscal_ia_gemini_invalid_response category=%s fallback_available=%s",
                               type(exc).__name__, bool(openrouter_key))
                if not openrouter_key:
                    raise HTTPException(502, "Não foi possível validar a análise Gemini. A conferência permanece disponível.") from None
    or_failed = False
    if openrouter_key:
        try:
            answer, used_model = _openrouter_completion(payload, models, openrouter_key)
            analyses = _validar_resposta_ia(answer, report, mapping, references, provider="openrouter", model=used_model)
            logger.info("fiscal_ia_openrouter_success model=%s groups=%d",
                        str(used_model).replace("\\n", " ")[:120], len(analyses))
            return {
                "analises": analyses, "aviso": "Sugestões da IA para revisão humana. Nenhum cálculo ou arquivo foi alterado.",
                "limite": coverage, "provedor": "openrouter", "modelo_usado": used_model,
                "gratuito": True, "fallback_usado": gemini_attempted,
            }
        except HTTPException as exc:
            # Apenas informações operacionais seguras, sem mensagens upstream,
            # chaves, prompt, históricos ou contas de clientes.
            logger.warning("fiscal_ia_openrouter_failure status=%d model=%s fallback_available=%s",
                           exc.status_code, models[0] if models else "none", bool(gemini_key))
            # 403/422/503 indicam problema de permissão ou configuração.
            if exc.status_code in (403, 422, 503) and not gemini_key:
                raise
            if not gemini_key:
                raise
            or_failed = True
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            # Nunca registrar o conteúdo livre do modelo nem dados do cliente.
            allowed_causes = {"Invalid analysis item", "Unknown or repeated group",
                "Invalid explanation", "Invalid evidence reference", "Empty answer",
                "Parecer incompleto em lote gratuito", "Resposta de OpenRouter com grupos ausentes"}
            category = str(exc) if isinstance(exc, ValueError) and str(exc) in allowed_causes else type(exc).__name__
            logger.warning("fiscal_ia_openrouter_invalid_response category=%s model=%s fallback_available=%s",
                           category, models[0] if models else "none", bool(gemini_key))
            if not gemini_key:
                raise HTTPException(
                    502, "Não foi possível obter análise válida do OpenRouter. A conferência permanece disponível."
                ) from None
            or_failed = True

    if gemini_key and not gemini_attempted:
        try:
            answer, used_model = _gemini_completion(
                payload, gemini_key, gemini_model, legacy=legacy_direct
            )
            analyses = _validar_resposta_ia(answer, report, mapping, references, provider="gemini", model=used_model)
            logger.info("fiscal_ia_gemini_success model=%s groups=%d fallback=%s",
                        used_model, len(analyses), or_failed)
            return {
                "analises": analyses, "aviso": "Sugestões da IA para revisão humana. Nenhum cálculo ou arquivo foi alterado.",
                "limite": coverage, "provedor": "gemini", "modelo_usado": used_model,
                "gratuito": not legacy_direct, "fallback_usado": or_failed,
            }
        except HTTPException as exc:
            logger.warning("fiscal_ia_gemini_failure status=%d fallback_available=False", exc.status_code)
            if not or_failed:
                raise
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            logger.warning("fiscal_ia_gemini_invalid_response category=%s fallback_available=False",
                           type(exc).__name__)
            if not or_failed:
                raise HTTPException(
                    502, "Não foi possível obter análise válida do Gemini. A conferência permanece disponível."
                ) from None

    raise HTTPException(
        429, "OpenRouter e Gemini gratuito estão indisponíveis ou atingiram seus limites. "
        "Tente novamente mais tarde. Nenhum valor da conferência foi modificado."
    )


@router.get("/status")
@legacy_router.get("/status")
def status():
    openrouter = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    gemini_free = bool(_gemini_free_key())
    legacy = False  # Modo custo zero obrigatório: configuração legada ignorada.
    groq_selected = _groq_enabled() and os.getenv("RAZYNC_AI_PRIMARY") == "groq"
    providers = [p for p, ready in (("groq", _groq_enabled()), ("gemini", gemini_free),
                                   ("openrouter", openrouter)) if ready]
    return {
        "configurado": bool(providers),
        "provedores": providers,
        "provedor": "groq" if groq_selected
            else "gemini" if gemini_free and os.getenv("RAZYNC_AI_PRIMARY", "openrouter") == "gemini"
            else "openrouter" if openrouter
            else "gemini" if (gemini_free or legacy)
            else "groq" if _groq_enabled() else None,
        "gratuito": True,
        "modo_custo_zero_obrigatorio": True,
        "modelo_pago_permitido": False,
        "fallback_gemini": bool((openrouter or groq_selected) and gemini_free),
        "cooperacao": len(providers) > 1,
    }


@router.get("/uso")
def usage_report(response: Response):
    """Relatório de uso local, sem saldos inventados nem dados fiscais."""
    response.headers["Cache-Control"] = "no-store"
    report = daily_report()
    configured = set(status()["provedores"])
    for provider in report["provedores"]:
        provider["configurado"] = provider["id"] in configured
    return report


@router.post("")
@legacy_router.post("")
async def analyze(
    acumuladores: UploadFile = File(...), razao: UploadFile = File(...),
    filial: str = Form(""), empresa_codigo: str = Form(""),
    provedor: Literal["", "openrouter"] = Form(""),
):
    if not status()["configurado"]:
        raise HTTPException(
            503, "IA não configurada. Configure um provedor gratuito e suas permissões no Railway."
        )
    if empresa_codigo and not empresa_codigo.isdigit():
        raise HTTPException(422, "Código da empresa inválido.")
    if filial and not filial.isdigit():
        raise HTTPException(422, "Código da filial inválido.")
    try:
        report = await run_in_threadpool(conferencia_fiscal_preview,
            await acumuladores.read(), acumuladores.filename or "fiscal.xlsx",
            await razao.read(), razao.filename or "razao.xlsx",
            int(empresa_codigo) if empresa_codigo else None, filial or None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if provedor == "openrouter":
        return await run_in_threadpool(explain, report, preferred_provider="openrouter", only_openrouter=True)
    return await run_in_threadpool(explain, report)



def gerar_excel_analise(payload: dict) -> bytes:
    """Exporta a análise já retornada, sem repetir chamadas de IA."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    analises = payload.get("analises")
    if not isinstance(analises, list) or not analises:
        raise ValueError("Não há análises válidas para exportar.")
    if len(json.dumps(payload, ensure_ascii=False, default=str)) > 8_000_000:
        raise ValueError("A análise excede o tamanho permitido para exportação.")

    def texto(value, limite=6000):
        value = str(value if value is not None else "").strip()
        if len(value) > limite:
            raise ValueError("O texto de uma análise excede o limite permitido.")
        # Evita que textos vindos de históricos ou IA virem fórmulas no Excel.
        if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
            return "'" + value
        return value

    def numero(value):
        if value in ("", None):
            return None
        try:
            n = float(value)
            if not -1e15 < n < 1e15:
                raise ValueError()
            return n
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Uma análise contém um valor monetário inválido.") from None

    book = Workbook()
    main = book.active
    main.title = "Análises IA"
    codes = book.create_sheet("Acumuladores")
    evidences = book.create_sheet("Lançamentos citados")
    grounded = book.create_sheet("Fatos e hipóteses")
    grounded.append(["Conta", "Tipo", "Origem dos fatos", "Hipóteses da IA", "Informações faltantes", "Cobertura dos lançamentos", "IA e modelo"])
    cor_titulo, cor_cabecalho, cor_texto = "203B59", "EAF0F7", "30485F"
    main.merge_cells("A1:L1")
    main["A1"] = "RAZYNC | CONFERÊNCIA FISCAL × CONTÁBIL · ANÁLISE ASSISTIDA"
    main["A1"].font = Font(name="Aptos", size=14, bold=True, color="FFFFFF")
    main["A1"].fill = PatternFill("solid", fgColor=cor_titulo)
    main["A1"].alignment = Alignment(vertical="center")
    main.row_dimensions[1].height = 34
    main.merge_cells("A2:L2")
    main["A2"] = "Empresa: " + texto(payload.get("empresa_nome") or "Não identificada", 180)
    main.merge_cells("A3:L3")
    main["A3"] = "As explicações são sugestões de IA para revisão humana. Valores oficiais vêm da conferência."
    main["A3"].font = Font(name="Aptos", size=10, italic=True, color="647B94")
    main.row_dimensions[3].height = 23

    head = ["Conta", "Descrição", "Tipo", "Situação", "Acumuladores",
            "Fiscal", "Contábil considerado", "Total do Razão", "Diferença",
            "Explicação da IA", "O que conferir", "Referências citadas"]
    main.append([""] * len(head))
    main.append(head)
    codes.append(["Conta", "Tipo", "Acumulador", "Descrição", "Valor fiscal"])
    evidences.append(["Conta", "Referência", "Data", "Histórico", "Contrapartida",
                      "Débito", "Crédito", "Tipo"])
    for item in analises:
        if not isinstance(item, dict):
            raise ValueError("Formato inválido de análise da IA.")
        valores = item.get("valores") or {}
        if not isinstance(valores, dict):
            raise ValueError("Valores inválidos no resultado da análise.")
        conta = texto(item.get("conta", ""), 48)
        tipo = texto(item.get("tipo", ""), 48)
        codigos = item.get("detalhes_fiscais") or []
        fatos = item.get("evidencias") or []
        if not isinstance(codigos, list) or not isinstance(fatos, list) or len(codigos) > 100 or len(fatos) > 12:
            raise ValueError("A lista de acumuladores ou lançamentos é inválida.")
        main.append([
            conta, texto(item.get("descricao"), 300), tipo, texto(item.get("situacao"), 80),
            texto(item.get("acumuladores"), 400),
            numero(valores.get("fiscal")), numero(valores.get("contabil")),
            numero(valores.get("total_conta")), numero(valores.get("diferenca")),
            texto(item.get("explicacao")), texto(item.get("verificar")),
            texto(", ".join(str(e.get("referencia", "")) for e in fatos if isinstance(e, dict)), 600)
        ])
        parecer = item.get("parecer") or {}
        if isinstance(parecer, dict) and parecer.get("versao"):
            coverage = parecer.get("cobertura") or {}
            missing = parecer.get("informacoes_faltantes") or []
            if not isinstance(missing, list) or len(missing) > 20:
                raise ValueError("Informações faltantes inválidas.")
            grounded.append([conta, tipo, "Valores oficiais na aba Análises IA; calculados pela ferramenta.",
                texto(parecer.get("hipoteses")), texto("\n".join(str(x) for x in missing)),
                texto(f"{coverage.get('enviados', 0)} de {coverage.get('disponiveis', 0)} lançamentos; "
                      f"históricos abreviados: {'sim' if coverage.get('historicos_abreviados') else 'não'}"),
                texto(" · ".join(str(x) for x in (item.get("provedor"), item.get("modelo_usado")) if x), 300)])
        for code in codigos:
            if not isinstance(code, dict):
                raise ValueError("Acumulador inválido.")
            codes.append([conta, tipo, texto(code.get("codigo"), 40),
                          texto(code.get("descricao"), 500), numero(code.get("valor"))])
        for ev in fatos:
            if not isinstance(ev, dict):
                raise ValueError("Lançamento inválido.")
            evidences.append([
                conta, texto(ev.get("referencia"), 80), texto(ev.get("data"), 40),
                texto(ev.get("historico"), 1800), texto(ev.get("contrapartida"), 80),
                numero(ev.get("debito")), numero(ev.get("credito")), tipo
            ])

    def formato(sheet, header_row, money_columns, widths, height=28):
        sheet.freeze_panes = f"C{header_row + 1}" if header_row == 1 else f"F{header_row + 1}"
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(sheet.max_column)}{sheet.max_row}"
        sheet.row_dimensions[header_row].height = height
        for idx, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(idx)].width = width
        for cell in sheet[header_row]:
            cell.font = Font(name="Aptos", size=10, bold=True, color=cor_titulo)
            cell.fill = PatternFill("solid", fgColor=cor_cabecalho)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for row in sheet.iter_rows(min_row=header_row + 1):
            sheet.row_dimensions[row[0].row].height = 62 if sheet == main else 29
            for cell in row:
                cell.font = Font(name="Aptos", size=10, color=cor_texto)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if cell.column in money_columns and isinstance(cell.value, (int, float)):
                    cell.number_format = '"R$" #,##0.00;-"R$" #,##0.00'
                    cell.alignment = Alignment(vertical="top", horizontal="right")
            if row[0].row % 2 == 0:
                for cell in row:
                    cell.fill = PatternFill("solid", fgColor="F8FAFC")

    formato(main, 5, {6, 7, 8, 9}, [15, 29, 14, 20, 22, 19, 22, 20, 19, 82, 68, 23])
    formato(codes, 1, {5}, [17, 17, 17, 55, 21])
    formato(evidences, 1, {6, 7}, [17, 18, 18, 95, 22, 22, 22, 16])
    formato(grounded, 1, set(), [17, 17, 60, 82, 82, 48, 42])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


@router.post("/exportar")
async def exportar_analise(payload: dict = Body(...)):
    """Gera planilha com o parecer pronto; não chama o provedor novamente."""
    try:
        workbook = await run_in_threadpool(gerar_excel_analise, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="RAZYNC_ANALISE_IA.xlsx"',
                 "Cache-Control": "no-store"},
    )

"""Lotes de IA fiscal com contexto temporário, sem repetir upload ou leitura."""
import secrets
import hashlib
import hmac
import json
import copy
import os
import threading
import time
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from app import fiscal_ai, ai_result_cache
from app.fiscal_ai_audit import ANALYSIS_VERSION
from app.ai_budget import provider_wait_seconds

router = APIRouter(prefix="/api/v1/conferencia-fiscal/ia/sessoes")
_sessions = {}
_guard = threading.RLock()
TTL_SECONDS = 1800
MAX_SESSIONS = 16  # Seis pessoas podem manter conferência e investigação abertas.
_dispatch_cursor = {"curto": 0, "medio": 0}
_cache_secret = secrets.token_bytes(32)
_completed_cache = {}
CACHE_SECONDS = 1800
CACHE_MAX_ENTRIES = 64
_inflight_groups = set()


def _group_id(row):
    return str(row["conta"]), row.get("tipo", "")


def _scope_report(report, accounts):
    # Isola a evidência relevante sem misturar identidade, filial ou período.
    scoped = {key: report[key] for key in (
        "empresa_codigo", "empresa_nome", "filial_aplicada", "periodo_fiscal",
        "periodo_razao", "fonte_fiscal", "escopo_razao", "avisos") if key in report}
    codes = {row["conta"] for row in accounts}
    identities = {_group_id(row) for row in accounts}
    scoped.update(contas=accounts, lancamentos=[row for row in report.get("lancamentos", [])
                                               if row.get("conta") in codes and
                                               ("_tipo_ia" not in row or (str(row["conta"]), row["_tipo_ia"]) in identities)])
    keys = {f'{row["conta"]}:{row["tipo"]}' for row in accounts}
    for field in ("documentos_pendentes", "cobertura_documental", "resumo_documental"):
        if field in report:
            scoped[field] = {k: v for k, v in report[field].items() if k in keys}
    return scoped


def _merge_results(results, accounts):
    items = {_group_id(item): item for result in results for item in result["analises"]}
    providers = list(dict.fromkeys(result.get("provedor") for result in results))
    return {**results[-1], "analises": [items[_group_id(row)] for row in accounts],
            "provedor": providers[0] if len(providers) == 1 else "cooperacao",
            "gratuito": all(result.get("gratuito") is True for result in results),
            "fallback_usado": any(result.get("fallback_usado") for result in results),
            "modelo_usado": "; ".join(dict.fromkeys(result.get("modelo_usado", "") for result in results))}

def _cache_digest(report):
    payload = ANALYSIS_VERSION + ":" + json.dumps(report, ensure_ascii=False, sort_keys=True, default=str)
    return ai_result_cache.stable_digest(payload) or hmac.new(_cache_secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

def _prune_cache():
    now = time.monotonic()
    for key in list(_completed_cache):
        if _completed_cache[key]["expires"] <= now:
            del _completed_cache[key]
    while len(_completed_cache) > CACHE_MAX_ENTRIES:
        del _completed_cache[next(iter(_completed_cache))]



def free_providers():
    providers = []
    if fiscal_ai._groq_enabled():
        providers.append("groq")
    if fiscal_ai._gemini_free_key():
        providers.append("gemini")
    if os.getenv("OPENROUTER_API_KEY", "").strip():
        providers.append("openrouter")
    return providers


def provider_order(providers, extensive):
    # Groq usa amostragem: só atende contas que cabem integralmente nela.
    if extensive:
        return [p for p in ("gemini", "openrouter") if p in providers]
    return [p for p in ("groq", "openrouter", "gemini") if p in providers]


def _get(token):
    with _guard:
        session = _sessions.get(token)
        if session is None or session["expires"] <= time.monotonic():
            discard(token)
            raise HTTPException(410, "A sessão de análise expirou. Anexe os arquivos novamente.")
        return session


def prepare(report):
    providers = free_providers()
    if not providers:
        raise HTTPException(503, "Não há provedor de IA configurado.")
    eligible = [row for row in report["contas"] if row["situacao"] != "CONFERE"]
    indexed = {}
    for i, row in enumerate(report.get("lancamentos", []), 1):
        indexed.setdefault(row.get("conta"), []).append(dict(row, _referencia_ia=row.get("_referencia_ia") or f"L{i}"))
    batches = []
    for start in range(0, len(eligible), 2):
        accounts = eligible[start:start + 2]
        codes = dict.fromkeys(row["conta"] for row in accounts)
        rows = [row for code in codes for row in indexed.get(code, [])]
        # Não usar uma amostra curta para economizar em contas extensas.
        extensive = any(len(indexed.get(code, [])) > 10 or any(
            len(str(row.get("historico") or "")) > 180 for row in indexed.get(code, [])) for code in codes)
        large = any(len(indexed.get(code, [])) > 80 or any(
            len(str(row.get("historico") or "")) > 500 for row in indexed.get(code, [])) for code in codes)
        order = provider_order(providers, extensive)
        order.sort(key=provider_wait_seconds)
        if not order:
            raise HTTPException(503, "Contas extensas precisam de Gemini gratuito ou OpenRouter para preservar os históricos completos.")
        provider = order[0]
        if "openrouter" in order and len(order) > 1 and not large and not provider_wait_seconds("openrouter"):
            category = "medio" if extensive else "curto"
            # Conserva a pequena cota gratuita do OpenRouter: um em quatro
            # lotes adequados, repartidos inclusive entre sessões diferentes.
            with _guard:
                turn = _dispatch_cursor[category]
                _dispatch_cursor[category] += 1
            if turn % 4 == 3:
                provider = "openrouter"
        batches.append({"id": len(batches), "provedor": provider,
                       "criterio": "contexto_integral" if extensive else "contexto_curto",
                       "reservas": [p for p in order if p != provider],
                       "grupos": len(accounts), "report": dict(report, contas=accounts, lancamentos=rows),
                       "result": None, "running": False, "digest": _cache_digest(dict(report, contas=accounts, lancamentos=rows))})
    token = secrets.token_urlsafe(32)
    with _guard:
        now = time.monotonic()
        for expired in [key for key, value in _sessions.items() if value["expires"] <= now]:
            discard(expired)
        if len(_sessions) >= MAX_SESSIONS:
            raise HTTPException(503, "O servidor está com várias análises abertas. Aguarde alguns minutos.")
        session = {"expires": now + TTL_SECONDS, "batches": batches, "active_providers": set()}
        _sessions[token] = session
    # Limpeza também acontece sem novas requisições, inclusive dados financeiros.
    timer = threading.Timer(TTL_SECONDS, discard, args=(token,))
    timer.daemon = True
    session["timer"] = timer
    timer.start()
    return {"sessao": token, "grupos": len(eligible), "registros": len(report.get("lancamentos", [])),
            "cobertura_documental": report.get("cobertura_documental", {}),
            "apoio_documental": report.get("apoio_documental", {}),
            "cooperacao": len(providers) > 1, "provedores": providers,
            "lotes": [{k: batch[k] for k in ("id", "provedor", "grupos", "criterio")} for batch in batches]}


def discard(token):
    with _guard:
        session = _sessions.pop(token, None)
    if session is not None and session.get("timer") is not None:
        session["timer"].cancel()


def _refresh_cached_review(result, report):
    """Atualiza somente as checagens/apresentação locais, sem nova chamada de IA."""
    refreshed = copy.deepcopy(result)
    refreshed["limite"] = (f"Parecer reaproveitado para {len(report.get('contas', []))} grupo(s), "
                           "com as mesmas evidências, filial e período. As checagens locais foram atualizadas sem nova chamada de IA.")
    for item in refreshed.get("analises", []):
        if not isinstance(item, dict) or not isinstance(item.get("valores"), dict) or not item.get("explicacao"):
            continue
        rows = [row for row in report.get("lancamentos", []) if row.get("conta") == item.get("conta")
                and row.get("_tipo_ia", item.get("tipo")) == item.get("tipo")]
        groq = item.get("provedor", result.get("provedor")) == "groq"
        key = f'{item["conta"]}:{item.get("tipo", "")}'
        item["resumo_documental"] = report.get("resumo_documental", {}).get(key, {})
        item["cobertura_documental"] = report.get("cobertura_documental", {}).get(key, {})
        item.setdefault("parecer", {})["comparacoes_documentais"] = report.get("documentos_pendentes", {}).get(key, [])
        # O dossiê e as prioridades permanecem atualizados no reaproveitamento,
        # sem solicitar novas inferências nem confiar em informações antigas.
        from app.fiscal_ai_dossier import build_dossier
        account = next((row for row in report.get("contas", [])
                        if _group_id(row) == _group_id(item)), item)
        item["dossie_contabil"] = build_dossier(
            account, rows, item["parecer"]["comparacoes_documentais"],
            item["resumo_documental"], item["cobertura_documental"])
        fiscal_ai.link_text_evidence(item, rows)
        fiscal_ai.protect_publication(item, rows, item["parecer"]["comparacoes_documentais"])
        item["parecer"] = fiscal_ai.structured_analysis(item, rows,
            sent=min(10, len(rows)) if groq else len(rows),
            shortened=groq and any(len(str(row.get("historico") or "")) > 180 for row in rows),
            documentary=bool(item.get("resumo_documental")) or ("resumo_documental" not in report and report.get("documentos_pendentes") is not None), periodo_fiscal=report.get("periodo_fiscal"))
        item["parecer"]["comparacoes_documentais"] = report.get("documentos_pendentes", {}).get(
            f'{item["conta"]}:{item.get("tipo", "")}', [])
        item["auditoria"] = fiscal_ai.audit_analysis(item)
    return refreshed


def _review_accounts(report, provider):
    """Uma conta/natureza por consulta; preserva sucesso antes de uma falha."""
    results = []
    reused = 0
    for account in report["contas"]:
        scoped = _scope_report(report, [account])
        digest = _cache_digest(scoped)
        with _guard:
            _prune_cache()
            saved = _completed_cache.get(digest)
            stored = saved["result"] if saved else ai_result_cache.read(digest)
        if stored is not None:
            results.append(_refresh_cached_review(stored, scoped))
            reused += 1
            continue
        answer = fiscal_ai.explain(scoped, preferred_provider=provider, only_provider=provider)
        analyses = answer.get("analises") if isinstance(answer, dict) else None
        if not isinstance(analyses, list) or len(analyses) != 1 or not isinstance(analyses[0], dict):
            raise HTTPException(502, "A IA não devolveu a conta solicitada.")
        item = analyses[0]
        if "tipo" not in item and str(item.get("conta")) == str(account["conta"]):
            item = dict(item, tipo=account["tipo"])
        if "conta" not in item or _group_id(item) != _group_id(account):
            raise HTTPException(502, "A resposta da IA pertence a outra conta ou natureza.")
        item = dict(item, provedor=answer.get("provedor"), modelo_usado=answer.get("modelo_usado"))
        answer = dict(answer, analises=[item])
        with _guard:
            _completed_cache[digest] = {"result": copy.deepcopy(answer), "expires": time.monotonic() + CACHE_SECONDS}
            if "auditoria" in item:
                ai_result_cache.write(digest, answer)
        results.append(answer)
    return dict(_merge_results(results, report["contas"]), contas_reutilizadas=reused)


def process(token, batch_id):
    session = _get(token)
    with _guard:
        if batch_id < 0 or batch_id >= len(session["batches"]):
            raise HTTPException(404, "Lote inexistente.")
        batch = session["batches"][batch_id]
        if batch["result"] is not None:
            return batch["result"]
        if batch["running"] or batch["provedor"] in session["active_providers"]:
            raise HTTPException(409, "Já há um lote em andamento neste provedor.")
        _prune_cache()
        cached = _completed_cache.get(batch["digest"])
        if cached is not None:
            batch["result"] = _refresh_cached_review(cached["result"], batch["report"])
            return dict(batch["result"], cache_reutilizado=True)
        persisted = ai_result_cache.read(batch["digest"])
        if persisted is not None:
            batch["result"] = _refresh_cached_review(persisted, batch["report"])
            _completed_cache[batch["digest"]] = {
                "result": copy.deepcopy(persisted), "expires": time.monotonic() + CACHE_SECONDS,
            }
            return dict(batch["result"], cache_reutilizado=True)
        reused, pending, claims = [], [], []
        for account in batch["report"]["contas"]:
            scoped = _scope_report(batch["report"], [account])
            digest = _cache_digest(scoped)
            saved = _completed_cache.get(digest)
            stored = saved["result"] if saved else ai_result_cache.read(digest)
            if stored is not None:
                reused.append(_refresh_cached_review(stored, scoped))
            else:
                pending.append(account)
                claims.append(digest)
        if not pending:
            batch["result"] = dict(_merge_results(reused, batch["report"]["contas"]), cache_reutilizado=True)
            return batch["result"]
        if any(digest in _inflight_groups for digest in claims):
            raise HTTPException(429, "Outra pessoa já está analisando estes dados. Aguarde para reaproveitar o parecer.",
                                headers={"Retry-After": "15"})
        _inflight_groups.update(claims)
        work_report = _scope_report(batch["report"], pending)
        batch["running"] = True
        session["active_providers"].add(batch["provedor"])
    try:
        result = None
        failure = None
        waiting = False
        candidates = [batch["provedor"], *batch["reservas"]]
        candidates.sort(key=provider_wait_seconds)
        for provider in candidates:
            if provider_wait_seconds(provider):
                waiting = True
                continue
            extra_slot = provider != batch["provedor"]
            with _guard:
                if extra_slot and provider in session["active_providers"]:
                    waiting = True
                    continue
                session["active_providers"].add(provider)
            try:
                result = _review_accounts(work_report, provider)
                expected = {_group_id(row) for row in work_report["contas"]}
                analyses = result.get("analises") if isinstance(result, dict) else None
                if not isinstance(analyses, list) or len(analyses) != len(expected):
                    raise HTTPException(502, "A IA não devolveu todas as contas do lote.")
                # Respostas antigas sem tipo são aceitas somente quando a conta
                # tem uma única natureza no lote. Não colapsar entradas e saídas.
                for item in analyses:
                    if isinstance(item, dict) and "tipo" not in item:
                        types = [tipo for code, tipo in expected if code == str(item.get("conta", ""))]
                        if len(types) == 1:
                            item["tipo"] = types[0]
                actual = [_group_id(item) for item in analyses if isinstance(item, dict) and "conta" in item]
                if len(actual) != len(expected) or set(actual) != expected:
                    raise HTTPException(502, "A resposta da IA contém contas incorretas ou repetidas.")
                result = dict(result, fallback_usado=extra_slot)
                break
            except HTTPException as exc:
                result = None
                if exc.status_code not in (429, 502, 503, 504):
                    raise
                failure = exc
            finally:
                if extra_slot:
                    with _guard:
                        session["active_providers"].discard(provider)
        if result is None:
            if waiting:
                raise HTTPException(429, "As IAs de reserva estão ocupadas. Aguarde a fila; os lotes concluídos foram preservados.", headers={"Retry-After": "15"})
            raise failure or HTTPException(429, "As IAs gratuitas estão ocupadas. Os lotes concluídos foram preservados.", headers={"Retry-After": "15"})
        result = dict(result, analises=[dict(item, provedor=item.get("provedor") or result.get("provedor"),
                                          modelo_usado=item.get("modelo_usado") or result.get("modelo_usado")) for item in result["analises"]])
        with _guard:
            for item in result["analises"]:
                account = next(row for row in pending if _group_id(row) == _group_id(item))
                digest = _cache_digest(_scope_report(batch["report"], [account]))
                single = dict(result, analises=[copy.deepcopy(item)], provedor=item.get("provedor"), modelo_usado=item.get("modelo_usado"))
                _completed_cache[digest] = {"result": single, "expires": time.monotonic() + CACHE_SECONDS}
                if "auditoria" in item:
                    ai_result_cache.write(digest, single)
            if reused:
                result = dict(_merge_results([*reused, result], batch["report"]["contas"]),
                              contas_reutilizadas=len(reused) + result.get("contas_reutilizadas", 0))
            batch["result"] = result
            _prune_cache()
            _completed_cache[batch["digest"]] = {
                "result": copy.deepcopy(result),
                "expires": time.monotonic() + CACHE_SECONDS,
            }
            _prune_cache()
            # Só persiste respostas já auditadas, com criptografia no volume existente.
            if all("auditoria" in row for row in result["analises"]):
                ai_result_cache.write(batch["digest"], result)
        return result
    finally:
        with _guard:
            _inflight_groups.difference_update(claims)
            batch["running"] = False
            session["active_providers"].discard(batch["provedor"])


@router.post("")
async def create(acumuladores: UploadFile = File(...), razao: UploadFile = File(...),
                 filial: str = Form(""), empresa_codigo: str = Form(""),
                 entradas: UploadFile | None = File(None), saidas: UploadFile | None = File(None)):
    if not fiscal_ai.status()["configurado"]:
        raise HTTPException(503, "IA não configurada.")
    if (empresa_codigo and not empresa_codigo.isdigit()) or (filial and not filial.isdigit()):
        raise HTTPException(422, "Código de empresa ou filial inválido.")
    try:
        if entradas is not None or saidas is not None:
            from app.fiscal_documentos import preparar_relatorio_pendencias_para_ia
            report = await run_in_threadpool(preparar_relatorio_pendencias_para_ia,
                await acumuladores.read(), acumuladores.filename or "fiscal.xlsx",
                await razao.read(), razao.filename or "razao.xlsx",
                (await entradas.read(), entradas.filename or "entradas.xlsx") if entradas else None,
                (await saidas.read(), saidas.filename or "saidas.xlsx") if saidas else None,
                filial, manter_outros_tipos=True)
        else:
            report = await run_in_threadpool(fiscal_ai.conferencia_fiscal_preview,
                await acumuladores.read(), acumuladores.filename or "fiscal.xlsx",
                await razao.read(), razao.filename or "razao.xlsx",
                int(empresa_codigo) if empresa_codigo else None, filial or None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse(await run_in_threadpool(prepare, report), headers={"Cache-Control": "no-store"})


@router.post("/{token}/lotes/{batch_id}")
async def batch(token: str, batch_id: int):
    return JSONResponse(await run_in_threadpool(process, token, batch_id), headers={"Cache-Control": "no-store"})


@router.delete("/{token}")
def cancel(token: str):
    discard(token)
    return {"ok": True}

"""Lotes de IA fiscal com contexto temporário, sem repetir upload ou leitura."""
import secrets
import os
import threading
import time
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from app import fiscal_ai

router = APIRouter(prefix="/api/v1/conferencia-fiscal/ia/sessoes")
_sessions = {}
_guard = threading.RLock()
TTL_SECONDS = 1800
_dispatch_cursor = {"curto": 0, "medio": 0}


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
        indexed.setdefault(row.get("conta"), []).append(dict(row, _referencia_ia=f"L{i}"))
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
        if not order:
            raise HTTPException(503, "Contas extensas precisam de Gemini gratuito ou OpenRouter para preservar os históricos completos.")
        provider = order[0]
        if "openrouter" in order and len(order) > 1 and not large:
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
                       "result": None, "running": False})
    token = secrets.token_urlsafe(32)
    with _guard:
        now = time.monotonic()
        for expired in [key for key, value in _sessions.items() if value["expires"] <= now]:
            discard(expired)
        if len(_sessions) >= 8:
            raise HTTPException(503, "O servidor está com várias análises abertas. Aguarde alguns minutos.")
        session = {"expires": now + TTL_SECONDS, "batches": batches, "active_providers": set()}
        _sessions[token] = session
    # Limpeza também acontece sem novas requisições, inclusive dados financeiros.
    timer = threading.Timer(TTL_SECONDS, discard, args=(token,))
    timer.daemon = True
    session["timer"] = timer
    timer.start()
    return {"sessao": token, "grupos": len(eligible), "registros": len(report.get("lancamentos", [])),
            "cooperacao": len(providers) > 1, "provedores": providers,
            "lotes": [{k: batch[k] for k in ("id", "provedor", "grupos", "criterio")} for batch in batches]}


def discard(token):
    with _guard:
        session = _sessions.pop(token, None)
    if session is not None and session.get("timer") is not None:
        session["timer"].cancel()


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
        batch["running"] = True
        session["active_providers"].add(batch["provedor"])
    try:
        result = None
        failure = None
        waiting = False
        for provider in [batch["provedor"], *batch["reservas"]]:
            extra_slot = provider != batch["provedor"]
            with _guard:
                if extra_slot and provider in session["active_providers"]:
                    waiting = True
                    continue
                session["active_providers"].add(provider)
            try:
                result = fiscal_ai.explain(batch["report"], preferred_provider=provider, only_provider=provider)
                result = dict(result, fallback_usado=extra_slot)
                break
            except HTTPException as exc:
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
        result = dict(result, analises=[dict(item, provedor=result.get("provedor"),
                                          modelo_usado=result.get("modelo_usado")) for item in result["analises"]])
        with _guard:
            batch["result"] = result
        return result
    finally:
        with _guard:
            batch["running"] = False
            session["active_providers"].discard(batch["provedor"])


@router.post("")
async def create(acumuladores: UploadFile = File(...), razao: UploadFile = File(...),
                 filial: str = Form(""), empresa_codigo: str = Form("")):
    if not fiscal_ai.status()["configurado"]:
        raise HTTPException(503, "IA não configurada.")
    if (empresa_codigo and not empresa_codigo.isdigit()) or (filial and not filial.isdigit()):
        raise HTTPException(422, "Código de empresa ou filial inválido.")
    try:
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

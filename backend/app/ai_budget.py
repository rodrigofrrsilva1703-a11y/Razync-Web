"""Admissão compartilhada por processo; nunca guarda prompts ou respostas."""
from collections import deque
from contextlib import contextmanager
import json
import math
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from fastapi import HTTPException

_guard = threading.RLock()
_windows = {}
_slots = {}
# Telemetria anônima e volátil: por processo/instância, sem prompts, modelos
# financeiros ou chaves. Não representa o saldo da cota no provedor.
_started_at = datetime.now(timezone.utc).isoformat()
_daily = {}
_LOCAL_LIMITS = {"gemini": (15, 250_000), "groq": (30, 8_000), "openrouter": (20, None)}
# Teto cautelar por instância; não representa a cota oficial nem substitui
# um controle distribuído se houver vários workers/instâncias.
_OPENROUTER_DAILY_CAP = 40


def provider_wait_seconds(provider):
    """Pressão da fila local, sem afirmar o saldo oficial do provedor."""
    with _guard:
        now = time.monotonic()
        rpm, tpm = _LOCAL_LIMITS[provider]
        waits = []
        for key, window in _windows.items():
            if key[0] != provider:
                continue
            active = [ticket for ticket in window if now - ticket[0] < 60]
            busy = _slots.get(key)
            if busy is not None and busy.locked():
                waits.append(15)
            elif active and (len(active) >= rpm or tpm and sum(x[1] for x in active) >= tpm):
                waits.append(max(15, math.ceil(60 - (now - active[0][0]))))
            else:
                waits.append(0)
        return min(waits) if waits else 0


def _reserve_daily_free_openrouter(today, observed):
    """Reserva chamada de forma atômica no volume existente do Railway.

    Só armazena dia e quantidade, nunca documentos, tokens ou dados de empresas.
    Em desenvolvimento sem volume, mantém o limite cautelar em memória.
    """
    base = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    if not base:
        if observed >= _OPENROUTER_DAILY_CAP:
            raise HTTPException(429, "Limite gratuito cautelar atingido nesta instância.",
                                headers={"Retry-After": "3600"})
        return
    if not os.path.isdir(base):
        raise HTTPException(503, "Controle persistente indisponível; requisição externa bloqueada.")
    db = os.path.join(base, "razync_ai_free_quota.sqlite3")
    try:
        with sqlite3.connect(db, timeout=5, isolation_level=None) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS free_calls (dia TEXT PRIMARY KEY, quantidade INTEGER NOT NULL)")
            row = conn.execute("SELECT quantidade FROM free_calls WHERE dia = ?", (today,)).fetchone()
            used = row[0] if row else 0
            if used >= _OPENROUTER_DAILY_CAP:
                raise HTTPException(429, "Limite gratuito cautelar diário do OpenRouter atingido.",
                                    headers={"Retry-After": "3600"})
            conn.execute("INSERT INTO free_calls(dia, quantidade) VALUES(?, 1) "
                         "ON CONFLICT(dia) DO UPDATE SET quantidade=quantidade+1", (today,))
            conn.execute("DELETE FROM free_calls WHERE dia < ?", (today,))
            conn.commit()
    except sqlite3.Error:
        raise HTTPException(503, "Controle de cotas indisponível; uso externo bloqueado.") from None


def _counter(provider, model):
    today = datetime.now(timezone.utc).date().isoformat()
    key = (today, provider, model)
    if key not in _daily:
        _daily[key] = {
            "chamadas": 0, "respostas": 0, "falhas": 0,
            "tokens_informados": 0, "respostas_sem_tokens": 0,
            "ultima_chamada": None, "ultima_resposta": None, "ultima_falha": None,
        }
    # Não reter estatísticas de outros dias: apenas o dia corrente.
    for stale in [item for item in _daily if item[0] != today]:
        _daily.pop(stale, None)
    return _daily[key]


def daily_report():
    """Contadores observados por esta instância desde o último reinício.

    Não informa créditos, limites diários ou quotas externas não verificadas.
    """
    providers = []
    with _guard:
        today = datetime.now(timezone.utc).date().isoformat()
        for provider, label in (
            ("groq", "GroqCloud"), ("gemini", "Gemini"), ("openrouter", "OpenRouter")
        ):
            models = []
            for day, name, model in sorted(_daily):
                if day != today or name != provider:
                    continue
                row = _daily[(day, name, model)]
                models.append(dict(modelo=model, **row))
            rpm, tpm = _LOCAL_LIMITS[provider]
            providers.append({
                "id": provider, "nome": label,
                "chamadas": sum(m["chamadas"] for m in models),
                "respostas": sum(m["respostas"] for m in models),
                "falhas": sum(m["falhas"] for m in models),
                "tokens_informados": sum(m["tokens_informados"] for m in models),
                "respostas_sem_tokens": sum(m["respostas_sem_tokens"] for m in models),
                "controle_local": {"requisicoes_minuto": rpm, "tokens_minuto": tpm},
                "cota_diaria_real": None,
                "saldo_diario_real": None,
                "modelos": models,
            })
    return {
        "data_utc": datetime.now(timezone.utc).date().isoformat(),
        "desde_utc": _started_at,
        "escopo": "instancia_atual",
        "observacao": (
            "Uso registrado apenas nesta instância desde o último reinício; "
            "não inclui outros serviços, painéis dos provedores ou chamadas anteriores ao deploy. "
            "As cotas diárias e os saldos reais não são disponibilizados por este endpoint. "
            "Os limites por minuto são controles cautelares do Razync, não cotas oficiais."
        ),
        "provedores": providers,
    }




@contextmanager
def request_slot(provider, model, body):
    # Cotas do console podem ser menores. O upstream continua sendo autoridade.
    key = (provider, model)
    rpm, tpm = _LOCAL_LIMITS[provider]
    content = body.get("messages") if provider != "gemini" else {
        k: body.get(k) for k in ("systemInstruction", "contents")}
    estimate = math.ceil(len(json.dumps(content, ensure_ascii=False).encode("utf-8")) / 3)
    if provider == "groq":
        estimate += body.get("max_completion_tokens", 3000)
    with _guard:
        slot = _slots.setdefault(key, threading.Lock())
    if not slot.acquire(timeout=10):
        raise HTTPException(429, "Há outra análise usando este modelo. Aguarde a fila.",
                            headers={"Retry-After": "15"})
    try:
        with _guard:
            now = time.monotonic()
            window = _windows.setdefault(key, deque())
            while window and now - window[0][0] >= 60:
                window.popleft()
            # Pedidos isolados maiores dependem da cota real do upstream.
            if len(window) >= rpm or (window and tpm and sum(x[1] for x in window) + estimate > tpm):
                wait = max(15, math.ceil(60 - (now - window[0][0]))) if window else 60
                raise HTTPException(429, "Fila da IA aguardando a cota por minuto.",
                                    headers={"Retry-After": str(wait)})
            if provider == "openrouter":
                today = datetime.now(timezone.utc).date().isoformat()
                used = sum(row["chamadas"] for (day, name, _), row in _daily.items()
                           if day == today and name == "openrouter")
                _reserve_daily_free_openrouter(today, used)
            ticket = [now, estimate]
            window.append(ticket)
            counter = _counter(provider, model)
            counter["chamadas"] += 1
            counter["ultima_chamada"] = datetime.now(timezone.utc).isoformat()
        def usage(raw):
            metadata = raw.get("usageMetadata", {}) if provider == "gemini" else raw.get("usage", {})
            actual = (
                metadata.get("totalTokenCount")
                if provider == "gemini" else metadata.get("total_tokens")
            )
            with _guard:
                counter = _counter(provider, model)
                counter["respostas"] += 1
                counter["ultima_resposta"] = datetime.now(timezone.utc).isoformat()
                if isinstance(actual, int) and not isinstance(actual, bool) and actual >= 0:
                    counter["tokens_informados"] += actual
                    ticket[1] = actual
                else:
                    counter["respostas_sem_tokens"] += 1
        try:
            yield usage
        except Exception:
            # Apenas contagem: nunca registrar exceções, conteúdo ou identificação.
            with _guard:
                counter = _counter(provider, model)
                counter["falhas"] += 1
                counter["ultima_falha"] = datetime.now(timezone.utc).isoformat()
            raise
    finally:
        slot.release()

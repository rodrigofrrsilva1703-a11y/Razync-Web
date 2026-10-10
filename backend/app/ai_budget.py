"""Admissão compartilhada por processo; nunca guarda prompts ou respostas."""
from collections import deque
from contextlib import contextmanager
import json
import math
import threading
import time
from fastapi import HTTPException

_guard = threading.RLock()
_windows = {}
_slots = {}


@contextmanager
def request_slot(provider, model, body):
    # Cotas do console podem ser menores. O upstream continua sendo autoridade.
    key = (provider, model)
    limits = {"gemini": (15, 250_000), "groq": (30, 8_000), "openrouter": (20, None)}
    rpm, tpm = limits[provider]
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
                wait = max(15, math.ceil(60 - (now - window[0][0])))
                raise HTTPException(429, "Fila da IA aguardando a cota por minuto.",
                                    headers={"Retry-After": str(wait)})
            ticket = [now, estimate]
            window.append(ticket)
        def usage(raw):
            metadata = raw.get("usageMetadata", {}) if provider == "gemini" else raw.get("usage", {})
            actual = metadata.get("promptTokenCount") if provider == "gemini" else metadata.get("total_tokens")
            if isinstance(actual, int) and actual >= 0:
                with _guard:
                    ticket[1] = actual
        yield usage
    finally:
        slot.release()

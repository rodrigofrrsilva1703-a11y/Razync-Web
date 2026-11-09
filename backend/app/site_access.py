"""Optional private access for the entire application, independent of admin actions."""
from collections import OrderedDict
import hashlib
import json
import os
import secrets
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter, Request as Incoming
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

router = APIRouter(prefix="/api/v1/acesso")
PUBLIC = {("GET", "/health"), ("GET", "/api/v1/acesso/config"), ("POST", "/api/v1/acesso/entrar")}
TTL = 8 * 60 * 60
_sessions = OrderedDict()
_attempts = OrderedDict()
_lock = Lock()


def enabled():
    return os.getenv("RAZYNC_LOGIN_REQUIRED", "0") != "0"


def allowlist():
    return {email.strip().casefold() for email in os.getenv("RAZYNC_LOGIN_EMAILS", "").split(",") if email.strip()}


def configured():
    return bool(allowlist() and os.getenv("RAZYNC_AUTH_URL") and os.getenv("RAZYNC_AUTH_PUBLIC_KEY"))


def reply(status, **data):
    headers = {"Cache-Control": "no-store"}
    if status == 401:
        headers["X-Razync-Login-Required"] = "1"
    return JSONResponse(data, status_code=status, headers=headers)


def fingerprint(token):
    return hashlib.sha256(token.encode()).digest()


def session(request):
    token = request.headers.get("x-razync-session", "")
    if len(token) != 43:
        return None
    with _lock:
        entry = _sessions.get(fingerprint(token))
        if not entry:
            return None
        email, deadline = entry
        if deadline <= time.monotonic() or email not in allowlist():
            _sessions.pop(fingerprint(token), None)
            return None
        return email


class SiteAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not enabled() or request.method == "OPTIONS" or (request.method, request.url.path) in PUBLIC:
            return await call_next(request)
        email = session(request)
        if not email:
            return reply(401, detail="Entre no Razync para continuar.")
        request.state.site_email = email
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response


def verify_password(email, password):
    base = os.getenv("RAZYNC_AUTH_URL", "").rstrip("/")
    key = os.getenv("RAZYNC_AUTH_PUBLIC_KEY", "")
    url = urlparse(base)
    if url.scheme != "https" or not (url.hostname or "").endswith(".supabase.co") or url.netloc != url.hostname or url.path or url.query or url.fragment or not key:
        raise RuntimeError("Acesso não configurado.")
    req = Request(base + "/auth/v1/token?grant_type=password", method="POST",
                  data=json.dumps({"email": email, "password": password}).encode(),
                  headers={"apikey": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as result:
            user = json.load(result).get("user", {})
    except HTTPError as error:
        if error.code in (400, 401, 403, 422):
            return False
        raise RuntimeError("Serviço de login indisponível.") from error
    except (URLError, ValueError, OSError) as error:
        raise RuntimeError("Serviço de login indisponível.") from error
    return bool(user.get("id") and user.get("email_confirmed_at") and user.get("email", "").casefold() == email)


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=512)


@router.get("/config")
def config():
    return reply(200, required=enabled(), available=configured())


@router.post("/entrar")
async def login(request: Incoming):
    if not configured():
        return reply(503, detail="Acesso ainda não configurado.")
    try:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                return reply(413, detail="Dados de login inválidos.")
            body.extend(chunk)
        payload = Login(**json.loads(body))
    except (TypeError, ValueError):
        return reply(400, detail="Dados de login inválidos.")
    email = payload.email.strip().casefold()
    if email not in allowlist():
        return reply(401, detail="E-mail ou senha inválidos.")
    now = time.monotonic()
    ip = request.client.host if request.client else ""
    with _lock:
        for client, (until, _) in list(_attempts.items()):
            if until <= now:
                _attempts.pop(client, None)
        if ip not in _attempts and len(_attempts) >= 2048:
            return reply(429, detail="Tente novamente em alguns minutos.")
        until, attempts = _attempts.get(ip, (now + 60, 0))
        if attempts >= 6:
            return reply(429, detail="Muitas tentativas. Aguarde um minuto.")
        _attempts[ip] = until, attempts + 1
    try:
        valid = await run_in_threadpool(verify_password, email, payload.password)
    except RuntimeError:
        return reply(503, detail="Não foi possível validar o acesso agora.")
    if not valid:
        return reply(401, detail="E-mail ou senha inválidos.")
    token = secrets.token_urlsafe(32)
    with _lock:
        for key, (_, deadline) in list(_sessions.items()):
            if deadline <= now:
                _sessions.pop(key, None)
        _sessions[fingerprint(token)] = email, now + TTL
        while len(_sessions) > 256:
            _sessions.popitem(last=False)
    return reply(200, session=token, email=email)


@router.get("/sessao")
def whoami(request: Incoming):
    email = session(request)
    return reply(200, email=email) if email else reply(401, detail="Sessão encerrada.")


@router.post("/sair")
def logout(request: Incoming):
    with _lock:
        _sessions.pop(fingerprint(request.headers.get("x-razync-session", "")), None)
    return reply(200, ok=True)

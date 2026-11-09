"""Optional private access for the entire application, independent of admin actions."""
from collections import OrderedDict
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import secrets
import sqlite3
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
TTL = 12 * 60 * 60
MAX_AGE = 7 * 24 * 60 * 60
TOUCH_INTERVAL = 5 * 60
_sessions = OrderedDict()
_attempts = OrderedDict()
_lock = Lock()
current_owner = ContextVar('site_access_owner', default=None)


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


@contextmanager
def session_database(volume):
    path = Path(volume) / "razync_sessions.sqlite3"
    # Restrictive permissions on the database; only hashes of session tokens are saved.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=3)
    try:
        db.execute("CREATE TABLE IF NOT EXISTS sessions (digest BLOB PRIMARY KEY, "
                   "email TEXT NOT NULL, expires REAL NOT NULL, last_seen REAL NOT NULL)")
        with db:
            yield db
    finally:
        db.close()


def session(request):
    token = request.headers.get("x-razync-session", "")
    if len(token) != 43:
        return None
    digest = fingerprint(token)
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    now = time.time()
    if volume:
        with session_database(volume) as db:
            entry = db.execute("SELECT email, expires, last_seen FROM sessions WHERE digest=?", (digest,)).fetchone()
            if not entry:
                return None
            email, expires, last_seen = entry
            if expires <= now or last_seen + TTL <= now or email not in allowlist():
                db.execute("DELETE FROM sessions WHERE digest=?", (digest,))
                return None
            if last_seen + TOUCH_INTERVAL <= now:
                db.execute("UPDATE sessions SET last_seen=? WHERE digest=? AND last_seen<?", (now, digest, now))
            return email
    with _lock:
        entry = _sessions.get(digest)
        if not entry:
            return None
        email, expires, last_seen = entry
        if expires <= now or last_seen + TTL <= now or email not in allowlist():
            _sessions.pop(digest, None)
            return None
        _sessions[digest] = email, expires, now
        _sessions.move_to_end(digest)
        return email


def save_session(token, email):
    now = time.time()
    digest = fingerprint(token)
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if volume:
        with session_database(volume) as db:
            db.execute("DELETE FROM sessions WHERE expires <= ? OR last_seen <= ?", (now, now - TTL))
            db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest, email, now + MAX_AGE, now))
            db.execute("DELETE FROM sessions WHERE digest IN (SELECT digest FROM sessions ORDER BY last_seen DESC LIMIT -1 OFFSET 256)")
        return
    with _lock:
        for key, (_, expires, last_seen) in list(_sessions.items()):
            if expires <= now or last_seen + TTL <= now:
                _sessions.pop(key, None)
        _sessions[digest] = email, now + MAX_AGE, now
        while len(_sessions) > 256:
            _sessions.popitem(last=False)


class SiteAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not enabled() or request.method == "OPTIONS" or (request.method, request.url.path) in PUBLIC:
            return await call_next(request)
        try:
            email = await run_in_threadpool(session, request)
        except (sqlite3.Error, OSError):
            return reply(503, detail="Não foi possível verificar a sessão agora.")
        if not email:
            return reply(401, detail="Entre no Razync para continuar.")
        request.state.site_email = email
        scope = current_owner.set(email)
        try:
            response = await call_next(request)
        finally:
            current_owner.reset(scope)
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
    try:
        await run_in_threadpool(save_session, token, email)
    except (sqlite3.Error, OSError):
        return reply(503, detail="Não foi possível iniciar a sessão agora.")
    return reply(200, session=token, email=email)


@router.get("/sessao")
def whoami(request: Incoming):
    try:
        email = getattr(request.state, "site_email", None) or session(request)
    except (sqlite3.Error, OSError):
        return reply(503, detail="Não foi possível verificar a sessão agora.")
    return reply(200, email=email) if email else reply(401, detail="Sessão encerrada.")


@router.post("/sair")
def logout(request: Incoming):
    digest = fingerprint(request.headers.get("x-razync-session", ""))
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    try:
        if volume:
            with session_database(volume) as db:
                db.execute("DELETE FROM sessions WHERE digest=?", (digest,))
        else:
            with _lock:
                _sessions.pop(digest, None)
    except (sqlite3.Error, OSError):
        return reply(503, detail="Não foi possível encerrar a sessão no servidor.")
    return reply(200, ok=True)

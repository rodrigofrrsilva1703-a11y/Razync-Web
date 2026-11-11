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
    touch = not (
        getattr(request, "method", None) == "GET"
        and request.url.path == "/api/v1/company-access/notifications"
    )
    if volume:
        with session_database(volume) as db:
            entry = db.execute("SELECT email, expires, last_seen FROM sessions WHERE digest=?", (digest,)).fetchone()
            if not entry:
                return None
            email, expires, last_seen = entry
            if expires <= now or last_seen + TTL <= now or email not in allowlist():
                db.execute("DELETE FROM sessions WHERE digest=?", (digest,))
                return None
            if touch and last_seen + TOUCH_INTERVAL <= now:
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
        if touch:
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


def auth_connection():
    base = os.getenv("RAZYNC_AUTH_URL", "").rstrip("/")
    key = os.getenv("RAZYNC_AUTH_PUBLIC_KEY", "")
    url = urlparse(base)
    if url.scheme != "https" or not (url.hostname or "").endswith(".supabase.co") or url.netloc != url.hostname or url.path or url.query or url.fragment or not key:
        raise RuntimeError("Acesso não configurado.")
    return base, key


def authenticate(email, password):
    base, key = auth_connection()
    req = Request(base + "/auth/v1/token?grant_type=password", method="POST",
                  data=json.dumps({"email": email, "password": password}).encode(),
                  headers={"apikey": key, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as result:
            data = json.load(result)
            user = data.get("user", {})
    except HTTPError as error:
        if error.code in (400, 401, 403, 422):
            return None
        raise RuntimeError("Serviço de login indisponível.") from error
    except (URLError, ValueError, OSError) as error:
        raise RuntimeError("Serviço de login indisponível.") from error
    token = data.get("access_token")
    if user.get("id") and user.get("email_confirmed_at") and user.get("email", "").casefold() == email and isinstance(token, str) and token:
        return token
    return None


def verify_password(email, password):
    return bool(authenticate(email, password))


def update_password(token, password):
    base, key = auth_connection()
    request = Request(base + "/auth/v1/user", method="PUT",
                      data=json.dumps({"password": password}).encode(),
                      headers={"apikey": key, "Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return response.status == 200


def revoke_other_sessions(email, keep):
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if volume:
        with session_database(volume) as db:
            db.execute("DELETE FROM sessions WHERE email=? AND digest<>?", (email, keep))
    else:
        with _lock:
            for digest, entry in list(_sessions.items()):
                if digest != keep and entry[0] == email:
                    _sessions.pop(digest, None)



class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=512)


@router.get("/config")
def config():
    return reply(200, required=enabled(), available=configured())


def allow_attempt(request):
    now = time.monotonic()
    ip = request.client.host if request.client else ""
    with _lock:
        for client, (until, _) in list(_attempts.items()):
            if until <= now:
                _attempts.pop(client, None)
        if ip not in _attempts and len(_attempts) >= 2048:
            return False
        until, attempts = _attempts.get(ip, (now + 60, 0))
        if attempts >= 6:
            return False
        _attempts[ip] = until, attempts + 1
    return True


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
    if not allow_attempt(request):
        return reply(429, detail="Muitas tentativas. Aguarde um minuto.")
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


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/alterar-senha")
async def change_password(request: Incoming):
    email = getattr(request.state, "site_email", None)
    if not email:
        return reply(401, detail="Entre na sua conta para alterar a senha.")
    try:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                return reply(413, detail="Dados de senha inválidos.")
            body.extend(chunk)
        payload = PasswordChange.model_validate_json(body)
        if len(payload.new_password.encode("utf-8")) > 72:
            raise ValueError()
    except (ValueError, TypeError):
        return reply(422, detail="A nova senha precisa ter pelo menos 8 caracteres e no máximo 72 bytes.")
    if payload.current_password == payload.new_password:
        return reply(422, detail="Escolha uma senha diferente da atual.")
    if not allow_attempt(request):
        return reply(429, detail="Muitas tentativas. Aguarde um minuto.")
    try:
        token = await run_in_threadpool(authenticate, email, payload.current_password)
        if not token:
            return reply(400, detail="A senha atual não confere.")
        if not await run_in_threadpool(update_password, token, payload.new_password):
            return reply(503, detail="Não foi possível confirmar a alteração da senha.")
    except HTTPError as error:
        if error.code in (400, 422):
            return reply(422, detail="O serviço de autenticação recusou a nova senha. Escolha outra.")
        if error.code == 429:
            return reply(429, detail="Muitas tentativas. Aguarde um minuto.")
        return reply(503, detail="Não foi possível confirmar a alteração da senha.")
    except (RuntimeError, OSError):
        return reply(503, detail="Não foi possível confirmar a alteração da senha.")
    try:
        await run_in_threadpool(revoke_other_sessions, email, fingerprint(request.headers.get("x-razync-session", "")))
    except (sqlite3.Error, OSError):
        return reply(200, ok=True, sessions_revoked=False)
    return reply(200, ok=True, sessions_revoked=True)


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

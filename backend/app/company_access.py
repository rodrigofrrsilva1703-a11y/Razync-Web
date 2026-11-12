"""Company ownership and access decisions for authenticated users."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.site_access import allowlist, current_owner, set_user_suspended, suspended_users, user_presence

router = APIRouter(prefix="/api/v1/company-access")


def administrators():
    return {email.strip().casefold() for email in os.getenv("RAZYNC_ADMIN_EMAILS", "").split(",") if email.strip()}


def is_admin():
    email = current_owner.get()
    return bool(email and email in administrators())


def _db():
    from app.classification_service import DB_PATH

    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    path = Path(volume) / "company-owners.sqlite3" if volume else DB_PATH.with_name("company-owners.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS company_owners (company INTEGER PRIMARY KEY, email TEXT NOT NULL)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS company_notifications ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, company INTEGER NOT NULL, "
        "name TEXT NOT NULL, recipient TEXT NOT NULL, created_at TEXT NOT NULL, "
        "read_at TEXT)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS company_notifications_recipient "
        "ON company_notifications(recipient, id DESC)"
    )
    db.execute("CREATE TABLE IF NOT EXISTS archived_companies (company INTEGER PRIMARY KEY)")
    db.execute("""CREATE TABLE IF NOT EXISTS monthly_task_messages (
        id INTEGER PRIMARY KEY, period TEXT NOT NULL, company INTEGER NOT NULL,
        owner TEXT NOT NULL, sender TEXT NOT NULL, kind TEXT NOT NULL,
        body TEXT NOT NULL, created_at TEXT NOT NULL, reply_to INTEGER
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS monthly_task_messages_scope
        ON monthly_task_messages(period,company,owner,id)""")
    db.execute("""CREATE TABLE IF NOT EXISTS monthly_task_notices (
        notice INTEGER PRIMARY KEY, message INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS direct_notification_messages (
        notice INTEGER PRIMARY KEY, sender TEXT NOT NULL, body TEXT NOT NULL
    )""")
    return db


def owners():
    with closing(_db()) as db:
        return dict(db.execute("SELECT company,email FROM company_owners"))


def archived_codes():
    with closing(_db()) as db:
        return {row[0] for row in db.execute("SELECT company FROM archived_companies")}


def owner_for(code, assignments):
    return assignments.get(int(code), os.getenv("RAZYNC_DEFAULT_COMPANY_OWNER", "").strip().casefold())


def allowed_codes():
    """None represents an unrestricted administrator or legacy deployment."""
    if not administrators() or is_admin():
        return None
    from app.company_service import catalog

    email = current_owner.get()
    if not email:
        return set()
    assignments = owners()
    return {int(row["codigo"]) for row in catalog() if owner_for(row["codigo"], assignments) == email}


def require_company_access(request: Request):
    if not administrators():
        return
    code = request.path_params.get("company_code")
    path = request.url.path
    if code is None and path.startswith(("/api/v1/conferencia-fiscal/ia", "/api/v1/conferencia-fiscal/242/ia")):
        code = 242
    if str(code).isascii() and str(code).isdigit() and len(str(code)) <= 9 and int(code) in archived_codes():
        raise HTTPException(404, "Empresa removida do catálogo.")
    if is_admin():
        return
    if path.startswith("/api/v1/tasks/manual"):
        raise HTTPException(403, "Apenas administradores podem gerenciar tarefas manuais.")
    if code is not None and str(code).isdigit() and int(code) not in allowed_codes():
        raise HTTPException(403, "Você não tem acesso a esta empresa.")


def _require_admin():
    if not is_admin():
        raise HTTPException(403, "Apenas administradores podem gerenciar responsáveis.")


@router.get("/me")
def profile():
    return {"enabled": bool(administrators()), "admin": is_admin()}


@router.get("/users")
def list_users():
    _require_admin()
    blocked = suspended_users()
    admins = administrators()
    presence = user_presence()
    return {"users": [
        {"email": email, "admin": email in admins, "suspended": email in blocked, "self": email == current_owner.get(),
         **presence.get(email, {"connected": False, "active": False, "last_active": None, "inactive_since": None})}
        for email in sorted(allowlist())
    ]}


class UserAccess(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    suspended: bool = Field(strict=True)


@router.put("/users")
def update_user_access(payload: UserAccess):
    _require_admin()
    email = payload.email.strip().casefold()
    if email not in allowlist():
        raise HTTPException(404, "Conta não encontrada.")
    try:
        set_user_suspended(current_owner.get(), email, payload.suspended)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"email": email, "suspended": payload.suspended}


@router.get("/assignments")
def list_assignments():
    _require_admin()
    from app.company_service import catalog

    assignments = owners()
    return {
        "users": sorted(allowlist()),
        "companies": [
            {"codigo": row["codigo"], "nome": row["nome"], "email": owner_for(row["codigo"], assignments)}
            for row in catalog()
        ],
    }


@router.delete("/companies/{company_code}")
def archive_company(company_code: int):
    _require_admin()
    from app.company_service import catalog

    if not any(int(row["codigo"]) == company_code for row in catalog()):
        raise HTTPException(404, "Empresa não cadastrada.")
    with closing(_db()) as db, db:
        db.execute("INSERT INTO archived_companies VALUES (?) ON CONFLICT DO NOTHING", (company_code,))
    return {"codigo": company_code}


class Assignment(BaseModel):
    email: str


@router.put("/assignments/{company_code}")
def set_assignment(company_code: int, payload: Assignment):
    _require_admin()
    from app.company_service import catalog

    email = payload.email.strip().casefold()
    if email not in allowlist():
        raise HTTPException(422, "Selecione um usuário autorizado a acessar o site.")
    company = next((row for row in catalog() if int(row["codigo"]) == company_code), None)
    if company is None:
        raise HTTPException(404, "Empresa não cadastrada.")
    with closing(_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM archived_companies WHERE company=?", (company_code,)).fetchone():
            raise HTTPException(404, "Empresa removida do catálogo.")
        row = db.execute("SELECT email FROM company_owners WHERE company=?", (company_code,)).fetchone()
        previous_email = owner_for(company_code, {company_code: row[0]} if row else {})
        changed = previous_email != email
        if changed:
            db.execute(
                "INSERT INTO company_owners(company,email) VALUES(?,?) "
                "ON CONFLICT(company) DO UPDATE SET email=excluded.email",
                (company_code, email),
            )
            db.execute(
                "INSERT INTO company_notifications(company,name,recipient,created_at) VALUES(?,?,?,?)",
                (company_code, company["nome"], email, datetime.now(timezone.utc).isoformat()),
            )
    return {"codigo": company_code, "email": email, "changed": changed}


def _notification_recipient():
    email = current_owner.get()
    if not email:
        raise HTTPException(401, "Entre na sua conta para consultar as notificações.")
    return email


@router.get("/notifications")
def list_notifications():
    email = _notification_recipient()
    visible = (
        " FROM company_notifications n LEFT JOIN company_owners o ON o.company=n.company "
        "LEFT JOIN monthly_task_notices link ON link.notice=n.id "
        "LEFT JOIN monthly_task_messages m ON m.id=link.message "
        "LEFT JOIN direct_notification_messages d ON d.notice=n.id WHERE n.recipient=? "
        "AND (d.notice IS NOT NULL OR (m.id IS NULL AND o.email=n.recipient) OR "
        "(m.owner=COALESCE(o.email,?) AND (m.owner=n.recipient OR ?))) "
        "AND NOT EXISTS (SELECT 1 FROM archived_companies a WHERE a.company=n.company)"
    )
    params = (email, owner_for(0, {}), is_admin())
    with closing(_db()) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        items = [dict(row) for row in db.execute(
            "SELECT n.id,n.company,n.name,n.created_at,n.read_at,m.period,"
            "CASE WHEN d.notice IS NOT NULL THEN 'direct' ELSE m.kind END AS kind,"
            "COALESCE(d.body,m.body) AS body,COALESCE(d.sender,m.sender) AS sender" + visible +
            " ORDER BY n.id DESC LIMIT 50", params,
        )]
        unread = db.execute("SELECT count(*)" + visible + " AND n.read_at IS NULL", params).fetchone()[0]
    result = {"items": items, "unread": unread}
    if is_admin():
        result["recipients"] = sorted(notification_collaborators())
    return result


def notification_collaborators():
    return allowlist() - administrators() - suspended_users()


class DirectNotification(BaseModel):
    recipient: str = Field(max_length=254)
    body: str = Field(max_length=2000)


@router.post("/notifications/send", status_code=201)
def send_notification(payload: DirectNotification):
    _require_admin()
    sender = _notification_recipient()
    recipient = payload.recipient.strip().casefold()
    body = payload.body.strip()
    if not body or recipient not in notification_collaborators():
        raise HTTPException(422, "Escolha um colaborador ativo e escreva uma mensagem.")
    with closing(_db()) as db, db:
        # Direct notices share the inbox sequence and have no associated company.
        notice = db.execute(
            "INSERT INTO company_notifications(company,name,recipient,created_at) VALUES(0,'',?,?)",
            (recipient, datetime.now(timezone.utc).isoformat()),
        ).lastrowid
        db.execute("INSERT INTO direct_notification_messages VALUES(?,?,?)", (notice, sender, body))
    return {"ok": True}


class ReadNotifications(BaseModel):
    through: int = Field(gt=0, le=9223372036854775807)
    single: bool = False


@router.post("/notifications/read")
def mark_notifications_read(payload: ReadNotifications):
    email = _notification_recipient()
    with closing(_db()) as db, db:
        db.execute(
            "UPDATE company_notifications SET read_at=? "
            "WHERE recipient=? AND id<=? AND read_at IS NULL AND (NOT ? OR id=?)",
            (datetime.now(timezone.utc).isoformat(), email, payload.through, payload.single, payload.through),
        )
    return {"ok": True}

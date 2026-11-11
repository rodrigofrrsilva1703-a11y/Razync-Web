"""Company ownership and access decisions for authenticated users."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.site_access import allowlist, current_owner

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
    return db


def owners():
    with closing(_db()) as db:
        return dict(db.execute("SELECT company,email FROM company_owners"))


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
    if not administrators() or is_admin():
        return
    code = request.path_params.get("company_code")
    path = request.url.path
    if code is None and path.startswith(("/api/v1/conferencia-fiscal/ia", "/api/v1/conferencia-fiscal/242/ia")):
        code = 242
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


class Assignment(BaseModel):
    email: str


@router.put("/assignments/{company_code}")
def set_assignment(company_code: int, payload: Assignment):
    _require_admin()
    from app.company_service import catalog

    email = payload.email.strip().casefold()
    if email not in allowlist():
        raise HTTPException(422, "Selecione um usuário autorizado a acessar o site.")
    if not any(int(row["codigo"]) == company_code for row in catalog()):
        raise HTTPException(404, "Empresa não cadastrada.")
    with closing(_db()) as db, db:
        db.execute(
            "INSERT INTO company_owners(company,email) VALUES(?,?) "
            "ON CONFLICT(company) DO UPDATE SET email=excluded.email",
            (company_code, email),
        )
    return {"codigo": company_code, "email": email}

"""Monthly accounting checklist, scoped to the current company portfolio."""
import io
import json
import re
from collections import defaultdict
from contextlib import closing
from datetime import date
from typing import Literal
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, File, HTTPException, UploadFile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field
from razync.task_deadlines import PRAZOS_EMPRESAS_DIAS, calcular_prioridade_empresa, obter_competencia_operacional

from app import company_access
from app.company_service import catalog
from app.site_access import current_owner

router = APIRouter(prefix="/api/v1/monthly-tasks")
STEP_LABELS = ("Documentos recebidos", "Conciliação bancária", "Dívida ativa", "Folha", "Fiscal", "Fechamento")
EMPTY = {"steps": ["pending"] * len(STEP_LABELS), "issue": "", "action": "", "issue_status": "none"}
MAX_UPLOAD = 8 * 1024 * 1024


class TaskUpdate(BaseModel):
    steps: list[Literal["pending", "done", "na"]] = Field(min_length=6, max_length=6)
    issue: str = Field(max_length=3000)
    action: str = Field(max_length=3000)
    issue_status: Literal["none", "open", "resolved"]
    revision: int = Field(ge=0)


def db_connection():
    db = company_access._db()
    db.execute("""CREATE TABLE IF NOT EXISTS monthly_accounting_tasks (
        period TEXT NOT NULL, company INTEGER NOT NULL, payload TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (period, company)
    )""")
    return db


def period_date(value):
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", value):
        raise HTTPException(422, "Informe uma competência válida.")
    return date.fromisoformat(value + "-01")


def identity():
    email = current_owner.get()
    if not email:
        raise HTTPException(401, "Entre na sua conta para acompanhar as tarefas.")
    return email, company_access.is_admin()


def task_metrics(steps):
    done = steps.count("done")
    applicable = len(steps) - steps.count("na")
    status = "na" if not applicable else "done" if done == applicable else "progress" if done else "pending"
    return {"done": done, "applicable": applicable, "status": status,
            "percent": round(100 * done / applicable) if applicable else 0}


@router.get("")
def dashboard(period: str | None = None):
    email, admin = identity()
    today, current = obter_competencia_operacional()
    period = period or current.isoformat()[:7]
    month = period_date(period)
    companies = catalog()
    with closing(db_connection()) as db, db:
        db.execute("BEGIN")
        assignments = dict(db.execute("SELECT company,email FROM company_owners"))
        stored = {code: (json.loads(payload), revision) for code, payload, revision in db.execute(
            "SELECT company,payload,revision FROM monthly_accounting_tasks WHERE period=?", (period,),
        )}
    rows = []
    groups = defaultdict(lambda: dict(companies=0, completed=0, done=0, applicable=0, issues=0))
    for company in companies:
        code = int(company["codigo"])
        owner = company_access.owner_for(code, assignments)
        if not admin and owner != email:
            continue
        entry, revision = stored.get(code, (EMPTY, 0))
        metrics = task_metrics(entry["steps"])
        deadline = None
        if str(company.get("regime", "")).casefold().strip() in PRAZOS_EMPRESAS_DIAS:
            deadline = calcular_prioridade_empresa(company, {}, today, month)["vencimento"].isoformat()
        row = {"code": code, "name": company["nome"], "owner": owner, "due": deadline,
               "revision": revision, **entry, **metrics}
        rows.append(row)
        if admin:
            group = groups[owner]
            group["companies"] += 1
            group["completed"] += metrics["status"] == "done"
            group["done"] += metrics["done"]
            group["applicable"] += metrics["applicable"]
            group["issues"] += entry["issue_status"] == "open"
    return {"period": period, "admin": admin, "steps": STEP_LABELS,
            "companies": sorted(rows, key=lambda row: row["code"]),
            "progress": [{"owner": owner, **counts} for owner, counts in sorted(groups.items())]}


@router.put("/{period}/{company_code}")
def save_task(period: str, company_code: int, update: TaskUpdate):
    period_date(period)
    email, admin = identity()
    if not any(int(row["codigo"]) == company_code for row in catalog()):
        raise HTTPException(404, "Empresa não cadastrada.")
    data = update.model_dump(exclude={"revision"})
    if data["issue_status"] == "open" and not data["issue"].strip():
        raise HTTPException(422, "Descreva a pendência aberta.")
    with closing(db_connection()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        assigned = db.execute("SELECT email FROM company_owners WHERE company=?", (company_code,)).fetchone()
        owner = company_access.owner_for(company_code, {company_code: assigned[0]} if assigned else {})
        if not admin and owner != email:
            raise HTTPException(403, "Esta empresa não está na sua carteira.")
        existing = db.execute(
            "SELECT revision FROM monthly_accounting_tasks WHERE period=? AND company=?", (period, company_code),
        ).fetchone()
        if (existing[0] if existing else 0) != update.revision:
            raise HTTPException(409, "A tarefa foi atualizada em outra sessão. Atualize a lista antes de salvar.")
        db.execute(
            "INSERT INTO monthly_accounting_tasks(period,company,payload,revision) VALUES(?,?,?,?) "
            "ON CONFLICT(period,company) DO UPDATE SET payload=excluded.payload,revision=excluded.revision",
            (period, company_code, json.dumps(data, ensure_ascii=False), update.revision + 1),
        )
    return {"revision": update.revision + 1, **data, **task_metrics(data["steps"])}


def normalized(value):
    return str(value if value is not None else "").strip()


def workbook_records(content):
    with ZipFile(io.BytesIO(content)) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > 48 * 1024 * 1024:
            raise ValueError("Planilha descompactada acima do limite.")
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        records = {}
        for sheet in book:
            match = re.fullmatch(r"(0[1-9]|1[0-2])(20\d{2})", sheet.title)
            if not match:
                continue
            month, year = match.groups()
            if sheet.max_row and sheet.max_row > 5000:
                raise ValueError("A aba mensal excede o limite de 5.000 linhas.")
            rows = sheet.iter_rows(max_row=5001, max_col=19, values_only=True)
            header = next(rows, ())
            if not header or normalized(header[0]).casefold() not in {"cód", "cod", "código", "codigo"} or normalized(header[8]).casefold() != "documentos recebidos" or normalized(header[13]).casefold() != "fechamento":
                raise ValueError("Cabeçalho da aba mensal incompatível com o controle gerencial.")
            for row in rows:
                code = normalized(row[0])
                if not code.isdecimal() or len(code) > 9 or not normalized(row[1]):
                    continue
                key = (f"{year}-{month}", int(code))
                if key in records:
                    raise ValueError("Há códigos de empresa repetidos na mesma competência.")
                steps = []
                for value in row[8:14]:
                    state = normalized(value).casefold()
                    if state not in {"", "ok", "-", "–", "—"}:
                        raise ValueError("Há etapas com situação desconhecida. Use OK, traço ou deixe em branco.")
                    steps.append("done" if state == "ok" else "na" if state else "pending")
                issue, action, state = map(normalized, row[16:19])
                if max(len(issue), len(action)) > 3000:
                    raise ValueError("Uma pendência ou tratativa excede 3.000 caracteres.")
                resolved = state.casefold() in {"resolvida", "concluída", "fechada", "baixada"}
                records[key] = {"steps": steps, "issue": issue, "action": action,
                                "issue_status": "resolved" if resolved else "open" if issue else "none"}
        if not records:
            raise ValueError("Nenhum registro encontrado nas abas de competência (MMAAAA).")
        return records
    finally:
        book.close()


@router.post("/import")
def import_workbook(file: UploadFile = File(...)):
    _, admin = identity()
    if not admin:
        raise HTTPException(403, "Apenas administradores podem importar o controle gerencial.")
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "A planilha deve ter até 8 MB.")
    try:
        records = workbook_records(content)
    except (BadZipFile, InvalidFileException, OSError, KeyError, ValueError, ParseError) as exc:
        message = str(exc) if type(exc) is ValueError else "Não foi possível ler a planilha XLSX."
        raise HTTPException(422, message) from exc
    known = {int(row["codigo"]) for row in catalog()}
    missing = set()
    imported = preserved = 0
    with closing(db_connection()) as db, db:
        for (period, code), data in records.items():
            if code not in known:
                missing.add(code)
                continue
            result = db.execute(
                "INSERT INTO monthly_accounting_tasks(period,company,payload) VALUES(?,?,?) "
                "ON CONFLICT(period,company) DO NOTHING",
                (period, code, json.dumps(data, ensure_ascii=False)),
            )
            imported += result.rowcount
            preserved += 1 - result.rowcount
    return {"imported": imported, "preserved": preserved, "missing": sorted(missing)}

"""Apply an administrator-supplied company roster from private deployment configuration."""
import json
import logging
import os
from contextlib import closing

from app import company_access, company_service

logger = logging.getLogger("uvicorn.error")


def import_configured_companies():
    raw = os.getenv("RAZYNC_COMPANY_IMPORT")
    if not raw:
        return

    roster = json.loads(raw)
    if not company_access.administrators():
        raise RuntimeError("Configure administradores antes de importar carteiras.")
    authorized = company_access.allowlist()
    existing = {int(row["codigo"]): row for row in company_service.catalog()}
    regimes = {"Não informado", "LUCRO REAL", "LUCRO PRESUMIDO", "SIMPLES NACIONAL"}
    eligible = []
    pending = set()
    seen = set()
    for code, name, regime, email in roster:
        if (
            type(code) is not int
            or not 1 <= code <= 999999999
            or code in seen
            or not name.strip()
            or len(name) > 160
            or regime not in regimes
        ):
            raise ValueError("Cadastro de empresas inválido para importação.")
        seen.add(code)
        if email not in authorized or (code in existing and existing[code]["nome"] != name):
            pending.add(code)
            continue
        eligible.append((code, name, regime, email))

    with closing(company_access._db()) as db, db:
        for code, _, _, email in eligible:
            cursor = db.execute(
                "INSERT INTO company_owners(company,email) VALUES(?,?) "
                "ON CONFLICT(company) DO NOTHING",
                (code, email),
            )
            if cursor.rowcount == 0:
                owner = db.execute("SELECT email FROM company_owners WHERE company=?", (code,)).fetchone()[0]
                if owner != email:
                    pending.add(code)
    with closing(company_service._db()) as db, db:
        for code, name, regime, _ in eligible:
            if code not in existing and code not in pending:
                db.execute(
                    "INSERT INTO custom_companies(codigo,nome,regime) VALUES(?,?,?) "
                    "ON CONFLICT(codigo) DO NOTHING",
                    (code, name, regime),
                )
    persisted = {int(row["codigo"]): row["nome"] for row in company_service.catalog()}
    assignments = company_access.owners()
    for code, name, _, email in eligible:
        if persisted.get(code) != name or assignments.get(code) != email:
            pending.add(code)
    saved = len(roster) - len(pending)
    logger.info("Importação de carteiras concluída. Verificadas: %s. Pendentes: %s.", saved, sorted(pending))

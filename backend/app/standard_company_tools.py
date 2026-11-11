"""Standard processing for the companies currently assigned to Brenda."""
import re
from contextlib import closing

from app import company_access
from app.registry import CAPABILITIES

STANDARD_OWNER = "brenda.lima@jaguarcontabil.com.br"
BANKS = ("itau", "bradesco", "banco_brasil", "sicredi", "santander", "caixa", "inter", "safra", "btg", "daycoval", "fibra")
TOOLS = ("modelo_dominio", "conferencia_extrato", "base_inteligente")


def enabled(code, assignments=None):
    if code in CAPABILITIES:
        return False
    assignments = company_access.owners() if assignments is None else assignments
    return assignments.get(code) == STANDARD_OWNER


def _db():
    db = company_access._db()
    db.execute("""CREATE TABLE IF NOT EXISTS standard_bank_accounts (
        company INTEGER NOT NULL, bank TEXT NOT NULL, account TEXT NOT NULL,
        PRIMARY KEY (company, bank)
    )""")
    return db


def accounts(code):
    with closing(_db()) as db:
        return dict(db.execute("SELECT bank,account FROM standard_bank_accounts WHERE company=?", (code,)))


def configured_accounts_by_company():
    result = {}
    with closing(_db()) as db:
        for code, bank, account in db.execute("SELECT company,bank,account FROM standard_bank_accounts"):
            result.setdefault(code, {})[bank] = account
    return result


def add_account(code, bank, account):
    if bank not in BANKS or not re.fullmatch(r"[1-9][0-9]{0,14}", account):
        raise ValueError("Selecione o banco e informe um código contábil válido.")
    with closing(_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        owners = dict(db.execute("SELECT company,email FROM company_owners WHERE company=?", (code,)))
        if not enabled(code, owners) or db.execute("SELECT 1 FROM archived_companies WHERE company=?", (code,)).fetchone():
            raise ValueError("Configuração indisponível para esta empresa.")
        existing = dict(db.execute("SELECT bank,account FROM standard_bank_accounts WHERE company=?", (code,)))
        if bank in existing and existing[bank] != account:
            raise ValueError("Este banco já tem uma conta cadastrada.")
        if any(key != bank and value == account for key, value in existing.items()):
            raise ValueError("Esta conta contábil já está vinculada a outro banco.")
        db.execute("INSERT INTO standard_bank_accounts VALUES(?,?,?) ON CONFLICT DO NOTHING", (code, bank, account))
        return {**existing, bank: account}


def capabilities(code, assignments=None, configured=None):
    if not enabled(code, assignments):
        return None
    return {"status": "api_ready", "workflow": "standard_multi_bank", "standard_tools": True,
            "tools": list(TOOLS), "banks": dict.fromkeys(BANKS, ""), "base_accounts": accounts(code) if configured is None else configured}


def read_statement(bank, content, filename):
    from app import engine
    from app.global_tools import _prefixar, processar_arquivo
    from app.migration_services import COLUNAS
    import pandas as pd

    if filename.lower().endswith(".pdf"):
        with engine.processing_context():
            rows = engine.processar_extrato_conferencia_empresa(content, filename, bank)
        frame = pd.DataFrame(rows, columns=COLUNAS)
    else:
        frame = processar_arquivo(content, filename)
    detected = {engine.identificar_chave_banco_empresa(value) for value in frame["DESCRIÇÃO"]}
    detected.discard("")
    if detected - {bank}:
        raise ValueError("O banco identificado no arquivo não corresponde ao selecionado.")
    frame = _prefixar(frame)
    if frame.empty:
        raise ValueError("Nenhum lançamento reconhecido para o banco selecionado.")
    frame["DESCRIÇÃO"] = engine.nome_banco_por_chave(bank)
    return frame

"""Persistent company catalog; registration never enables processors."""
import sqlite3
from contextlib import closing
from app import classification_service, persistence
from razync.company_catalog import EMPRESAS

def _db():
    path = classification_service.DB_PATH
    con = persistence.connect(path)
    if persistence.is_postgres(con):return con
    con.execute('CREATE TABLE IF NOT EXISTS custom_companies (codigo INTEGER PRIMARY KEY, nome TEXT NOT NULL, regime TEXT NOT NULL)')
    return con

def catalog():
    with closing(_db()) as con, con:
        custom = [dict(row) for row in con.execute('SELECT codigo,nome,regime FROM custom_companies ORDER BY codigo')]
    original_codes = {int(row['codigo']) for row in EMPRESAS}
    return [dict(row) for row in EMPRESAS] + [row for row in custom if row['codigo'] not in original_codes]

def create(code, name='', regime='Não informado'):
    if isinstance(code, bool) or not str(code).isdigit() or not 1 <= int(code) <= 999999999:
        raise ValueError('Informe um código inteiro positivo de até 9 dígitos.')
    code = int(code)
    name = str(name or '').strip() or f'Empresa {code}'
    regime = str(regime or '').strip() or 'Não informado'
    if len(name) > 160 or regime not in {'Não informado','LUCRO REAL','LUCRO PRESUMIDO','SIMPLES NACIONAL'}:
        raise ValueError('Nome ou regime inválido.')
    if any(int(row['codigo']) == code for row in EMPRESAS):
        raise FileExistsError('Já existe uma empresa com esse código.')
    with closing(_db()) as con, con:
        try:
            con.execute('INSERT INTO custom_companies(codigo,nome,regime) VALUES(?,?,?)',(code,name,regime))
        except persistence.INTEGRITY_ERRORS as exc:
            raise FileExistsError('Já existe uma empresa com esse código.') from exc
    return {'codigo':code,'nome':name,'regime':regime}

"""Migração atômica no volume do Railway: python -m app.migrate_to_supabase.

Nunca imprime registros ou credenciais. Mantém SQLite + backup local completo.
"""
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from app import persistence

SQLITE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS classification_records(company INTEGER NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(company,id));
CREATE TABLE IF NOT EXISTS classification_imports(company INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(company,digest));
CREATE TABLE IF NOT EXISTS patterns(company INTEGER NOT NULL,bank TEXT NOT NULL,signature TEXT NOT NULL,nature TEXT NOT NULL,counterpart TEXT NOT NULL,period TEXT NOT NULL,example TEXT,occurrences INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(company,bank,signature,nature,counterpart,period));
CREATE TABLE IF NOT EXISTS manual_tasks(id TEXT PRIMARY KEY,titulo TEXT NOT NULL,descricao TEXT,codigo_empresa TEXT,categoria TEXT,prioridade TEXT,prazo TEXT,status TEXT NOT NULL DEFAULT 'Pendente',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS company_task_status(codigo_empresa TEXT NOT NULL,competencia TEXT NOT NULL,concluida INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(codigo_empresa,competencia));
CREATE TABLE IF NOT EXISTS custom_companies(codigo INTEGER PRIMARY KEY,nome TEXT NOT NULL,regime TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS razync_migration_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),migration_id TEXT NOT NULL,active INTEGER NOT NULL);
'''


def fingerprint(rows):
    canonical={table:sorted((dict(row) for row in data),key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False)) for table,data in rows.items()}
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def migrate(path=None):
    path=Path(path or os.getenv('RAZYNC_DB_PATH','/data/razync.db'))
    if not path.exists():raise RuntimeError('A base SQLite de origem não existe. Migração interrompida.')
    if persistence.marker(path):return {'status':'already_active'}
    source=sqlite3.connect(path,timeout=30);source.row_factory=sqlite3.Row
    target=None
    try:
        source.executescript(SQLITE_SCHEMA)
        source.execute('BEGIN IMMEDIATE')
        # Outra inicialização pode ter concluído enquanto aguardávamos o bloqueio.
        active=source.execute('SELECT migration_id FROM razync_migration_state WHERE active=1').fetchone()
        if active:return {'status':'already_active'}
        migration_id=str(uuid.uuid4())
        backup=path.with_name(path.stem+'.pre-supabase-'+migration_id+'.sqlite3')
        fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        reader=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
        output=sqlite3.connect(backup)
        try:reader.backup(output)
        finally:output.close();reader.close()
        data={table:[dict(row) for row in source.execute('SELECT * FROM '+table)] for table in persistence.TABLES}
        digest=fingerprint(data)
        target=persistence.PostgresConnection()
        target.execute('BEGIN IMMEDIATE')
        existing=target.execute('SELECT migration_id,fingerprint FROM migration_state WHERE singleton=1').fetchone()
        if existing:
            if existing['fingerprint']!=digest:raise RuntimeError('O destino já contém uma migração diferente. Nenhum dado foi substituído.')
            migration_id=existing['migration_id']
        else:
            for table in persistence.TABLES:
                if target.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone():
                    raise RuntimeError('O destino precisa estar vazio antes da primeira migração.')
                if data[table]:
                    columns=','.join(data[table][0])
                    params=','.join('%s' for _ in data[table][0])
                    with target.raw.cursor() as cursor:
                        cursor.executemany(f'INSERT INTO {table}({columns}) VALUES({params})',
                                           (tuple(row.values()) for row in data[table]))
            target.execute('INSERT INTO migration_state VALUES(1,?,?,?)',(migration_id,digest,datetime.now(timezone.utc).isoformat()))
        copied={table:target.execute('SELECT * FROM '+table).fetchall() for table in persistence.TABLES}
        if fingerprint(copied)!=digest:raise RuntimeError('A conferência dos dados falhou. A base de origem permanece ativa.')
        # Depois do commit no destino, o marcador local ativa a nova conexão.
        target.commit()
        source.execute('INSERT INTO razync_migration_state VALUES(1,?,1)',(migration_id,))
        # Protege também conexões antigas que estavam abertas antes da ativação.
        for table in persistence.TABLES:
            for operation in ('INSERT','UPDATE','DELETE'):
                source.execute(f'''CREATE TRIGGER IF NOT EXISTS migrated_{table}_{operation.lower()}
                    BEFORE {operation} ON {table}
                    WHEN EXISTS(SELECT 1 FROM razync_migration_state WHERE active=1)
                    BEGIN SELECT RAISE(ABORT,'Base migrada para o Supabase; escrita local bloqueada.'); END''')
        source.commit()
        return {'status':'activated','counts':{table:len(rows) for table,rows in data.items()},'fingerprint':digest,'backup':backup.name}
    finally:
        source.close()
        if target:target.close()


if __name__=='__main__':
    try:print(json.dumps(migrate(),ensure_ascii=False))
    except Exception as exc:
        # Detalhes de conexão podem conter credenciais; não são enviados ao log.
        print('Migração não concluída. A origem foi preservada. Verifique a conexão, o esquema e o estado do destino.')
        raise SystemExit(1) from None

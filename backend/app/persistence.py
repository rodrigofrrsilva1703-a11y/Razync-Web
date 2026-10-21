"""Persistência selecionada apenas após uma migração verificada.

SQLite permanece a origem e o backup. Não há fallback silencioso: depois da
ativação, uma indisponibilidade do Postgres nunca cria uma segunda base local.
"""
import os
import re
import sqlite3
import threading
from pathlib import Path
from psycopg import IntegrityError
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

INTEGRITY_ERRORS = (sqlite3.IntegrityError, IntegrityError)
TABLES = ('classification_records','classification_imports','patterns',
          'manual_tasks','company_task_status','custom_companies')
_pool = None
_pool_url = None
_pool_lock = threading.Lock()
WRITE_LOCK = 527290203


def marker(path):
    path=Path(path)
    if not path.exists():return None
    con=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='razync_migration_state'").fetchone():return None
        row=con.execute("SELECT migration_id FROM razync_migration_state WHERE active=1").fetchone()
        return row[0] if row else None
    finally:con.close()


def _configure(con):
    con.execute('SET search_path TO razync')
    con.execute("SET statement_timeout TO '30s'")
    con.commit()


def pool():
    global _pool, _pool_url
    url=os.getenv('RAZYNC_DATABASE_URL','')
    if not url:raise RuntimeError('Configure a conexão privada do Supabase no servidor.')
    with _pool_lock:
        if _pool is None or _pool_url != url:
            if _pool is not None:_pool.close()
            _pool=ConnectionPool(url,min_size=0,max_size=3,timeout=15,
                kwargs={'row_factory':dict_row,'prepare_threshold':None,'connect_timeout':10,'sslmode':'require'},
                configure=_configure)
            _pool_url=url
    return _pool


class PostgresConnection:
    def __init__(self):
        self.pool=pool()
        try:self.raw=self.pool.getconn()
        except Exception:raise RuntimeError('Não foi possível conectar à base do Supabase. A base local foi preservada.') from None
        self.closed=False
    def execute(self, query, params=()):
        if query.strip().upper()=='BEGIN IMMEDIATE':
            self.raw.execute('BEGIN')
            return self.raw.execute('SELECT pg_advisory_xact_lock(%s)',(WRITE_LOCK,))
        if query.strip().upper()=='BEGIN':query='BEGIN ISOLATION LEVEL REPEATABLE READ'
        if isinstance(params,dict):query=re.sub(r':([a-zA-Z_]\w*)',r'%(\1)s',query)
        else:query=query.replace('?', '%s')
        return self.raw.execute(query,params)
    def commit(self):self.raw.commit()
    def rollback(self):self.raw.rollback()
    def close(self):
        if not self.closed:
            try:self.raw.rollback()
            finally:self.pool.putconn(self.raw);self.closed=True
    def __enter__(self):return self
    def __exit__(self,typ,value,tb):
        if typ:self.rollback()
        else:self.commit()


def is_postgres(con):return isinstance(con,PostgresConnection)


def table_exists(con,name):
    if name not in (*TABLES,'certificates'):raise ValueError('Tabela desconhecida.')
    if is_postgres(con):
        return con.execute('SELECT 1 FROM information_schema.tables WHERE table_schema=? AND table_name=?',('razync',name)).fetchone() is not None
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


def connect(path):
    active=marker(path)
    if os.getenv('RAZYNC_DATA_BACKEND','sqlite') not in ('sqlite','postgres'):
        raise RuntimeError('Modo de persistência inválido.')
    if active:
        con=PostgresConnection()
        try:
            row=con.execute('SELECT migration_id FROM migration_state WHERE singleton=1').fetchone()
            if not row or row['migration_id']!=active:raise RuntimeError('A migração do banco de dados não foi validada.')
            con.commit()
            return con
        except Exception:
            con.close();raise
    if os.getenv('RAZYNC_DATA_BACKEND')=='postgres':
        raise RuntimeError('Migre e valide a base atual antes de ativar o Supabase.')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=30);con.row_factory=sqlite3.Row
    return con

"""Integração real com Postgres; CI fornece um servidor isolado e descartável."""
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest

URL=os.getenv('RAZYNC_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requer PostgreSQL de integração isolado.')


@pytest.fixture
def postgres(monkeypatch):
    import psycopg
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
    from app import persistence, classification_service as base
    schema=(Path(__file__).resolve().parents[1]/'resources/razync_schema.sql').read_text()
    with psycopg.connect(URL,autocommit=True) as admin:
        for role in ('anon','authenticated'):
            if not admin.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():admin.execute('CREATE ROLE '+role+' NOLOGIN')
        admin.execute(schema)
        admin.execute('TRUNCATE '+','.join('razync.'+table for table in (*persistence.TABLES,'migration_state')))
    def configure(con):
        con.execute('SET ROLE razync_api');persistence._configure(con)
    test_pool=ConnectionPool(URL,min_size=0,max_size=3,timeout=10,open=True,kwargs={'row_factory':dict_row,'prepare_threshold':None},configure=configure)
    monkeypatch.setenv('RAZYNC_DATABASE_URL',URL)
    monkeypatch.setattr(persistence,'_pool',test_pool);monkeypatch.setattr(persistence,'_pool_url',URL)
    yield base.DB_PATH
    test_pool.close()


def seed():
    from app import classification_service as base, tasks, company_service as companies
    payload=json.dumps({'company':3,'records':[{'banco':'itau','assinatura':'acme','debito':'166','credito':'508','periodos':['2026-07','2026-08','2026-09']}]}).encode()
    base.learn(3,payload,'base.json')
    task=tasks.create_task({'titulo':'Conferir razão','descricao':'João & Maria'})
    tasks.set_company_status('3','2026-10-01',True)
    companies.create(909091,'Empresa de teste','SIMPLES NACIONAL')
    return payload,task


def test_copy_verify_activate_and_keep_sqlite_backup(postgres):
    from app import classification_service as base, tasks, company_service as companies
    from app.migrate_to_supabase import migrate
    payload,task=seed();before=base.records(3)
    result=migrate();assert result['status']=='activated'
    assert (postgres.parent/result['backup']).exists()
    assert base.records(3)==before
    tasks.update_task(task['id'],'Concluída')
    assert next(t for t in tasks._manual_rows() if t['id']==task['id'])['status']=='Concluída'
    assert tasks._statuses('2026-10-01')['3']['concluida']
    assert any(c['codigo']==909091 for c in companies.catalog())
    with pytest.raises(FileExistsError):companies.create(909091)
    with sqlite3.connect(postgres) as old:
        assert old.execute('SELECT status FROM manual_tasks WHERE id=?',(task['id'],)).fetchone()[0]=='Pendente'
        with pytest.raises(sqlite3.IntegrityError):old.execute('DELETE FROM classification_records')
    assert migrate()['status']=='already_active'


def test_classification_cleanup_and_concurrent_deduplication(postgres):
    from app import classification_service as base, base_maintenance, tasks
    from app.migrate_to_supabase import migrate
    seed();migrate()
    preview=base_maintenance.preview(3,'itau','2026-08')
    base_maintenance.delete(3,'itau','2026-08',preview['token'])
    assert base.records(3)[0]['periodos']==['2026-07','2026-09']
    payload=json.dumps({'company':3,'records':[{'banco':'itau','assinatura':'new','debito':'200','credito':'508','periodos':['2026-10']}]}).encode()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda _:base.learn(3,payload,'new.json'),range(4)))
    assert sorted(results)==[0,0,0,1]
    tasks.import_company_statuses([{'codigo_empresa':'3','competencia':'2026-11-01','concluida':True,'atualizado_em':'2026-11-02T12:00:00Z'}])
    assert tasks._statuses('2026-11-01')['3']['concluida']
    with pytest.raises(ValueError):base.learn(3,b'{}','invalid.json')
    assert len(base.records(3))==2


def test_nonempty_destination_does_not_replace_source(postgres):
    from app import persistence, classification_service as base
    from app.migrate_to_supabase import migrate
    seed()
    target=persistence.PostgresConnection()
    target.execute('INSERT INTO custom_companies VALUES(?,?,?)',(123456,'Existing','Não informado'));target.commit();target.close()
    with pytest.raises(RuntimeError,match='vazio'):migrate()
    assert persistence.marker(postgres) is None
    assert base.records(3)[0]['periodos']==['2026-07','2026-08','2026-09']


def test_force_postgres_requires_validated_source_marker(postgres,monkeypatch):
    from app import persistence
    seed();monkeypatch.setenv('RAZYNC_DATA_BACKEND','postgres')
    with pytest.raises(RuntimeError,match='valide'):persistence.connect(postgres)


def test_unavailable_destination_never_falls_back_to_local_data(postgres,monkeypatch):
    from app import classification_service as base,persistence
    from app.migrate_to_supabase import migrate
    seed();migrate()
    class Unavailable:
        def getconn(self):raise OSError('unavailable')
    monkeypatch.setattr(persistence,'pool',lambda:Unavailable())
    with pytest.raises(RuntimeError,match='conectar'):base.records(3)

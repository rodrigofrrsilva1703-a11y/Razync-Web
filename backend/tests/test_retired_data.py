import sqlite3

from fastapi.testclient import TestClient
from app.main import app
from app.retired_data import remove_retired_credentials


def test_cleanup_preserves_business_data_and_erases_pre_migration_copies(tmp_path):
    path = tmp_path / 'razync.db'
    backup = tmp_path / 'razync.pre-supabase-test.sqlite3'
    unrelated = tmp_path / 'other.sqlite3'
    for item in (path, backup, unrelated):
        with sqlite3.connect(item) as con:
            con.execute('CREATE TABLE certificates(company INTEGER, metadata TEXT, encrypted TEXT)')
            con.execute('INSERT INTO certificates VALUES(3, ?, ?)', ('retired-metadata', 'retired-secret-payload'))
            con.execute('CREATE TABLE classification_records(id TEXT)')
            con.execute("INSERT INTO classification_records VALUES('keep-business-data')")
            con.execute('CREATE TABLE razync_migration_state(active INTEGER)')
            con.execute('INSERT INTO razync_migration_state VALUES(1)')
    assert remove_retired_credentials(path) == {'databases': 2, 'records': 2}
    for item in (path, backup):
        with sqlite3.connect(item) as con:
            assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='certificates'").fetchone()
            assert con.execute('SELECT * FROM classification_records').fetchall() == [('keep-business-data',)]
            assert con.execute('SELECT * FROM razync_migration_state').fetchall() == [(1,)]
            assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert b'retired-secret-payload' not in item.read_bytes()
    assert remove_retired_credentials(path) == {'databases': 0, 'records': 0}
    with sqlite3.connect(unrelated) as con:
        assert con.execute('SELECT COUNT(*) FROM certificates').fetchone()[0] == 1


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / 'missing.db'
    assert remove_retired_credentials(path) == {'databases': 0, 'records': 0}
    assert not path.exists()


def test_retired_routes_are_not_exposed():
    client = TestClient(app)
    for method in ('get', 'post', 'delete'):
        assert getattr(client, method)('/api/v1/certificates/242').status_code == 404
    assert client.get('/api/v1/connector/download').status_code == 404
    assert 'certificates_configured' not in client.get('/api/v1/migration-status').json()
    paths = client.get('/openapi.json').json()['paths']
    assert not any('certificates' in path or 'connector' in path for path in paths)

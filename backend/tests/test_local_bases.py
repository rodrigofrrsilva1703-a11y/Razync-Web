import importlib.util
import io
import json
from pathlib import Path
import re
import sqlite3
import urllib.error

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app import classification_service as base

spec = importlib.util.spec_from_file_location('local_bases', Path(__file__).parents[2] / 'scripts/local_bases.py')
local_bases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local_bases)


def test_copia_bases_persiste_e_guarda_backup(tmp_path, monkeypatch):
    record = {'banco': 'bb', 'assinatura': 'TESTE FICTICIO', 'debito': '166',
              'credito': '8', 'periodos': ['2026-08'], 'ocorrencias': 1}
    base.status(242)
    class Response(io.BytesIO):
        pass
    def remote(request, timeout):
        assert request.full_url.startswith(local_bases.SOURCE + '/')
        assert request.get_header('Authorization') == 'Bearer chave-ficticia'
        code = int(request.full_url.split('/')[-2])
        return Response(json.dumps({'company': code, 'records': [record] if code == 242 else []}).encode())
    monkeypatch.setattr(local_bases.urllib.request, 'urlopen', remote)
    assert local_bases.copy_bases(tmp_path, 'chave-ficticia') == (1, 1)
    assert base.status(242)['patterns'] == 1
    backup = list((tmp_path / 'backups').glob('*/antes-importacao.db'))
    assert len(backup) == 1
    with sqlite3.connect(backup[0]) as connection:
        assert connection.execute('SELECT count(*) FROM classification_records').fetchone()[0] == 0
    assert 'chave-ficticia' not in ''.join(p.read_text() for p in (tmp_path / 'backups').glob('*/base-*.json'))


def test_erro_autenticacao_nao_grava_base(tmp_path, monkeypatch):
    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, 'não autorizado', {}, None)
    monkeypatch.setattr(local_bases.urllib.request, 'urlopen', fail)
    with pytest.raises(ValueError):
        local_bases.copy_bases(tmp_path, 'chave-ficticia')
    assert not (tmp_path / 'backups').exists()


def test_transferencia_recusa_origem_externa_e_host_estranho(tmp_path, monkeypatch):
    app = FastAPI()
    local_bases.register(app, tmp_path)
    client = TestClient(app, base_url='http://127.0.0.1:8000')
    page = client.get('/local/bases')
    assert page.status_code == 200
    token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    assert client.get('/local/bases', headers={'Host': 'externo.example'}).status_code == 403
    assert client.post('/local/bases', data={'csrf': token, 'chave': 'ficticia'}, headers={'Origin': 'https://externo.example'}).status_code == 403
    assert client.post('/local/bases', data={'csrf': 'incorreto', 'chave': 'ficticia'}, headers={'Origin': 'http://127.0.0.1:8000'}).status_code == 403
    monkeypatch.setattr(local_bases, 'copy_bases', lambda private, key: (2, 30))
    response = client.post('/local/bases', data={'csrf': token, 'chave': 'ficticia'}, headers={'Origin': 'http://127.0.0.1:8000'})
    assert response.status_code == 200
    assert '30 padrões copiados em 2 empresas' in response.text
    assert 'ficticia' not in response.text

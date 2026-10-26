import io
import threading
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import organizer_jobs as jobs


def workbook():
    stream = io.BytesIO()
    pd.DataFrame([{'DATA':'01/03/2026','VALOR':100,'HISTÓRICO':'FICTICIO'}]).to_excel(stream,index=False)
    return stream.getvalue(), 'teste.xlsx'


def poll(client, token):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = client.get('/api/v1/organizador/'+token).json()
        if state['state'] not in {'queued','processing'}:
            return state
        time.sleep(.01)
    pytest.fail('Job não terminou')


def test_lote_retorna_antes_de_terminar_e_reutiliza_resultado(monkeypatch):
    import app.main as main
    started, release = threading.Event(), threading.Event()
    calls = []
    def work(code, roles, options):
        calls.append((code, roles))
        started.set()
        assert release.wait(5)
        jobs.progress(2,2)
        return workbook()
    monkeypatch.setattr(main,'migrated_workflow',work)
    with TestClient(app) as client:
        try:
            response=client.post('/api/v1/workflow/1529',headers={'X-Razync-Background':'1'},
                data={'roles_json':'["itau","banco_brasil"]'}, files=[('files',('a.pdf',b'a')),('files',('b.pdf',b'b'))])
            assert response.status_code==202
            token=response.json()['job_token']
            assert started.wait(2)
            assert client.get('/health').status_code==200
            assert client.get('/api/v1/organizador/'+token).json()['state']=='processing'
        finally:
            release.set()
        assert poll(client,token)['state']=='ready'
        result=client.get('/api/v1/organizador/'+token+'/resultado')
        assert result.status_code==200
        data=result.json()
        assert data['preview']['sheets'][0]['count']==1
        assert client.get('/api/v1/resultados/'+data['report_token']).content.startswith(b'PK')
        assert client.get('/api/v1/organizador/'+token+'/resultado').json()==data
        assert len(calls)==1


def test_erro_e_cancelamento_nao_publicam_arquivo_parcial():
    client=TestClient(app)
    def invalid():
        raise ValueError('PDF inválido')
    token=__import__('json').loads(jobs.submit(invalid,1,1).body)['job_token']
    assert poll(client,token)=={'state':'error','current':0,'total':1,'error':'PDF inválido'}
    assert client.get('/api/v1/organizador/'+token+'/resultado').status_code==409
    started, release = threading.Event(), threading.Event()
    def work():
        started.set()
        assert release.wait(5)
        jobs.progress()
        return workbook()
    token=__import__('json').loads(jobs.submit(work,1,1).body)['job_token']
    try:
        assert started.wait(2)
        assert client.delete('/api/v1/organizador/'+token).status_code==200
    finally:
        release.set()
    assert poll(client,token)['state']=='cancelled'
    assert client.get('/api/v1/organizador/'+token+'/resultado').status_code==409
    assert client.get('/api/v1/organizador/token-inexistente').status_code==404


def test_fila_tem_limite_e_erro_de_capacidade_preserva_status_429(monkeypatch):
    monkeypatch.setattr(jobs,'MAX_PENDING',0)
    response=TestClient(app).post('/api/v1/workflow/1529',headers={'X-Razync-Background':'1'},
        data={'roles_json':'["banco_brasil"]'}, files=[('files',('a.pdf',b'a'))])
    assert response.status_code==429

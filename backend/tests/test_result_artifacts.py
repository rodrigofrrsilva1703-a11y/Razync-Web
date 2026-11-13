import io
from collections import OrderedDict
import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app import result_artifacts as cache
from app.migration_routes import workbook_preview
from app.report_helpers import _excel_report
from test_migration import workbook_signature

@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(cache, '_items', OrderedDict())
    monkeypatch.setattr(cache, '_bytes', 0)


def test_tokens_isolate_outputs_and_expire(monkeypatch):
    now=[100.0]
    monkeypatch.setattr(cache.time,'monotonic',lambda:now[0])
    one=cache.store(b'one','one.xlsx');two=cache.store(b'two','two.xlsx')
    assert one != two
    assert cache.retrieve(one)==(b'one','one.xlsx')
    assert cache.retrieve(two)==(b'two','two.xlsx')
    now[0]+=cache.TTL_SECONDS+1
    with pytest.raises(HTTPException) as error:cache.retrieve(one)
    assert error.value.status_code==404
    assert cache._bytes==0


def test_cache_budget_never_restricts_binary_report(monkeypatch):
    monkeypatch.setattr(cache,'MAX_BYTES',3)
    assert cache.store(b'large output','report.xlsx') is None
    response=cache.workbook_response(b'large output','report.xlsx',True)
    assert response.media_type=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert cache._bytes==0
    first=cache.store(b'ab','first');second=cache.store(b'cd','second')
    with pytest.raises(HTTPException):cache.retrieve(first)
    assert cache.retrieve(second)==(b'cd','second')
    assert cache._bytes==2


def test_inline_preview_keeps_exact_workbook_and_totals():
    book=_excel_report({'Banco':pd.DataFrame({'DATA':['01/07/2026']*1001,'VALOR':[10]*1000+[-5],'HISTÓRICO':['Teste']*1001})})
    response=cache.workbook_response(book,'modelo.xlsx',True)
    import json
    result=json.loads(response.body)
    assert result['preview']['sheets']==workbook_preview(book)
    sheet=result['preview']['sheets'][0]
    assert sheet['count']==1001 and len(sheet['rows'])==500
    assert sheet['entradas']==10000 and sheet['saidas']==5
    assert cache.retrieve(result['report_token'])==(book,'modelo.xlsx')


def test_reconciliation_download_reuses_snapshot_without_processing_again(monkeypatch):
    import app.migration_services as services
    calls=[]
    def reconcile(company,bank,model,files,options):
        calls.append((company,bank,model,files,options))
        daily=pd.DataFrame([{'DATA':pd.Timestamp('2026-07-01'),'ENTRADAS PLANILHA':100,'ENTRADAS EXTRATO':100,'SAÍDAS PLANILHA':0,'SAÍDAS EXTRATO':0}])
        return {'ok':True},{'Conferência diária':daily}
    monkeypatch.setattr(services,'reconcile',reconcile)
    client=TestClient(app)
    files={'model_file':('modelo.xlsx',b'model'),'statement_files':('extrato.pdf',b'pdf')}
    preview=client.post('/api/v1/conferencia-extrato/242/preview',data={'bank':'itau_508'},files=files,headers={'X-Razync-Reuse':'1'})
    assert preview.status_code==200,preview.text
    download=client.get('/api/v1/resultados/'+preview.json()['report_token'])
    assert download.status_code==200 and len(calls)==1
    assert download.headers['cache-control']=='private, no-store'
    original=client.post('/api/v1/conferencia-extrato/242',data={'bank':'itau_508'},files=files)
    assert workbook_signature(download.content)==workbook_signature(original.content)


def test_fiscal_cached_export_matches_original():
    from test_multiple_attachments import fiscal,ledger
    files={'acumuladores':('resumo.xlsx',fiscal(7)),'razao':('razao.xlsx',ledger([7]))}
    client=TestClient(app)
    preview=client.post('/api/v1/conferencia-fiscal/preview',files=files,headers={'X-Razync-Reuse':'1'})
    assert preview.status_code==200,preview.text
    download=client.get('/api/v1/resultados/'+preview.json()['report_token'])
    original=client.post('/api/v1/conferencia-fiscal/exportar',files=files)
    assert original.status_code==200,original.text
    assert workbook_signature(download.content)==workbook_signature(original.content)

def test_report_helpers_keep_values_and_do_not_copy_or_mutate_frames():
    from app.report_helpers import _preview_records
    frame=pd.DataFrame({'DATA':[pd.Timestamp('2026-07-01'),pd.NaT], 'VALOR':[10.125,float('nan')], 'CONTA':[508,12]})
    before=frame.copy(deep=True)
    rows=_preview_records(frame)
    assert rows==[{'DATA':'2026-07-01','VALOR':10.12,'CONTA':508},{'DATA':None,'VALOR':None,'CONTA':12}]
    _excel_report({'Teste':frame})
    pd.testing.assert_frame_equal(frame,before)

def test_optional_export_failure_keeps_reconciliation_preview(monkeypatch):
    def fail(_):raise ValueError('test export failure')
    monkeypatch.setattr(cache,'_excel_report',fail)
    result=cache.reconciliation_response({'ok':True},[{'DATA':'2026-07-01'}],{},'test.xlsx',True)
    assert result=={'summary':{'ok':True},'rows':[{'DATA':'2026-07-01'}]}

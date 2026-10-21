import json
import pytest
from fastapi.testclient import TestClient
from app import classification_service as base, base_maintenance as maintenance
from app.main import app


def seed(company=3, bank='itau', periods=None):
    con=base._db()
    try:
        base._save(con,company,[{'banco':bank,'assinatura':'acme','debito':'166','credito':'508','periodos':periods or ['2026-07','2026-08','2026-09'],'ocorrencias':3}])
        con.commit()
    finally:con.close()


def test_remove_only_one_bank_month_and_preserve_other_company():
    seed();seed(bank='bradesco');seed(company=178)
    preview=maintenance.preview(3,'itau','2026-08')
    assert (preview['affected'],preview['retained'],preview['removed'])==(1,1,0)
    maintenance.delete(3,'itau','2026-08',preview['token'])
    result={r['banco']:r['periodos'] for r in base.records(3)}
    assert result['itau']==['2026-07','2026-09']
    assert result['bradesco']==['2026-07','2026-08','2026-09']
    assert base.records(178)[0]['periodos']==['2026-07','2026-08','2026-09']


def test_last_period_removes_record_and_reimport_is_allowed():
    payload=json.dumps({'company':3,'records':[{'banco':'itau','assinatura':'acme','debito':'166','credito':'508','periodos':['2026-09']}]}).encode()
    assert base.learn(3,payload,'base.json')==1
    preview=maintenance.preview(3,'itau','2026-09');assert preview['removed']==1
    maintenance.delete(3,'itau','2026-09',preview['token'])
    assert base.records(3)==[]
    assert base.learn(3,payload,'base.json')==1


def test_stale_or_cross_period_confirmation_cannot_delete():
    seed();preview=maintenance.preview(3,'itau','2026-08');seed(periods=['2026-10'])
    with pytest.raises(maintenance.StaleSelection):maintenance.delete(3,'itau','2026-08',preview['token'])
    assert '2026-08' in base.records(3)[0]['periodos']
    with pytest.raises(maintenance.StaleSelection):maintenance.delete(3,'itau','2026-09',preview['token'])
    assert '2026-09' in base.records(3)[0]['periodos']


def test_empty_selection_never_expands_to_all_data():
    seed()
    for bank,period in [('', ''),('itau',''),('', '2026-09'),('itau',"' OR 1=1 --")]:
        with pytest.raises(ValueError):maintenance.preview(3,bank,period)
    assert len(base.records(3))==1


def test_legacy_aliases_removed_without_reappearing(monkeypatch):
    from app import base_inteligente
    monkeypatch.setattr(base_inteligente,'DB_PATH',base.DB_PATH)
    con=base_inteligente._db()
    for period in ['2026-08','2026-09']:
        con.execute('INSERT INTO patterns VALUES(?,?,?,?,?,?,?,?)',(242,'banco_brasil','acme','pago','166',period,'Pago ACME',1))
    con.commit();con.close();seed(company=242,bank='bb',periods=['2026-08'])
    assert maintenance.slices(242)['banks']==[{'bank':'bb','account':'8','periods':['2026-09','2026-08']}]
    preview=maintenance.preview(242,'bb','2026-08');assert preview['affected']==2
    maintenance.delete(242,'bb','2026-08',preview['token'])
    assert all('2026-08' not in record['periodos'] for record in base.records(242))
    assert base.records(242)[0]['periodos']==['2026-09']


def test_routes_require_admin_and_reject_stale_token(monkeypatch):
    monkeypatch.setenv('RAZYNC_ACCESS_TOKEN','test-only-secret');client=TestClient(app);seed()
    root='/api/v1/base-inteligente/3'
    for path in ['/recortes','/exclusao-previa?bank=itau&period=2026-08']:assert client.get(root+path).status_code==401
    assert client.post(root+'/excluir-recorte',json={'bank':'itau','period':'2026-08','token':'wrong'}).status_code==401
    headers={'Authorization':'Bearer test-only-secret'}
    assert client.get(root+'/recortes',headers=headers).status_code==200
    preview=client.get(root+'/exclusao-previa',params={'bank':'itau','period':'2026-08'},headers=headers).json()
    assert client.post(root+'/excluir-recorte',headers=headers,json={'bank':'itau','period':'2026-08','token':'wrong'}).status_code==409
    assert client.post(root+'/excluir-recorte',headers=headers,json={k:preview[k] for k in ['bank','period','token']}).status_code==200
    assert client.get(root+'/exclusao-previa',params={'bank':'itau','period':'2026-08'},headers=headers).status_code==422

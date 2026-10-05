import io,json
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app import engine
from app.migration_services import workflow,diagnostics,statement
from razync.rgr_1248 import processar_rgr
from test_api_equivalence import pdf_text
from test_migration import workbook_signature,reference_engine

def inputs(total=300):
    pdf=pdf_text(f'RGR IMPORTADORA 0021550-8\n01/10/2026 SALDO EM CONTA 1.000,00\n02/10/2026 BOLETOS RECEBIDOS {total},00\n02/10/2026 PAGAMENTO -50,00')
    output=io.BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        pd.DataFrame([['PAGADOR','PAGAMENTO','VALOR','NF'],['CLIENTE A','02/10/2026',100,'1'],['CLIENTE B','02/10/2026',200,'2']]).to_excel(writer,sheet_name='ENTRADAS',header=False,index=False)
        pd.DataFrame([['Data','Razão Social','Valor'],['02/10/2026','FORNECEDOR TESTE',-50]]).to_excel(writer,sheet_name='SAIDAS',header=False,index=False)
    return pdf,output.getvalue()

def test_rgr_breakdown_balance_exclusion_and_original_excel(monkeypatch):
    pdf,sheet=inputs()
    model,diag,unused,expenses,summary=processar_rgr(pdf,sheet)
    assert len(model)==3
    assert model['VALOR'].sum()==250
    assert set(model.loc[model['VALOR']>0,'DÉBITO'])=={'508'}
    assert 'FORNECEDOR TESTE' in model.iloc[-1]['HISTÓRICO']
    assert summary['agregados_batendo']==1
    assert len(statement(1248,'itau',pdf,'extrato.pdf'))==2
    monkeypatch.chdir(engine.TEMPLATE.parent)
    expected=reference_engine().gerar_excel_modelo_dominio(model,formato_data='dd/mm/yyyy')
    actual,name=workflow(1248,{'extrato':[('extrato.pdf',pdf)],'movimentos':[('movimentos.xlsx',sheet)]},{})
    assert workbook_signature(actual)==workbook_signature(expected)
    assert name=='RGR_1248_ITAU_508_MODELO_DOMINIO_02102026_A_02102026.xlsx'
    tables=diagnostics(1248,{'extrato':[('extrato.pdf',pdf)],'movimentos':[('movimentos.xlsx',sheet)]},{})
    pd.testing.assert_frame_equal(tables['Boletos recebidos'],diag)
    response=TestClient(app).post('/api/v1/workflow/1248/preview',data={'roles_json':'["extrato","movimentos"]'},files=[('files',('extrato.pdf',pdf)),('files',('movimentos.xlsx',sheet))])
    assert response.status_code==200,response.text
    assert response.json()['sheets'][0]['count']==3

def test_rgr_divergent_total_remains_original():
    pdf,sheet=inputs(350)
    model,_,_,_,summary=processar_rgr(pdf,sheet)
    assert len(model)==2
    assert model['VALOR'].sum()==300
    assert summary['agregados_divergentes']==1
    actual,_=workflow(1248,{'extrato':[('extrato.pdf',pdf)],'movimentos':[('movimentos.xlsx',sheet)]},{})
    assert workbook_signature(actual)==workbook_signature(engine.gerar_excel_modelo_dominio(model,formato_data='dd/mm/yyyy'))

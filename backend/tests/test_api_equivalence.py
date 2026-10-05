import io
import json
from datetime import date
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.main import app, _original_export
from app import engine
from app.migration_services import workflow, eletro_reports
from test_migration import xlsx, workbook_signature, reference_engine

client = TestClient(app)

@pytest.mark.parametrize('code', [242,1408])
def test_eletro_reports_preserve_individual_original_and_consolidated(code):
    from razync import eletro_forte as ef
    raw = b'<table><tr><th>Data</th><th>Debito</th><th>Credito</th><th>Valor</th><th>Historico</th></tr><tr><td>03/08</td><td>166</td><td>8</td><td>100,50</td><td>CLIENTE TESTE</td></tr></table>'
    roles = {name:[('relatorio.xls',raw)] for name in ('despesas','fornecedores','recebidos')}
    actual = eletro_reports(code,roles,{'ano':2026})
    groups = [f(raw,2026,'512' if code==1408 else None) for f in (ef.processar_despesas,ef.processar_fornecedores,ef.processar_recebidos)]
    expected = ef.gerar_consolidado_bancos_eletro_forte(engine.TEMPLATE.read_bytes(),*groups)
    assert workbook_signature(actual[f'ELETRO_FORTE_{code}_CONSOLIDADO.xlsx']) == workbook_signature(expected)
    for index,name in enumerate(('despesas','fornecedores','recebidos')):
        params=[None,{},{}];params[index]=groups[index]
        expected = ef.gerar_modelo_dominio_eletro_forte(raw,'relatorio.xls',engine.TEMPLATE.read_bytes(),*params)
        assert workbook_signature(actual[f'ELETRO_FORTE_{code}_{name.upper()}.xlsx']) == workbook_signature(expected)
    response = client.post(f'/api/v1/workflow/{code}/reports',data={'roles_json':json.dumps(list(roles)),'options_json':'{"ano":2026}'},files=[('files',('relatorio.xls',raw)) for _ in roles])
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/zip'

@pytest.mark.parametrize('code,accounts',[(266,['99549-5','451990-6','673947-1']),(1396,['98002-6','3084-8'])])
def test_nova_geracao_period_removals_and_workbook_match_original(code,accounts):
    data=xlsx([['Conta','Data','Valor','Lacto','Historico','Doc']]+[[a,'01/10/2026',100,'PAGAR','Fornecedor teste','NF1'] for a in accounts]+[[accounts[0],'02/10/2026',100,'ESTORNO DE BAIXA','Estorno de baixa fornecedor','NF1']])
    ref=reference_engine()
    parsers=[ref.processar_nova_geracao_itau,ref.processar_nova_geracao_bradesco,ref.processar_nova_geracao_fibra] if code==266 else [ref.processar_nova_geracao_filial_itau,ref.processar_nova_geracao_filial_bradesco]
    groups={name:dict(zip(('principal','retirados'),parser(data))) for name,parser in zip(('Itaú','Bradesco','Fibra'),parsers)}
    expected=ref.gerar_excel_nova_geracao(groups,engine.TEMPLATE.read_bytes(),prefixar_historicos=False)
    actual,_=workflow(code,{'consolidada':[('consolidada.xlsx',data)]},{})
    assert workbook_signature(actual)==workbook_signature(expected)

def test_vgv_workflow_needs_only_caixa_and_matches_original(monkeypatch):
    from test_original_vgv_1402 import _caixa_bytes
    from razync.vgv_1402 import ler_caixa_vgv
    data=_caixa_bytes()
    ref=reference_engine();monkeypatch.chdir(engine.TEMPLATE.parent)
    expected=ref.gerar_excel_modelo_dominio(ler_caixa_vgv(data)[['DESCRIÇÃO','DATA','VALOR','DÉBITO','CRÉDITO','HISTÓRICO']])
    actual,_=workflow(1402,{'planilha':[('caixa.xlsx',data)]},{})
    assert workbook_signature(actual)==workbook_signature(expected)

def test_up_pack_sicredi_keeps_original_accounts_and_workbook():
    from razync.up_pack import processar_planilha_up_pack
    data=xlsx([['Data','D/C','Complemento','Conf','Entrada','Saída','Saldo','Conta Vinculada'],['13/07/2026','TRANSFERÊNCIA (E)','TRANSFERENCIA ENTRE CONTAS',None,400,0,410.38,'SANTANDER'],['22/07/2026','PAGTO TITULO','Doc.084574/01 - HOTEL',None,0,238,172.38,None]])
    ref=reference_engine()
    expected=ref.gerar_excel_nova_geracao({'Sicredi':{'principal':processar_planilha_up_pack(data,'sicredi'),'retirados':pd.DataFrame()}},engine.TEMPLATE.read_bytes())
    actual,_=workflow(1096,{'sicredi':[('sig.xlsx',data)]},{})
    assert workbook_signature(actual)==workbook_signature(expected)

def test_preview_runs_same_workflow_and_returns_real_counts():
    from test_original_vgv_1402 import _caixa_bytes
    response=client.post('/api/v1/workflow/1402/preview',data={'roles_json':'["planilha"]'},files={'files':('caixa.xlsx',_caixa_bytes())})
    assert response.status_code==200,response.text
    sheet=response.json()['sheets'][0]
    assert (sheet['count'],sheet['entradas'],sheet['saidas'])==(2,4730,540.33)

def test_tax_endpoint_excel_matches_original_report():
    from razync.conferencia_impostos import processar_conferencia_impostos,gerar_relatorio_impostos
    balance=xlsx([['INSS',100],['IRRF',80]])
    revenue=xlsx([['INSS',100],['IRRF',90]])
    expected=gerar_relatorio_impostos(processar_conferencia_impostos(revenue,'receita.xlsx',balance,'balancete.xlsx'),'242 - Eletro Forte',date(2026,10,1))
    response=client.post('/api/v1/conferencia-impostos/242',data={'competencia':'2026-10'},files={'receita':('receita.xlsx',revenue),'balancete':('balancete.xlsx',balance)})
    assert response.status_code==200,response.text
    summary=json.loads(response.headers['x-razync-summary'])
    assert (summary['impostos'],summary['conferem'],summary['revisar'])==(2,1,1)
    from openpyxl import load_workbook
    actual=load_workbook(io.BytesIO(response.content));original=load_workbook(io.BytesIO(expected))
    # Catalog's full legal name is intentional; all calculation and formatting match.
    original.active['B1']=actual.active['B1'].value
    out=io.BytesIO();original.save(out)
    assert workbook_signature(response.content)==workbook_signature(out.getvalue())

def test_bank_validation_does_not_silently_use_another_processor():
    response=client.post('/api/v1/modelo-dominio/154',data={'bank':'sicredi'},files={'files':('extrato.pdf',b'pdf')})
    assert response.status_code==400

"""PDFs sintéticos: nenhum extrato confidencial é incluído no repositório."""
import io
import json
from decimal import Decimal

import fitz
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from app.registry import CAPABILITIES
from app.migration_services import workflow, statement
from app.santander_consolidado_1522 import read_statement, HOLDER


def sample(*, holder=HOLDER, month='março', closing='0,00', close=True, split=False, april_dates=False):
    doc=fitz.open()
    def page():
        p=doc.new_page(width=595.3,height=841.9)
        p.insert_text((35,35),'Santander Empresas - EXTRATO CONSOLIDADO',fontsize=10)
        p.insert_text((35,55),month+'/2026',fontsize=10)
        p.insert_text((35,80),holder,fontsize=9)
        for x,t in [(34,'Data'),(65,'Descrição'),(293,'Nº Documento'),(380,'Movimentos (R$)'),(508,'Saldo (R$)')]:p.insert_text((x,130),t,fontsize=8)
        p.insert_text((384,145),'Créditos',fontsize=8);p.insert_text((435,145),'Débitos',fontsize=8)
        return p
    def row(p,y,day,text,credit='',debit='',saldo='',docno='-'):
        if april_dates:
            day=day.replace('/03','/04')
            text=text.replace('28/02','31/03').replace('31/03','30/04') if text=='SALDO EM 31/03' else text.replace('28/02','31/03')
        for x,t in [(34,day),(65,text),(315,docno),(380,credit),(428,debit),(530,saldo)]:
            if t:p.insert_text((x,y),t,fontsize=8)
    p=page();row(p,168,'','SALDO EM 28/02',saldo='0,00',docno='')
    row(p,190,'02/03','PIX RECEBIDO',credit='100,00')
    if split:p=page(); y=168
    else:y=205
    row(p,y,'','FORNECEDOR TESTE',docno='')
    row(p,y+20,'','APLICACAO CONTAMAX',debit='100,00-',saldo='0,00')
    row(p,y+40,'19/03','PAGAMENTO CARTAO DE CREDITO',credit='369,60',docno='108694')
    row(p,y+55,'','GETNET-MASTER',docno='')
    row(p,y+75,'','PIX ENVIADO FORNECEDOR',debit='369,60-',saldo='0,00')
    if close:row(p,y+95,'','SALDO EM 31/03',saldo=closing,docno='')
    # A segunda tabela não é nova movimentação da conta corrente.
    p=doc.new_page();p.insert_text((40,50),'Investimentos - ContaMax Empresarial',fontsize=10)
    p.insert_text((40,80),'02/MAR/26 02/MAR/26 260000000 100,00 100,00',fontsize=9)
    result=doc.tobytes();doc.close();return result


def test_capability_1522_santander_pdf_513():
    cap=CAPABILITIES[1522]
    assert cap['banks']=={'santander':'513'}
    assert cap['workflow']=='advanced'
    assert cap['roles']==[{'name':'santander','label':'Extrato Santander consolidado (PDF)','accept':'.pdf','multiple':True}]
    assert CAPABILITIES[1001]['banks']['santander']=='513'


@pytest.mark.parametrize('split',[False,True])
def test_parser_keeps_continuations_sign_by_column_and_ignores_investments(split):
    f=read_statement(sample(split=split))
    assert len(f)==4
    assert f.VALOR.tolist()==[100,-100,369.6,-369.6]
    assert f.DATA.tolist()==['02/03/2026','02/03/2026','19/03/2026','19/03/2026']
    assert f.iloc[0]['HISTÓRICO']=='Recebido: PIX RECEBIDO FORNECEDOR TESTE'
    assert f.iloc[2]['HISTÓRICO']=='Recebido: PAGAMENTO CARTAO DE CREDITO GETNET-MASTER'
    assert f['DÉBITO'].tolist()==['513','','513','']
    assert f['CRÉDITO'].tolist()==['','513','','513']
    assert f.attrs['opening_balance']==f.attrs['closing_balance']==0


@pytest.mark.parametrize('kwargs,message',[({'holder':'OUTRA EMPRESA LTDA'},'titular'),({'closing':'1,00'},'saldo final'),({'close':False},'incompleta'),({'month':'abril'},'datas dos saldos')])
def test_rejects_wrong_company_bad_balance_and_incomplete_or_inconsistent_period(kwargs,message):
    with pytest.raises(ValueError,match=message):read_statement(sample(**kwargs))


def test_invalid_pdf_and_non_pdf_are_rejected():
    for name,content in [('planilha.xlsx',b'abc'),('extrato.pdf',b'%PDF-invalid')]:
        with pytest.raises(ValueError):read_statement(content,name)


def test_workflow_generates_domain_and_filtered_dates():
    content,name=workflow(1522,{'santander':[('marco.pdf',sample())]},{'data_inicial':'2026-03-19','data_final':'2026-03-31'})
    assert name=='PRISCILA_1522_MODELO_DOMINIO.xlsx'
    wb=load_workbook(io.BytesIO(content));assert wb.sheetnames==['Santander']
    rows=list(wb.active.values)
    assert list(rows[0])==['DESCRIÇÃO','DATA','VALOR','DÉBITO','CRÉDITO','HISTÓRICO']
    assert len(rows)==3 and [r[2] for r in rows[1:]]==[369.6,-369.6]
    assert all(r[1].strftime('%d/%m/%Y')=='19/03/2026' for r in rows[1:])
    assert wb.active['B2'].number_format=='dd/mm/yyyy'
    assert sum(Decimal(str(r[2])) for r in rows[1:])==0


def test_duplicate_months_files_and_empty_selection_are_rejected():
    pdf=sample()
    for uploads in [[('a.pdf',pdf),('b.pdf',pdf)],[('a.pdf',pdf),('b.pdf',sample(split=True))]]:
        with pytest.raises(ValueError,match='mais de uma vez|deste mês'):workflow(1522,{'santander':uploads},{})
    with pytest.raises(ValueError,match='Envie'):workflow(1522,{}, {})
    with pytest.raises(ValueError,match='Nenhum movimento'):workflow(1522,{'santander':[('a.pdf',pdf)]},{'data_inicial':'2026-04-01','data_final':'2026-04-30'})


def test_same_reader_is_used_for_statement_and_advanced():
    from app.advanced import workflow_modelo
    pdf=sample()
    assert statement(1522,'santander',pdf,'extrato.pdf').VALOR.tolist()==[100,-100,369.6,-369.6]
    content,name=workflow_modelo(1522,{'santander':[('a.pdf',pdf)]},{})
    assert name=='PRISCILA_1522_MODELO_DOMINIO.xlsx'
    assert load_workbook(io.BytesIO(content)).active.max_row==5


def test_api_enables_1522_and_returns_workbook():
    client=TestClient(app)
    response=client.get('/api/v1/companies/1522')
    assert response.status_code==200
    assert response.json()['capabilities']['banks']=={'santander':'513'}
    response=client.post('/api/v1/workflow/1522',data={'roles_json':json.dumps(['santander']),'options_json':'{}'},files={'files':('extrato.pdf',sample(),'application/pdf')})
    assert response.status_code==200,response.text
    assert load_workbook(io.BytesIO(response.content)).active.max_row==5


def test_multiple_months_are_sorted_and_not_duplicated():
    content,_=workflow(1522,{'santander':[('abril.pdf',sample(month='abril',april_dates=True)),('marco.pdf',sample())]}, {})
    wb=load_workbook(io.BytesIO(content)); rows=list(wb.active.values)[1:]
    assert len(rows)==8
    assert [r[1].month for r in rows]==[3]*4+[4]*4
    assert all(wb.active.cell(i,2).number_format=='dd/mm/yyyy' for i in range(2,10))

from decimal import Decimal
import json
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import bank_investments as investments


def daily(values=(-100,30,0)):
    return pd.DataFrame([{'DATA':f'{i+1:02}/08/2026','ENTRADAS PLANILHA':max(value,0),'SAÍDAS PLANILHA':max(-value,0),
        'ENTRADAS EXTRATO':max(value,0),'SAÍDAS EXTRATO':max(-value,0)} for i,value in enumerate(values)])


def test_resgate_e_aplicacao_zeram_cada_dia_sem_reacumular_saldo():
    entries=investments.daily_entries(daily(),'508','900')
    assert len(entries)==2
    assert entries[0]=={'DATA':'01/08/2026','DÉBITO':'508','CRÉDITO':'900','VALOR':Decimal('100.00'),'HISTÓRICO':investments.REDEMPTION}
    assert entries[1]['DÉBITO']=='900' and entries[1]['CRÉDITO']=='508' and entries[1]['VALOR']==Decimal('30.00')
    assert entries[1]['HISTÓRICO']==investments.INVESTMENT
    for original,entry in zip((-100,30),entries):
        signed=entry['VALOR'] if entry['DÉBITO']=='508' else -entry['VALOR']
        assert Decimal(original)+signed==0


def test_saldo_anterior_entra_somente_no_primeiro_dia_e_datas_sao_ordenadas():
    result=investments.daily_entries(daily((-100,30)).iloc[::-1],'508','900',Decimal('120.00'))
    assert [entry['VALOR'] for entry in result]==[Decimal('20.00'),Decimal('30.00')]
    assert all(entry['HISTÓRICO']==investments.INVESTMENT for entry in result)


@pytest.mark.parametrize('value,expected',[('1.234,56','1234.56'),('-100,25','-100.25'),('0,00','0'),(10,'10')])
def test_saldo_anterior_brasileiro(value,expected):
    assert investments.opening_balance(value)==Decimal(expected)


@pytest.mark.parametrize('mutate',[
    lambda frame:frame.assign(**{'ENTRADAS EXTRATO':999}),
    lambda frame:frame.assign(DATA='invalida'),
    lambda frame:frame.assign(DATA='01/08/2026'),
    lambda frame:frame.assign(**{'ENTRADAS PLANILHA':float('nan')}),
])
def test_recusa_divergencia_ou_dados_invalidos(mutate):
    with pytest.raises(ValueError):investments.daily_entries(mutate(daily()),'508','900')


def test_recusa_conta_igual_e_saldo_ambiguo():
    with pytest.raises(ValueError):investments.daily_entries(daily(),'508','0508')
    with pytest.raises(ValueError):investments.opening_balance('1.23')


def post(settings,banks=('itau',),file_banks=('itau',)):
    return TestClient(app).post('/api/v1/conferencia-extrato/3/aplicacoes-resgates',
        data={'banks_json':json.dumps(banks),'file_banks_json':json.dumps(file_banks),'settings_json':json.dumps(settings)},
        files=[('model_file',('modelo.xlsx',b'test')), *[('files',('extrato.pdf',b'test')) for _ in file_banks]])


def test_txt_formato_dominio_historicos_exatos_e_valores_positivos(monkeypatch):
    calls=[]
    def reconcile(code,bank,model,files,options):
        calls.append((code,bank,model,files));return {'ok':True},{'Conferência diária':daily()}
    monkeypatch.setattr(investments,'reconcile',reconcile)
    response=post({'itau':{'conta_aplicacao':'900','saldo_anterior':'0,00'}})
    assert response.status_code==200,response.text
    assert response.text=='DESCRIÇÃO: APLICAÇÃO E RESGATE;DATA;VALOR;DÉBITO;CRÉDITO;HISTÓRICO\nAPLICAÇÃO E RESGATE;01/08/2026;100.00;508;900;RESGATE APLICAÇÃO FINANCEIRA CF EXTRATO\nAPLICAÇÃO E RESGATE;02/08/2026;30.00;900;508;APLICAÇÃO FINANCEIRA CF EXTRATO\n'
    assert calls[0][0:3]==(3,'itau',b'test')


def test_multibanco_nao_mistura_contas_e_bloqueia_resultado_parcial(monkeypatch):
    monkeypatch.setattr(investments,'reconcile',lambda *args:({'ok':False},{'Conferência diária':daily() if args[1]=='itau' else daily().assign(**{'ENTRADAS EXTRATO':999})}))
    settings={'itau':{'conta_aplicacao':'900'},'daycoval':{'conta_aplicacao':'901'}}
    response=post(settings,('itau','daycoval'),('itau','daycoval'))
    assert response.status_code==422
    monkeypatch.setattr(investments,'reconcile',lambda *args:({'ok':True},{'Conferência diária':daily()}))
    response=post(settings,('itau','daycoval'),('itau','daycoval'))
    assert response.status_code==200
    assert ';2283;901;' in response.text and ';508;900;' in response.text


def test_nao_permite_alterar_conta_banco_cadastrada(monkeypatch):
    monkeypatch.setattr(investments,'reconcile',lambda *a:pytest.fail('Valida contas antes de processar'))
    assert post({'itau':{'conta_aplicacao':'900','conta_banco':'999'}}).status_code==422


def test_dias_zerados_nao_geram_lancamentos_artificiais(monkeypatch):
    monkeypatch.setattr(investments,'reconcile',lambda *args:({'ok':True},{'Conferência diária':daily((0,0))}))
    response=post({'itau':{'conta_aplicacao':'900'}})
    assert response.status_code==422 and 'já estão zerados' in response.text


def test_integracao_le_modelo_e_extrato_reais_sem_substituir_motor():
    import io
    def book(rows):
        output=io.BytesIO();pd.DataFrame(rows).to_excel(output,index=False,header=False);return output.getvalue()
    model=book([['DESCRIÇÃO','DATA','VALOR','DÉBITO','CRÉDITO','HISTÓRICO'],
        ['BANCO ITAÚ','01/08/2026',-100,'','508','Pago: Fornecedor fictício'],
        ['BANCO ITAÚ','02/08/2026',30,'508','','Recebido: Cliente fictício']])
    statement=book([['Data','Histórico','Valor'],['01/08/2026','Fornecedor fictício',-100],['02/08/2026','Cliente fictício',30]])
    response=TestClient(app).post('/api/v1/conferencia-extrato/3/aplicacoes-resgates',
        data={'banks_json':'["itau"]','file_banks_json':'["itau"]','settings_json':'{"itau":{"conta_aplicacao":"900"}}'},
        files=[('model_file',('modelo.xlsx',model)),('files',('itau.xlsx',statement))])
    assert response.status_code==200,response.text
    assert response.text.splitlines()==[
        'DESCRIÇÃO: APLICAÇÃO E RESGATE;DATA;VALOR;DÉBITO;CRÉDITO;HISTÓRICO',
        'APLICAÇÃO E RESGATE;01/08/2026;100.00;508;900;RESGATE APLICAÇÃO FINANCEIRA CF EXTRATO',
        'APLICAÇÃO E RESGATE;02/08/2026;30.00;900;508;APLICAÇÃO FINANCEIRA CF EXTRATO']


def test_previa_e_txt_tem_mesmos_lancamentos_e_saldos_zerados(monkeypatch):
    monkeypatch.setattr(investments,'reconcile',lambda *args:({'ok':True},{'Conferência diária':daily()}))
    client=TestClient(app)
    data={'banks_json':'["itau"]','file_banks_json':'["itau"]','settings_json':'{"itau":{"conta_aplicacao":"900"}}'}
    files=[('model_file',('modelo.xlsx',b'test')),('files',('extrato.pdf',b'test'))]
    preview=client.post('/api/v1/conferencia-extrato/3/aplicacoes-resgates/preview',data=data,files=files)
    txt=client.post('/api/v1/conferencia-extrato/3/aplicacoes-resgates',data=data,files=files)
    assert preview.status_code==txt.status_code==200
    result=preview.json()
    assert result['txt']==txt.text
    assert result['txt'].splitlines()[0]=='DESCRIÇÃO: APLICAÇÃO E RESGATE;DATA;VALOR;DÉBITO;CRÉDITO;HISTÓRICO'
    assert all(row['DESCRIÇÃO']=='APLICAÇÃO E RESGATE' for row in result['rows'])
    assert all(len(line.split(';'))==6 for line in result['txt'].splitlines())
    assert result['summary']=={'lancamentos':2,'resgates':1,'aplicacoes':1,'total_resgates':'100.00','total_aplicacoes':'30.00'}
    assert [row['SALDO_ANTES'] for row in result['rows']]==['-100.00','30.00']
    assert all(row['SALDO_APOS']=='0.00' for row in result['rows'])
    assert {row['BANCO'] for row in result['rows']}=={'itau'}
    assert preview.headers['cache-control']=='no-store'


def test_saldos_diarios_batendo_liberam_txt_sem_exigir_pareamento_individual(monkeypatch):
    monkeypatch.setattr(investments,'reconcile',lambda *args:(
        {'ok':False,'faltando_planilha':2,'a_mais_planilha':1},{'Conferência diária':daily()}))
    response=post({'itau':{'conta_aplicacao':'900'}})
    assert response.status_code==200,response.text
    assert ';100.00;508;900;' in response.text


def test_selecao_de_um_banco_nao_exige_contas_ou_extratos_dos_outros(monkeypatch):
    calls=[]
    def reconcile(code,bank,model,files,options):
        calls.append(bank)
        return {'ok':True},{'Conferência diária':daily()}
    monkeypatch.setattr(investments,'reconcile',reconcile)
    response=post({'daycoval':{'conta_aplicacao':'901'}},('daycoval',),('daycoval',))
    assert response.status_code==200,response.text
    assert calls==['daycoval']
    assert ';2283;901;' in response.text
    assert ';508;' not in response.text

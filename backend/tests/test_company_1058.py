"""Cobertura da empresa 1058 sem anexar dados reais de clientes ao Git."""
from datetime import datetime
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest

from app.company_1058 import read_itau, read_caixa


def synthetic_excel():
    data = [[None] * 6 for _ in range(6)]
    data += [[None, 'DATA', 'TIPO', 'FAVORECIDO', 'VALOR', 'DESCRIÇÃO']]
    data += [[None, 46237, 'Boletos de cobrança', 'FORNECEDOR TESTE', 123.45, 'Serviço']]
    data += [[None, 46238, 'Crédito em conta', 'BENEFICIARIO TESTE', 200.00, 'Transferencia']]
    output=BytesIO()
    pd.DataFrame(data).to_excel(output,index=False,header=False)
    return output.getvalue()


def test_itau_credito_em_conta_e_saida_na_conta_origem():
    frame = read_itau(synthetic_excel())
    assert frame['VALOR'].tolist() == [-123.45,-200.0]
    assert frame['CRÉDITO'].tolist() == ['514','514']
    assert all(value.startswith('Pago: ') for value in frame['HISTÓRICO'])
    assert frame['DATA'].dt.strftime('%d/%m/%Y').tolist() == ['03/08/2026','04/08/2026']


def test_caixa_valida_saldo_e_ignora_saldo_dia():
    from unittest.mock import MagicMock
    text = '''Extrato por período
Cliente: QUARTETO DE OBRAS LTDA
Conta: 4115 | 1292 | 000578789424-0
Mês: Abril/2026
Extrato
Data Mov. Nr. Doc. Histórico Valor Saldo
27/04/2026000000 TAR MAN CC 71,33 D 0,03 D
27/04/2026000000 RESG AUT 0,03 C 0,00 C
27/04/2026000000 SALDO DIA 0,00 C 0,00 C'''
    with patch('app.company_1058.PdfReader') as reader:
        reader.return_value.pages = [MagicMock(extract_text=lambda: text)]
        frame = read_caixa(b'%PDF synthetic')
    assert frame['VALOR'].tolist() == [-71.33,0.03]
    assert frame['CRÉDITO'].tolist() == ['504','']
    assert frame['DÉBITO'].tolist() == ['', '504']


def test_caixa_rejeita_saldo_divergente():
    from unittest.mock import MagicMock
    text = '''Extrato por período
Cliente: QUARTETO DE OBRAS LTDA
Conta: 4115 | 1292 | 000578789424-0
Mês: Abril/2026
Extrato
Data Mov. Nr. Doc. Histórico Valor Saldo
27/04/2026000000 TAR MAN CC 71,33 D 0,03 D
27/04/2026000000 RESG AUT 0,03 C 0,01 C'''
    with patch('app.company_1058.PdfReader') as reader:
        reader.return_value.pages = [MagicMock(extract_text=lambda: text)]
        with pytest.raises(ValueError,match='Saldo bancário'):
            read_caixa(b'%PDF synthetic')


def test_conferencia_itau_usa_leitor_central_e_conta_514():
    from app.company_1058 import read_itau_statement
    records=[{'DESCRIÇÃO':'BANCO ITAÚ','DATA':'03/08/2026','VALOR':-120.0,'HISTÓRICO':'PAGAMENTO PIX'},
             {'DESCRIÇÃO':'BANCO ITAÚ','DATA':'04/08/2026','VALOR':50.0,'HISTÓRICO':'Recebido: Cliente'}]
    with patch('app.engine.processar_extrato_conferencia_empresa',return_value=records) as parser:
        frame=read_itau_statement(b'%PDF testing','extrato.pdf')
    parser.assert_called_once_with(b'%PDF testing','extrato.pdf','itau')
    assert frame['VALOR'].tolist()==[-120.0,50.0]
    assert frame['CRÉDITO'].tolist()==['514','']
    assert frame['DÉBITO'].tolist()==['','514']
    assert frame['HISTÓRICO'].tolist()==['Pago: PAGAMENTO PIX','Recebido: Cliente']


def test_conferencia_itau_descricoes_genericas_com_assinatura_do_banco():
    from app.company_1058 import read_itau_statement
    records=[{'DESCRIÇÃO':'CONTA CORRENTE','DATA':'03/08/2026','VALOR':-18.0,
              'HISTÓRICO':'PIX'}]
    with patch('app.engine.processar_extrato_conferencia_empresa',return_value=records), \
         patch('app.engine.identificar_banco_inteligente',return_value='BANCO ITAU'), \
         patch('pypdf.PdfReader') as pdf:
        pdf.return_value.pages = [type('P',(),{'extract_text':lambda self:'Itaú Empresas'})()]
        result=read_itau_statement(b'%PDF synthetic','extrato.pdf')
    assert len(result)==1
    assert result.iloc[0]['CRÉDITO']=='514'


def test_conferencia_itau_rejeita_banco_errado():
    from app.company_1058 import read_itau_statement
    rows=[{'DESCRIÇÃO':'BANCO BRADESCO','DATA':'03/08/2026','VALOR':-10,'HISTÓRICO':'PIX'}]
    with patch('app.engine.processar_extrato_conferencia_empresa',return_value=rows):
        with pytest.raises(ValueError,match='outro banco'):
            read_itau_statement(b'%PDF testing','extrato.pdf')


def test_conferencia_1058_exige_conta_514_na_selecao():
    from app import migration_services as services
    from app import engine
    model=pd.DataFrame([{'DESCRIÇÃO':'BANCO ITAÚ','DATA':pd.Timestamp('2026-08-03'),'VALOR':-100.0,'HISTÓRICO':'Pago: Teste'}])
    with patch.object(engine,'ler_planilha_organizada_conferencia',return_value=(model,pd.DataFrame(columns=model.columns),None)) as reader, \
         patch.object(services,'statement',return_value=model), \
         patch.object(engine,'conciliar_empresa_com_extrato',return_value=(pd.DataFrame(columns=['ENTRADAS PLANILHA','SAÍDAS PLANILHA','ENTRADAS EXTRATO','SAÍDAS EXTRATO']),pd.DataFrame(),pd.DataFrame(),pd.DataFrame())):
        services.reconcile(1058,'itau',b'model',[('extrato.pdf',b'%PDF')])
    assert reader.call_args.args[2]=='514'


def test_itau_mensal_quarteto_carry_date_between_pages_and_ignore_summary():
    from app.itau_1058_monthly import read_itau_monthly
    from unittest.mock import MagicMock
    h1 = '''extrato mensal ag 7111 cc 99743-8 ago 2026 001|002
QUARTETO DE OBRAS LTDA.
01. Conta Corrente e Aplicações Automáticas R$ 10,00 R$ 35,00
R$ 50,00 R$ 25,00
Conta Corrente | Movimentação
data descrição entradas R$ saídas R$ saldo R$
03/08 Sispag RESIDENCIAL VERD                  50,00
Sispag TRIB MUNICIPAL                              25,00-
Apl Aplic Aut Mais                                  5,00-
'''
    h2 = '''extrato mensal ag 7111 cc 99743-8 ago 2026 002|002
data descrição entradas R$ saídas R$ saldo R$
Res Aplic Aut Mais                      5,00
totalizador de aplicações automáticas entrada R$ saída R$
Conta Corrente | Aplicações Automáticas
Sispag TRANSF CC ITAU             999.999,99-
'''
    pages=[MagicMock(extract_text=lambda **kwargs: h1),MagicMock(extract_text=lambda **kwargs:h2)]
    with patch('app.itau_1058_monthly.PdfReader') as reader:
        reader.return_value.pages=pages
        frame=read_itau_monthly(b'%PDF test')
    assert frame['VALOR'].tolist()==[50.0,-25.0,-5.0,5.0]
    assert frame['DATA'].dt.strftime('%d/%m/%Y').tolist()==['03/08/2026']*4
    assert frame['DÉBITO'].tolist()==['514','','','514']
    assert frame['CRÉDITO'].tolist()==['','514','514','']


def test_itau_mensal_quarteto_rejeita_total_incorreto():
    from app.itau_1058_monthly import read_itau_monthly
    from unittest.mock import MagicMock
    h='''extrato mensal ag 7111 cc 99743-8 ago 2026 001|001
QUARTETO DE OBRAS LTDA.
R$ 10,00 R$ 35,00
R$ 50,00 R$ 25,00
Conta Corrente | Movimentação
data descrição entradas R$ saídas R$ saldo R$
03/08 Sispag TRIB MUNICIPAL              20,00-
totalizador de aplicações automáticas'''
    with patch('app.itau_1058_monthly.PdfReader') as reader:
        reader.return_value.pages=[MagicMock(extract_text=lambda **kwargs:h)]
        with pytest.raises(ValueError,match='Totais do extrato'):
            read_itau_monthly(b'%PDF test')


def test_1058_usa_workflow_especifico():
    from app.migration_services import _workflow
    with patch('app.company_1058.workflow_1058', return_value=(b'file','ok.xlsx')) as process:
        assert _workflow(1058, {'itau': [],'caixa': []}, {}) == (b'file','ok.xlsx')
    process.assert_called_once()

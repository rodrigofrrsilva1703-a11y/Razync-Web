"""Regressões: o extrato Itaú 1058 é a fonte contábil, planilha só enriquece."""
from unittest.mock import patch
import pandas as pd
import pytest


def _frame(rows):
    return pd.DataFrame([{
        'DESCRIÇÃO': 'BANCO ITAÚ',
        'DATA': pd.Timestamp(date),
        'VALOR': value,
        'DÉBITO': '514' if value > 0 else '',
        'CRÉDITO': '514' if value < 0 else '',
        'HISTÓRICO': description,
    } for date, value, description in rows])


def test_enrichment_uses_bank_rows_and_unique_matching_only():
    from app.itau_1058_enrichment import enrich
    bank = _frame([
        ('2026-08-03',-5984.26,'Pago: Sispag TRIB MUNICIPAL'),
        ('2026-08-03',-323.0,'Pago: BOLETO PAGO FEA PARK'),
        ('2026-08-03',-323.0,'Pago: BOLETO PAGO FEA PARK'),
        ('2026-08-06',-1780.0,'Pago: Sispag TRANSF CC ITAU'),
        ('2026-08-06',-1780.0,'Pago: Sispag TRANSF CC ITAU'),
        ('2026-08-06',-1780.0,'Pago: Sispag TRANSF CC ITAU'),
        ('2026-08-07',-18000.0,'Pago: Sispag TRANSF CC ITAU'),
        ('2026-08-07',-0.03,'Pago: Rend Pago Aplic Aut Mais'),
    ])
    aux = _frame([
        ('2026-08-03',-5984.26,'Pago: IPTU'),
        ('2026-08-03',-323.0,'Pago: FEA PARK'),
        ('2026-08-03',-323.0,'Pago: FEA PARK'),
        ('2026-08-06',-1780.0,'Pago: PRO LABORE CAIO'),
        ('2026-08-06',-1780.0,'Pago: PRO LABORE CARLOS'),
        ('2026-08-06',-1780.0,'Pago: PRO LABORE PAMELA'),
        ('2026-08-07',-18000.0,'Pago: DISTRIBUICAO PAMELA'),
    ])
    with patch('app.itau_1058_enrichment.read_itau_monthly', return_value=bank), \
         patch('app.itau_1058_enrichment.read_itau', return_value=aux):
        result, audit = enrich(b'pdf', b'xlsx')
    assert len(result) == len(bank)
    assert result['VALOR'].tolist() == bank['VALOR'].tolist()
    assert result['DATA'].tolist() == bank['DATA'].tolist()
    assert result.iloc[0]['HISTÓRICO'] == 'Pago: IPTU'
    assert result.iloc[1]['HISTÓRICO'] == 'Pago: FEA PARK'
    assert result.iloc[2]['HISTÓRICO'] == 'Pago: FEA PARK'
    assert result.iloc[3:6]['HISTÓRICO'].tolist() == ['Pago: Sispag TRANSF CC ITAU']*3
    assert result.iloc[6]['HISTÓRICO'] == 'Pago: DISTRIBUICAO PAMELA'
    assert result.iloc[7]['HISTÓRICO'] == 'Pago: Rend Pago Aplic Aut Mais'
    assert (audit['SITUAÇÃO'] == 'Identificado').sum() == 4
    assert (audit['SITUAÇÃO'].str.startswith('Ambíguo')).sum() == 3


def test_enrichment_does_not_guess_if_aux_row_missing():
    from app.itau_1058_enrichment import enrich
    bank = _frame([('2026-08-10',-50000.0,'Pago: Sispag TRANSF CC ITAU'),
                   ('2026-08-10',-50000.0,'Pago: Sispag TRANSF CC ITAU')])
    aux = _frame([('2026-08-10',-50000.0,'Pago: APORTE RES PERRELLA')])
    with patch('app.itau_1058_enrichment.read_itau_monthly',return_value=bank), \
         patch('app.itau_1058_enrichment.read_itau',return_value=aux):
        result, audit = enrich(b'pdf',b'xls')
    assert result['HISTÓRICO'].tolist() == bank['HISTÓRICO'].tolist()
    assert 'Ambíguo' in audit.iloc[0]['SITUAÇÃO']


def test_workflow_1058_requires_both_itau_files():
    from app.company_1058 import workflow_1058
    with pytest.raises(ValueError, match='extrato mensal PDF e a planilha auxiliar XLSX'):
        workflow_1058({'itau':[('extrato.pdf',b'%PDF')]},{})
    with pytest.raises(ValueError, match='extrato mensal PDF e a planilha auxiliar XLSX'):
        workflow_1058({'planilha_itau':[('aux.xlsx',b'file')]},{})


def test_workflow_1058_routes_pdf_and_excel_separately():
    from app.company_1058 import workflow_1058
    from app import company_1058 as module
    sheet = _frame([('2026-08-03',-5984.26,'Pago: IPTU')])
    audit=pd.DataFrame([{'DATA':pd.Timestamp('2026-08-03'),'VALOR':-5984.26,
                         'SITUAÇÃO':'Identificado','HISTÓRICO PLANILHA':'Pago: IPTU',
                         'LINHA AUXILIAR':1}])
    with patch('app.itau_1058_monthly.read_itau_monthly',return_value=sheet) as reader, \
         patch.object(module,'read_itau',return_value=sheet) as excel_reader, \
         patch('app.itau_1058_enrichment.enrich',return_value=(sheet,audit)) as enricher, \
         patch('app.excel.gerar_modelo_abas',return_value=b'xlsx') as exporter, \
         patch('app.advanced.append_dataframe_sheets',return_value=b'xlsx_with_audit') as append:
        workbook, name=workflow_1058({'itau':[('extrato.pdf',b'%PDF')],
                                      'planilha_itau':[('aux.xlsx',b'excel')]},{})
    assert reader.call_count == 1
    assert excel_reader.call_count == 1
    enricher.assert_called_once_with(b'%PDF', b'excel')
    assert set(exporter.call_args.args[0])=={'Itaú'}
    assert append.call_count==1
    assert workbook==b'xlsx_with_audit'
    assert name.endswith('.xlsx')

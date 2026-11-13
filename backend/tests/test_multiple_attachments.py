import io
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app.attachments import merge_models
from test_fiscal_documentos import book


def fiscal(month, value=100, company='COMERCIAL TESTE LTDA'):
    end = pd.Timestamp(2026, month, 1) + pd.offsets.MonthEnd(0)
    return book([[company], ['Período:', f'01/{month:02}/2026 a {end:%d/%m/%Y}'], ['ENTRADAS'],
                 ['Código', 'Descrição', 'Valor Contábil', 'Conta'], [1152, 'Compras', value, 508]])


def ledger(months, company='COMERCIAL TESTE LTDA'):
    return book([['Empresa:', '', company], ['Conta:', 508],
                 ['Data', 'Lote', 'Histórico', 'Cta.C.Part.', 'Filial', 'Débito', 'Crédito'],
                 *[[f'03/{m:02}/2026', m, f'COMPRA CF NF {m}', 800, 242, 100, 0] for m in months]])


def test_fiscal_batch_counts_all_months_and_excludes_unselected_gaps():
    response = TestClient(app).post('/api/v1/conferencia-fiscal/preview', files=[
        ('acumuladores', ('julho.xlsx', fiscal(7))), ('acumuladores', ('setembro.xlsx', fiscal(9))),
        ('razao', ('razao.xlsx', ledger([7, 8, 9]))),
    ])
    assert response.status_code == 200, response.text
    row = response.json()['contas'][0]
    assert row['fiscal'] == 200 and row['contabil'] == 200 and row['diferenca'] == 0


def test_fiscal_batch_rejects_overlaps_and_mixed_companies():
    for other, expected in [(fiscal(7, 101), 'sobrepostos'), (fiscal(9, company='OUTRA EMPRESA LTDA'), 'empresas diferentes')]:
        response = TestClient(app).post('/api/v1/conferencia-fiscal/preview', files=[
            ('acumuladores', ('primeiro.xlsx', fiscal(7))), ('acumuladores', ('segundo.xlsx', other)),
            ('razao', ('razao.xlsx', ledger([7, 9]))),
        ])
        assert response.status_code == 422
        assert expected in response.text


def test_multiple_ledgers_csv_are_all_parsed():
    response = TestClient(app).post('/api/v1/conferencia-fiscal/preview', files=[
        ('acumuladores', ('julho.xlsx', fiscal(7))), ('acumuladores', ('setembro.xlsx', fiscal(9))),
        ('razao', ('julho.csv', b'Conta;Data;Historico;Debito;Credito;Filial\n508;03/07/2026;COMPRA CF NF 7;100;0;242')),
        ('razao', ('setembro.xlsx', ledger([9]))),
    ])
    assert response.status_code == 200, response.text
    assert response.json()['contas'][0]['contabil'] == 200


def test_merge_models_keeps_bank_and_all_rows_without_repeated_headers():
    def model(date):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            pd.DataFrame([{'DATA': date, 'VALOR': 100, 'HISTÓRICO': 'Recebido: TESTE'}]).to_excel(writer, sheet_name='Itaú', index=False)
        return out.getvalue()
    merged = merge_models([(model('01/07/2026'), 'julho.xlsx'), (model('01/09/2026'), 'setembro.xlsx')])
    table = pd.read_excel(io.BytesIO(merged), sheet_name='Itaú')
    assert list(table['DATA']) == ['01/07/2026', '01/09/2026']


def test_repeated_content_is_rejected_before_processing():
    content = fiscal(7)
    response = TestClient(app).post('/api/v1/conferencia-fiscal/preview', files=[
        ('acumuladores', ('julho.xlsx', content)), ('acumuladores', ('copia.xlsx', content)),
        ('razao', ('razao.xlsx', ledger([7]))),
    ])
    assert response.status_code == 422
    assert 'Arquivo repetido' in response.text


def test_documentary_batch_preserves_documents_and_unique_ids():
    from app.fiscal_documentos import ler_acompanhamento, _valida_relatorio
    def documents(month):
        end = pd.Timestamp(2026, month, 1) + pd.offsets.MonthEnd(0)
        return book([['COMERCIAL TESTE LTDA'], ['Período:', f'01/{month:02}/2026 a {end:%d/%m/%Y}'],
                     ['ACOMPANHAMENTO DE ENTRADAS'],
                     ['Código', 'Nota', 'Data', 'CFOP', 'Valor Contábil', 'Tipo', 'Fornecedor'],
                     [1152, month, f'03/{month:02}/2026', 1102, 100, '', 'Fornecedor Teste']])
    result = ler_acompanhamento([(documents(7), 'julho.xlsx'), (documents(9), 'setembro.xlsx')], 'lote.xlsx', 'ENTRADAS', {'1152'})
    assert len(result['documentos']) == 2
    assert len({doc['id'] for doc in result['documentos']}) == 2
    assert {doc['arquivo_origem'] for doc in result['documentos']} == {'julho.xlsx', 'setembro.xlsx'}
    preview = {'empresa_nome': 'COMERCIAL TESTE LTDA', 'periodo_fiscal': {
        'inicio': '01/07/2026', 'fim': '30/09/2026', 'intervalos': [
            {'inicio': '01/07/2026', 'fim': '31/07/2026'}, {'inicio': '01/09/2026', 'fim': '30/09/2026'}]}}
    assert _valida_relatorio(result, preview, 'ENTRADAS') == ''
    import pytest
    with pytest.raises(ValueError, match='não correspondem'):
        _valida_relatorio({**result, 'intervalos': [result['periodo']]}, preview, 'ENTRADAS')


def test_account_analysis_uses_all_files_without_requesting_ai_when_balanced():
    response = TestClient(app).post('/api/v1/conferencia-fiscal/ia/conta', data={'conta': '508', 'tipo': 'ENTRADAS'}, files=[
        ('acumuladores', ('julho.xlsx', fiscal(7))), ('acumuladores', ('setembro.xlsx', fiscal(9))),
        ('razao', ('razao.xlsx', ledger([7, 9]))),
    ])
    assert response.status_code == 200, response.text
    assert response.json()['provedor'] == 'local'

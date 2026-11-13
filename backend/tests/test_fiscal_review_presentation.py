import copy
import io
import pytest
from openpyxl import load_workbook
from app.fiscal_review_presentation import enrich_review, impact
from app.fiscal_account_ai import review_context
from app.fiscal_ai import gerar_excel_analise


def test_maior_desvio_vem_antes_do_valor_fiscal_sem_candidato():
    known = {"situacao":"VALOR_DIFERENTE","valor_brl":"R$ 100,00","valor_razao_candidato_brl":"R$ 120,00"}
    unknown = {"situacao":"VALOR_DIFERENTE","valor_brl":"R$ 9.000,00"}
    assert impact(known) > impact(unknown)
    assert impact(dict(known,diferenca_candidato_brl="-R$ 50,00")) > impact(known)


def test_referencias_sao_locais_e_candidatos_nao_viram_vinculo_confirmado():
    doc = {"referencia":"E-1","nota":"100","situacao":"CONTA_DIFERENTE","acumulador":"1152","conta_razao_candidato":"509","razao_id":"L8"}
    item = {"conta":"508","parecer":{"comparacoes_documentais":[doc]}}
    reading = {"orientacoes":[{"categoria":"CONTA_DIFERENTE","documentos":[{"referencia":"E-1"}]}]}
    result = enrich_review(reading,item,[])
    example = result['orientacoes'][0]['documentos'][0]
    assert '1152' in example['onde_conferir'] and '509' in example['onde_conferir'] and 'L8' in example['onde_conferir']
    assert 'a confirmar' in example['vinculo']
    assert 'historico_candidato' not in example


def test_contexto_isola_origem_conta_filial_e_evidencias():
    source = {'contas':[{'conta':'508','diferenca':10}]};scope={'conta':'508','tipo':'ENTRADAS','origem':'resumo'}
    original=review_context(source,scope,'242','242')
    assert original == review_context(copy.deepcopy(source),dict(reversed(list(scope.items()))),'242','242')
    assert original != review_context(source,dict(scope,conta='509'),'242','242')
    assert original != review_context(source,dict(scope,tipo='SAÍDAS'),'242','242')
    assert original != review_context(source,dict(scope,origem='documentos'),'242','242')
    assert original != review_context(source,scope,'1408','242')
    assert original != review_context({'contas':[{'conta':'508','diferenca':11}]},scope,'242','242')


def test_excel_separa_revisao_manual_dos_fatos_e_neutraliza_formula():
    payload={'analises':[{'conta':'508','tipo':'ENTRADAS','valores':{}}],
             'acompanhamento_manual':[{'title':'NF 100','note':'=1+1','status':'resolved','updatedAt':'2026-10-19T20:00:00Z'}]}
    book=load_workbook(io.BytesIO(gerar_excel_analise(payload)))
    sheet=book['Revisão manual']
    assert sheet['B2'].value == 'Resolvido manualmente'
    assert sheet['C2'].value == "'=1+1" and sheet['C2'].data_type != 'f'
    assert 'Não altera totais' in sheet['E2'].value


def test_excel_rejeita_resolucao_sem_justificativa():
    with pytest.raises(ValueError,match='revisão manual'):
        gerar_excel_analise({'analises':[{'conta':'508','tipo':'ENTRADAS','valores':{}}],
                            'acompanhamento_manual':[{'title':'NF 100','note':'','status':'resolved'}]})

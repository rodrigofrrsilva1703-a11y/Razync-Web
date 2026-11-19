import io

from openpyxl import load_workbook

from app import ai_classification_agent as agent, classification_service as base, engine
from app.classification_chart import remember_chart_approval
from app.classification_history import HistoryMatcher
from test_base_investigator import book


def test_266_reuses_a_taught_name_without_chart_or_document_number(monkeypatch, tmp_path):
    source_history = 'PIX ENVIADO - COMERCIAL SILVA LTDA'
    record = {
        'banco': 'itau', 'debito': '412', 'credito': '508', 'periodos': ['2026-09'],
        'assinatura': engine.criar_assinatura_classificacao(source_history),
        'exemplo_historico': source_history,
    }
    monkeypatch.setenv('RAZYNC_CHART_DIRECTORY', str(tmp_path))
    monkeypatch.setattr(base, 'records', lambda _: [record])
    history = 'Pago: Empresa: Comercial Silva Obs: NF 9999'
    data = book([[-100, None, 508, history], [-100, 777, 508, history]])

    def classify():
        result, summary = base.classify_with_coverage(266, data, 'itau.xlsx', plano_contas={})
        return load_workbook(io.BytesIO(result)).worksheets[0], summary

    sheet, summary = classify()
    assert sheet['D2'].value is None
    review = agent.investigate(266, data, use_ai=False)['sugestoes'][0]
    assert review['conta_sugerida'] == '412'
    assert review['situacao'] == 'MODERADA'
    assert not review['aprovada']
    assert review['evidencias'][0]['periodos_nome_normalizado'] == ['2026-09']

    remember_chart_approval(record, normalize_unstructured=True)
    sheet, summary = classify()
    assert sheet['D2'].value == 412
    assert sheet['D3'].value == 777
    assert summary['por_aprovacao_historica'] == 1
    assert not summary.get('por_plano_contas')

    matcher = HistoryMatcher([record], base.accounts(266))
    assert matcher.find('itau', 'pago', history, '30/09/2026') is None
    assert matcher.find('bradesco', 'pago', history, '15/10/2026') is None
    assert matcher.find('itau', 'recebido', history, '15/10/2026') is None
    assert matcher.find('itau', 'pago', history, '15/10/2026', {'413'}) is None
    assert matcher.find('itau', 'pago', 'Pago: Empresa: Comercial Silva Obs: Reembolso', '15/10/2026') is None
    alternate = {**record, 'debito': '413', 'aprovacoes_nome': {}}
    assert HistoryMatcher([record, alternate], base.accounts(266)).find('itau', 'pago', history, '15/10/2026') is None

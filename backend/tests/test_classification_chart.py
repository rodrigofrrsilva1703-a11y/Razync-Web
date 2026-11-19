import io
import json

from openpyxl import load_workbook

from app import classification_service
from app.classification_decision import configured_key
from test_base_investigator import book, record


def test_plan_matches_names_independently_of_document_without_overwriting_existing_account(monkeypatch):
    approved = record(periods=('2026-07', '2026-08'))
    approved['exemplo_historico'] = 'Pago: Empresa: Comercial Vale Verde Ltda Obs: 1234/2'
    chart = {'412': {
        'analitica': True, 'nome': 'Comercial Vale Verde', 'classificacao': '2.1.3.01.001',
    }}
    monkeypatch.setattr(classification_service, 'records', lambda _: [approved])
    monkeypatch.delenv('GEMINI_DECISION_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    assert not configured_key()
    source = book([
        [-100, '', 508, 'Pago: Empresa: Comercial Vale Verde Obs: 1234/2'],
        [-100, '', 508, 'Pago: Empresa: Comercial Vale Verde Obs: 1234/3'],
        [-100, 777, 508, 'Pago: Empresa: Comercial Vale Verde Obs: 1234/2'],
    ])
    options = {'modo_consolidado': False}

    def apply():
        result, summary = classification_service.classify_with_coverage(
            242, source, 'itau.xlsx', options, plano_contas=chart,
        )
        return load_workbook(io.BytesIO(result)).worksheets[0], summary

    from app.classification_chart import ChartNameMatcher

    matcher = ChartNameMatcher([approved], {'itau_508': '508'}, chart)
    first = 'Pago: Empresa: Comercial Vale Verde Obs: 1234/2'
    second = 'Pago: Empresa: Comercial Vale Verde Obs: 9999/99'
    assert matcher.find('itau_508', 'pago', first, '2026-09-15') == (
        '412', 'por_historico_confirmado_no_plano',
    )
    assert matcher.find('itau_508', 'pago', second, '2026-09-15') == matcher.find(
        'itau_508', 'pago', first, '2026-09-15',
    )
    output, _ = apply()
    assert output['D4'].value == 777

    chart['412']['classificacao'] = '1.1.2.01.001'
    matcher = ChartNameMatcher([approved], {'itau_508': '508'}, chart)
    assert matcher.find('itau_508', 'pago', first, '2026-09-15') is None

    chart['412']['classificacao'] = '2.1.3.01.001'
    alternative = {**approved, 'debito': '413'}
    matcher = ChartNameMatcher([approved, alternative], {'itau_508': '508'}, chart)
    assert matcher.find('itau_508', 'pago', first, '2026-09-15') is None


def test_transfer_pair_requires_unique_opposite_with_confirmed_bank(monkeypatch, tmp_path):
    from openpyxl import Workbook
    from app import classification_decision

    def unexpected_gemini():
        raise AssertionError('A classificação automática da 266 não usa Gemini')

    monkeypatch.setattr(classification_decision, 'configured_key', unexpected_gemini)

    monkeypatch.setattr(classification_service, 'records', lambda _: [])
    monkeypatch.delenv('GEMINI_DECISION_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    chart = {
        '508': {'analitica': True, 'nome': 'Itaú', 'classificacao': '1.1.1.02.007'},
        '506': {'analitica': True, 'nome': 'Fibra', 'classificacao': '1.1.1.02.005'},
    }
    (tmp_path / "266.json").write_text(json.dumps(chart), encoding="utf-8")
    monkeypatch.setenv("RAZYNC_CHART_DIRECTORY", str(tmp_path))
    source = Workbook()
    itau = source.active
    itau.title = 'Itaú'
    fibra = source.create_sheet('Fibra')
    for ws in (itau, fibra):
        ws.append(['DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO'])
    itau.append(['15/09/2026', 100, None, None, 'Transferência recebida'])
    fibra.append(['15/09/2026', -100, 508, 506, 'Transferência enviada'])

    def classify():
        buffer = io.BytesIO()
        source.save(buffer)
        result, summary = classification_service.classify_with_coverage(
            266, buffer.getvalue(), 'modelo.xlsx',
        )
        return load_workbook(io.BytesIO(result)), summary

    result, summary = classify()
    assert result['Itaú']['D2'].value == 506
    assert result['Fibra']['C2'].value == 508
    assert summary['por_transferencia_confirmada'] == 1

    fibra.append(['15/09/2026', -100, 508, 506, 'Outro débito de mesmo valor'])
    result, summary = classify()
    assert result['Itaú']['D2'].value is None
    assert not summary.get('por_transferencia_confirmada')


def test_title_report_uses_saved_chart_and_leaves_conflicts_pending(monkeypatch, tmp_path):
    from openpyxl import Workbook

    chart = {
        code: {'analitica': True, 'nome': 'Comercial Vale Verde', 'classificacao': '2.1.3.01.001'}
        for code in ('412', '413')
    }
    monkeypatch.setenv('RAZYNC_CHART_DIRECTORY', str(tmp_path))
    monkeypatch.setattr(classification_service, 'records', lambda _: [])
    monkeypatch.delenv('GEMINI_DECISION_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    (tmp_path / '242.json').write_text(json.dumps(chart), encoding='utf-8')

    report = Workbook()
    sheet = report.active
    sheet.append(['Contraparte', 'Título', 'Parcela', 'Natureza', 'Conta contábil'])
    sheet.append(['Comercial Vale Verde', '1234', '2', 'Pagamento', '412'])
    sheet.append(['Comercial Vale Verde', '8888', '1', 'Pagamento', '412'])
    sheet.append(['Comercial Vale Verde', '8888', '1', 'Pagamento', '413'])
    titles = io.BytesIO()
    report.save(titles)

    source = book([
        [-100, '', 508, 'Pago: Empresa: Comercial Vale Verde Ltda Obs: 1234/2'],
        [-100, '', 508, 'Pago: Empresa: Comercial Vale Verde Ltda Obs: 8888/1'],
    ])
    result, summary = classification_service.classify_with_coverage(
        242, source, 'itau.xlsx', {'modo_consolidado': False}, titulos_baixados=titles.getvalue(),
    )
    output = load_workbook(io.BytesIO(result)).worksheets[0]
    assert output['D2'].value == 412
    assert output['D3'].value is None
    assert summary['por_titulo_baixado'] == 1
    assert classification_service.chart_status(266)['analiticas'] == 0


def test_recognizes_accede_title_and_preserves_document_namespace():
    from app.classification_chart import _document_identity
    assert _document_identity(
        'Pago: Comercial Vale Verde Ltda 034433/01'
    ) == ('comercial vale verde', '034433', '01')
    assert _document_identity(
        'Recebido: Doc.PED0000131/01 - Comercial Vale Verde Ltda'
    ) == ('comercial vale verde', 'ped0000131', '01')
    assert _document_identity('Recebido: Ted Recebida 06649712000112') is None


def test_assistant_prioritizes_three_recent_periods_without_approving(monkeypatch, tmp_path):
    from app import ai_classification_agent as agent

    older = record(periods=('2026-03',), account='413')
    current = record(periods=('2026-07', '2026-08', '2026-09'))
    chart = {'412': {'analitica': True, 'nome': 'Fornecedor ABC', 'classificacao': '2.1.3.01.001'}}
    (tmp_path / '242.json').write_text(json.dumps(chart), encoding='utf-8')
    monkeypatch.setenv('RAZYNC_CHART_DIRECTORY', str(tmp_path))
    monkeypatch.setattr(classification_service, 'records', lambda _: [older, current])

    result = agent.investigate(242, book(), use_ai=False)
    suggestion = result['sugestoes'][0]
    assert suggestion['conta_sugerida'] == '412'
    assert suggestion['tres_periodos'] == {'conta': '412', 'periodos': ['2026-07', '2026-08', '2026-09']}
    assert not suggestion['aprovada']

    older['periodos'].append('2026-08')
    result = agent.investigate(242, book(), use_ai=False)
    assert 'tres_periodos' not in result['sugestoes'][0]


def test_taught_approval_reuses_name_in_later_period_and_respects_conflicts(monkeypatch, tmp_path):
    from app import ai_classification_agent as agent, base_maintenance
    from app.classification_chart import ChartNameMatcher

    base = classification_service
    monkeypatch.setattr(base, 'DB_PATH', tmp_path / 'base.sqlite')
    monkeypatch.setenv('RAZYNC_DATA_BACKEND', 'sqlite')
    monkeypatch.setenv('RAZYNC_CHART_DIRECTORY', str(tmp_path))
    monkeypatch.delenv('GEMINI_DECISION_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    original = record(periods=('2026-08',), signature='pago|comercial verde')
    original['exemplo_historico'] = 'Pago: Empresa: Comercial Verde'
    chart = {'412': {
        'analitica': True, 'nome': 'Fornecedor ABC Componentes', 'classificacao': '2.1.3.01.001',
    }}
    banks = base.accounts(242)
    with base._db() as con:
        base._save(con, 242, [original])

    def match(rows=None, date='2026-11-15', history='Pago: Empresa: Fornecedor ABC Obs: 1000/2'):
        return ChartNameMatcher(base.records(242) if rows is None else rows, banks, chart).find(
            'itau_508', 'pago', history, date,
        )

    assert match() is None
    data = book()
    investigation = agent.investigate(242, data, use_ai=False)
    approvals = [{'_aba': 'Itaú 508', '_linha': 2, 'Conta da contrapartida': '412'}]
    _, summary = agent.apply(242, data, 'modelo.xlsx', approvals, investigation['token'], remember=True)
    assert summary['aprendizados'] == 1
    target = load_workbook(io.BytesIO(book([
        [-100, '', 508, 'Pago: Empresa: Fornecedor ABC Obs: 1000/2'],
        [-100, 777, 508, 'Pago: Empresa: Fornecedor ABC Obs: 1001/2'],
    ])))
    sheet = target['Itaú 508']
    sheet['B2'] = sheet['B3'] = '15/11/2026'
    workbook = io.BytesIO()
    target.save(workbook)
    result, summary = base.classify_with_coverage(
        242, workbook.getvalue(), 'itau.xlsx', {'modo_consolidado': False}, plano_contas=chart,
    )
    result_sheet = load_workbook(io.BytesIO(result))['Itaú 508']
    assert summary['por_aprovacao_no_plano'] == 1
    assert result_sheet['D2'].value == 412
    assert result_sheet['D3'].value == 777

    with base._db() as con:
        base._save(con, 242, [record(periods=('2026-11',))])

    assert match() == ('412', 'por_aprovacao_no_plano')
    assert match(date='2026-10-31') is None
    assert match(history='Pago: Empresa: Fornecedor ABC Obs: Aluguel') is None
    assert match(rows=base.records(242) + [record(account='413')]) is None
    chart['413'] = dict(chart['412'])
    assert match() is None
    chart.pop('413')

    selection = base_maintenance.preview(242, 'itau_508', '2026-10')
    base_maintenance.delete(242, 'itau_508', '2026-10', selection['token'])
    assert match() is None

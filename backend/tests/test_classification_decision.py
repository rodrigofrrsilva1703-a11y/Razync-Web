from contextlib import nullcontext
from types import SimpleNamespace
import sys

from app import classification_decision, classification_service, engine
from test_base_investigator import book, record
from openpyxl import load_workbook
import io


def test_classification_uses_company_name_across_bank_prefixes(monkeypatch):
    learned = record()
    monkeypatch.setattr(classification_service, 'records', lambda _company: [learned])
    sheet = book([[-100, '', 508, 'PIX ENVIADO PARA FORNECEDOR ABC LTDA'],
                  [-100, '', 508, 'PIX ENVIADO'],
                  [-100, '', 508, 'PAGTO FORNECEDOR ABC OBS: ADIANTAMENTO']])
    result, summary = classification_service.classify(242, sheet, 'itau.xlsx', {'modo_consolidado': False})
    output = load_workbook(io.BytesIO(result)).worksheets[0]
    assert str(output['D2'].value) == '412'
    assert output['D3'].value is None
    assert output['D4'].value is None
    assert output['F2'].value == 'PIX ENVIADO PARA FORNECEDOR ABC LTDA'
    assert summary['por_nome_empresa'] == 1


def test_name_extraction_removes_prefix_without_changing_internal_pix():
    assert engine.extrair_nome_empresa_classificacao(
        'Recebimento via PIX de Oficina PIX Peças Ltda'
    ) == 'oficina pix pecas'


def test_decision_only_sends_anonymous_evidence_and_requires_approval(monkeypatch):
    def request(**kwargs):
        payload = str(kwargs)
        assert 'Empresa Confidencial' not in payload
        assert '412' not in payload
        assert '2026-07' not in payload
        return SimpleNamespace(answers={'g1': SimpleNamespace(choice='opcao_1')})

    client = SimpleNamespace(decisions=SimpleNamespace(create=request))
    monkeypatch.setitem(sys.modules, 'google', SimpleNamespace(
        genai=SimpleNamespace(Client=lambda **_: nullcontext(client))
    ))
    item = dict(grupo=1, situacao='MANUAL', aprovada=False, Histórico='Empresa Confidencial',
                evidencias=[
                    dict(conta='412', mesmo_banco=True, exata=True, periodos=['2026-07', '2026-08']),
                    dict(conta='413', mesmo_banco=True, exata=True, periodos=['2026-07']),
                ])
    result = classification_decision.interpret([item], 'test-key')
    assert result['estado'] == 'concluida'
    assert item['conta_sugerida'] == '412'
    assert not item['aprovada']


def test_one_approved_invoice_is_enough_for_the_same_document(monkeypatch):
    approved = record(periods=('2026-07',))
    approved['exemplo_historico'] = 'Pago: Empresa: Fornecedor ABC Obs: NF 1234'
    monkeypatch.setattr(classification_service, 'records', lambda _: [approved])
    source = book([[-100, '', 508, 'PIX ENVIADO PARA FORNECEDOR ABC NF 1234'],
                   [-100, '', 508, 'PIX ENVIADO PARA FORNECEDOR ABC NF 9000']])
    output, _ = classification_service.classify(242, source, 'itau.xlsx', {'modo_consolidado': False})
    rows = load_workbook(io.BytesIO(output)).worksheets[0]
    assert rows['D2'].value == 412
    assert rows['D3'].value is None


def test_gemini_automatic_flow_compares_then_applies_only_when_enabled(monkeypatch):
    invoice = record()
    invoice['exemplo_historico'] = 'Pago: Empresa: Fornecedor ABC Obs: NF 1234'
    refund = record(periods=('2026-07',), account='413')
    refund['exemplo_historico'] = 'Pago: Empresa: Fornecedor ABC Obs: Reembolso'
    monkeypatch.setattr(classification_service, 'records', lambda _: [invoice, refund])
    monkeypatch.setattr(classification_decision, 'configured_key', lambda: 'test-key')
    calls = []

    def request(key, context, questions):
        calls.append(questions)
        assert '412' not in str(questions)
        assert 'Fornecedor ABC' not in str(questions)
        return {name: SimpleNamespace(choice='opcao_1', confidence=.99) for name in questions}

    monkeypatch.setattr(classification_decision, 'request_choices', request)
    source = book([[-100, '', 508, 'PIX ENVIADO PARA FORNECEDOR ABC NF 9000'],
                   [-100, '', 508, 'PIX ENVIADO PARA FORNECEDOR ABC']])
    options = {'modo_consolidado': False}
    monkeypatch.delenv('GEMINI_DECISION_AUTO_APPLY', raising=False)
    shadow, summary = classification_service.classify(242, source, 'itau.xlsx', options)
    assert summary['gemini_confirmados'] == 1
    assert load_workbook(io.BytesIO(shadow)).worksheets[0]['D2'].value is None

    monkeypatch.setenv('GEMINI_DECISION_AUTO_APPLY', '1')
    applied, summary = classification_service.classify(242, source, 'itau.xlsx', options)
    rows = load_workbook(io.BytesIO(applied)).worksheets[0]
    assert rows['D2'].value == 412
    assert rows['D3'].value is None
    assert summary['por_gemini_decision'] == 1
    assert len(calls) == 2


def test_conflict_without_operation_is_evaluated_but_never_written(monkeypatch):
    monkeypatch.setattr(classification_service, 'records', lambda _: [
        record(account='412'), record(account='413'),
    ])
    monkeypatch.setattr(classification_decision, 'configured_key', lambda: 'test-key')
    monkeypatch.setenv('GEMINI_DECISION_AUTO_APPLY', '1')

    def request(key, context, questions):
        assert 'Escolha revisar' in questions['g1']['instructions']
        return {name: SimpleNamespace(choice='opcao_1', confidence=.99) for name in questions}

    monkeypatch.setattr(classification_decision, 'request_choices', request)
    output, summary = classification_service.classify(
        242, book(), 'itau.xlsx', {'modo_consolidado': False},
    )
    assert summary['gemini_avaliados'] == 1
    assert summary['por_gemini_decision'] == 0
    assert load_workbook(io.BytesIO(output)).worksheets[0]['D2'].value is None


def test_competing_accounts_require_distinct_document_evidence(monkeypatch):
    invoice = record(periods=('2026-07',))
    invoice['exemplo_historico'] = 'Pago: Empresa: Fornecedor ABC Obs: NF 1234'
    other = record(periods=('2026-07',), account='413')
    other['exemplo_historico'] = 'Pago: Empresa: Fornecedor ABC Obs: NF 5678'
    monkeypatch.setattr(classification_service, 'records', lambda _: [invoice, other])
    source = book([[-100, '', 508, 'PIX ENVIADO PARA FORNECEDOR ABC NF 1234'],
                   [-100, '', 508, 'PIX ENVIADO PARA FORNECEDOR ABC NF 9000']])
    options = {'modo_consolidado': False}
    output, _ = classification_service.classify(242, source, 'itau.xlsx', options)
    rows = load_workbook(io.BytesIO(output)).worksheets[0]
    assert rows['D2'].value == 412
    assert rows['D3'].value is None

    other['exemplo_historico'] = invoice['exemplo_historico']
    output, _ = classification_service.classify(242, source, 'itau.xlsx', options)
    assert load_workbook(io.BytesIO(output)).worksheets[0]['D2'].value is None


def test_existing_name_rule_takes_priority_over_contextual_comparison(monkeypatch):
    learned = record()
    learned['exemplo_historico'] = 'Pago: Empresa: Fornecedor ABC Obs: Contrato Regional'
    monkeypatch.setattr(classification_service, 'records', lambda _: [learned])
    source = book([[-100, '', 508, 'Pago: Empresa: Fornecedor ABC Obs: Serviço Local']])
    output, summary = classification_service.classify(
        242, source, 'itau.xlsx', {'modo_consolidado': False},
    )
    assert load_workbook(io.BytesIO(output)).worksheets[0]['D2'].value == 412
    assert summary['por_nome_empresa'] == 1

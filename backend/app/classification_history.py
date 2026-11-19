"""Evidence from the company's classified entries and taught approvals."""
from collections import defaultdict
import re

from app import engine
from app.classification_chart import (
    _month, _SPECIAL_OPERATION, _APPROVAL_SPECIAL_OPERATION, chart_approvals,
)


_STRUCTURED_PARTY = re.compile(r'\bempresa\s*:\s*(.+?)(?:\s+obs\s*:\s*(.*))?$')
_MOVEMENT_PREFIX = re.compile(
    r'^(?:(?:pago|pagamento|pagto|pgto|recebido|recebimento|pix(?:\s+(?:enviado|recebido))?)\b[\s:–-]*)+'
)
_REFERENCE = re.compile(r'\s+\b(?:nf(?:e)?|nota fiscal|documento|doc|pedido|ped)\b\s*[:#-]?\s*\d.*$')
_NUMERIC_REFERENCE = re.compile(r'(?<![a-z0-9])\d+(?:[./-]\d+)*(?![a-z0-9])')
_GENERIC = {'pix', 'ted', 'debito', 'credito', 'pagamento', 'pagto', 'boleto', 'titulo', 'enviado', 'recebido'}


def historical_identity(history):
    text = engine.normalizar_texto(engine.texto_celula_seguro(history))
    structured = _STRUCTURED_PARTY.search(text)
    if structured:
        party, details = structured[1], structured[2] or ''
    elif _MOVEMENT_PREFIX.match(text):
        party, details = _MOVEMENT_PREFIX.sub('', text), ''
    else:
        return '', ''

    party = _MOVEMENT_PREFIX.sub('', party)
    party = re.sub(r'^doc\.?\s*[a-z]*\d[\d./-]*\s+[-–]\s+', '', party)
    party = _REFERENCE.sub('', party)
    name = engine.extrair_nome_empresa_classificacao(_NUMERIC_REFERENCE.sub(' ', party))
    distinct = set(name.split()) - _GENERIC
    if len(distinct) < 2:
        return '', ''

    operations = [key for key, pattern in engine._OPERACOES_CLASSIFICACAO.items() if re.search(pattern, text)]
    if len(operations) > 1:
        return name, ''
    if operations and operations[0] != 'nota fiscal':
        return name, operations[0]
    if _SPECIAL_OPERATION.search(text) or _APPROVAL_SPECIAL_OPERATION.search(text):
        return name, ''
    # Free-form observations may describe a different accounting event.
    details = re.sub(r'\b(?:doc(?:umento)?|ped(?:ido)?|nf(?:e)?|nota fiscal)\s*[:#-]?\s*[a-z]*\d[\d./-]*\b', '', details)
    details = _NUMERIC_REFERENCE.sub('', details)
    if re.search(r'[a-z]', details):
        return name, ''
    return name, 'movimento_regular'


class HistoryMatcher:
    def __init__(self, records, bank_accounts):
        self.accounts = defaultdict(set)
        self.approvals = defaultdict(set)
        bank_codes = {engine.texto_celula_seguro(code) for code in bank_accounts.values()}
        for record in records:
            bank = record.get('banco')
            bank_account = engine.texto_celula_seguro(bank_accounts.get(bank))
            debit = engine.texto_celula_seguro(record.get('debito'))
            credit = engine.texto_celula_seguro(record.get('credito'))
            if not bank_account or (credit == bank_account) == (debit == bank_account):
                continue
            nature, account = ('pago', debit) if credit == bank_account else ('recebido', credit)
            if not account or not re.fullmatch(r'[1-9][0-9]{0,14}', account):
                continue
            name, operation = historical_identity(record.get('exemplo_historico'))
            if not name:
                continue
            party = (bank, nature, name)
            self.accounts[party].add(account)
            if account not in bank_codes and operation == 'movimento_regular':
                for approved_name, months in chart_approvals(record).items():
                    if engine.extrair_nome_empresa_classificacao(approved_name) == name:
                        self.approvals[*party, account].update(months)

    def find(self, bank, nature, history, date, competing=()):
        name, operation = historical_identity(history)
        month = _month(date)
        if operation != 'movimento_regular' or not month:
            return None
        party = (bank, nature, name)
        accounts = self.accounts.get(party, set())
        if len(accounts) != 1 or set(competing) - accounts:
            return None
        account = next(iter(accounts))
        if any(p < month for p in self.approvals.get((*party, account), ())):
            return account, 'por_aprovacao_historica'
        return None

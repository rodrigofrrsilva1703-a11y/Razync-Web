"""Enriquecimento auditável do extrato Itaú 1058 usando planilha auxiliar.

O extrato é a única fonte de datas, valores e quantidade de movimentos.
A planilha somente substitui históricos quando o pareamento é inequívoco.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import pandas as pd

from app.company_1058 import read_itau
from app.itau_1058_monthly import read_itau_monthly


def _cents(value):
    exact = Decimal(str(value)) * 100
    if exact != exact.to_integral_value():
        raise ValueError('Valor com fração de centavo no Itaú 1058.')
    return int(exact)


def _key(record):
    return (pd.Timestamp(record['DATA']).date(), _cents(record['VALOR']))


def enrich(statement_pdf, auxiliary_excel):
    """Return (bank_rows, audit_rows): one original bank row per bank movement."""
    bank = read_itau_monthly(statement_pdf).reset_index(drop=True).copy()
    auxiliary = read_itau(auxiliary_excel).reset_index(drop=True)
    original = bank.copy(deep=True)

    candidates = defaultdict(list)
    movements = defaultdict(list)
    for i, row in auxiliary.iterrows():
        candidates[_key(row)].append((i, str(row['HISTÓRICO']).strip()))
    for i, row in bank.iterrows():
        movements[_key(row)].append(i)

    audit = []
    for key in sorted(set(candidates) | set(movements)):
        aux_rows, bank_ids = candidates.get(key, []), movements.get(key, [])
        day, cents = key
        if not aux_rows:
            continue
        if not bank_ids:
            for aux_id, history in aux_rows:
                audit.append({'DATA': day, 'VALOR': cents/100, 'SITUAÇÃO': 'Sem lançamento no extrato',
                              'HISTÓRICO PLANILHA': history, 'LINHA AUXILIAR': aux_id + 1})
            continue
        # Para valores repetidos, apenas usar a planilha se todas as descrições
        # forem idênticas E as multiplicidades coincidirem. Nunca presumir ordem.
        distinct = {history.casefold() for _, history in aux_rows}
        safe = len(aux_rows) == len(bank_ids) and len(distinct) == 1
        if len(aux_rows) == len(bank_ids) == 1:
            safe = True
        if safe and all(history for _, history in aux_rows):
            for bank_id in bank_ids:
                bank.at[bank_id, 'HISTÓRICO'] = aux_rows[0][1]
            for aux_id, history in aux_rows:
                audit.append({'DATA': day, 'VALOR': cents/100, 'SITUAÇÃO': 'Identificado',
                              'HISTÓRICO PLANILHA': history, 'LINHA AUXILIAR': aux_id + 1})
        else:
            for aux_id, history in aux_rows:
                audit.append({'DATA': day, 'VALOR': cents/100, 'SITUAÇÃO': 'Ambíguo; histórico bancário preservado',
                              'HISTÓRICO PLANILHA': history, 'LINHA AUXILIAR': aux_id + 1})

    # Não permitir duplicação, exclusão ou alteração de datas e valores.
    if len(bank) != len(original):
        raise AssertionError('Quantidade de lançamentos bancários alterada.')
    for column in ('DATA', 'VALOR', 'DÉBITO', 'CRÉDITO'):
        if bank[column].tolist() != original[column].tolist():
            raise AssertionError(f'Coluna bancária {column} alterada.')
    return bank, pd.DataFrame(audit, columns=[
        'DATA', 'VALOR', 'SITUAÇÃO', 'HISTÓRICO PLANILHA', 'LINHA AUXILIAR'])

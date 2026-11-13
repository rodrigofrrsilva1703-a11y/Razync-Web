"""Extrato Bradesco da empresa 1033, com conferência de saldos em centavos."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re
import unicodedata

import pandas as pd
import pdfplumber

COLUNAS = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
MOEDA = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}$')
DATA = re.compile(r'^\d{2}/\d{2}/\d{4}$')
IDENTIDADE = re.compile(r'Extrato de:\s*Ag:\s*(\d+)\s*\|\s*CC:\s*([\d-]+)\s*\|\s*Entre\s*(\d{2}/\d{2}/\d{4})\s*e\s*(\d{2}/\d{2}/\d{4})', re.I)
INICIOS = ('TRANSF ', 'TARIFA ', 'BLOQUEIO', 'RENTAB.', 'PAGAMENTO ', 'PIX ', 'TED ', 'DOC ', 'DEBITO ', 'CREDITO ', 'SAQUE ', 'APLICACAO ', 'RESGATE ')


def normalizar(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ''.join(c for c in text if not unicodedata.combining(c)).upper().strip()


def centavos(value):
    return int(Decimal(value.replace('.', '').replace(',', '.')) * 100)


def linhas(page):
    groups = []
    for word in sorted(page.extract_words(x_tolerance=2, y_tolerance=2), key=lambda w: (w['top'], w['x0'])):
        if not groups or abs(groups[-1][0] - word['top']) > 2.3:
            groups.append((word['top'], [word]))
        else:
            groups[-1][1].append(word)
    return [sorted(words, key=lambda w: w['x0']) for _, words in groups]


def read_statement(content):
    if not content.startswith(b'%PDF') or len(content) > 25 * 1024 * 1024:
        raise ValueError('Empresa 1033: envie PDF Bradesco válido de até 25 MB.')
    try:
        document = pdfplumber.open(BytesIO(content))
    except Exception as exc:
        raise ValueError('Não foi possível abrir o extrato Bradesco.') from exc
    with document:
        if not 1 <= len(document.pages) <= 40:
            raise ValueError('Extrato Bradesco deve ter entre 1 e 40 páginas.')
        header = document.pages[0].extract_text() or ''
        if 'Extrato de: Ag:' not in header or 'Crédito (R$)' not in header:
            raise ValueError('Layout do extrato mensal Bradesco não reconhecido.')
        identity = IDENTIDADE.search(header)
        if not identity or int(identity[1]) != 1432 or identity[2].lstrip('0') != '106702-8':
            raise ValueError('Agência ou conta bancária não corresponde à empresa 1033.')
        start, end = [datetime.strptime(value, '%d/%m/%Y').date() for value in identity.groups()[2:]]
        if start > end or (start.year, start.month) != (end.year, end.month):
            raise ValueError('Extrato deve corresponder a uma competência mensal.')
        records, current_date, heading = [], None, ''
        opening = closing = total_credit = total_debit = None
        active = False
        for page in document.pages:
            for words in linhas(page):
                line = ' '.join(w['text'] for w in words)
                label = normalizar(line)
                if 'DATA' in label and 'LANCAMENTO' in label and 'SALDO' in label:
                    active = True
                    continue
                if not active:
                    continue
                if label.startswith('TOTAL '):
                    money = [(w['x0'], w['text']) for w in words if MOEDA.fullmatch(w['text'])]
                    credit = [v for x, v in money if 320 <= x < 425]
                    debit = [v for x, v in money if 425 <= x < 520]
                    balance = [v for x, v in money if x >= 520]
                    if len(credit) != 1 or len(debit) != 1 or len(balance) != 1:
                        raise ValueError('Totais bancários não reconhecidos.')
                    total_credit, total_debit, closing = centavos(credit[0]), abs(centavos(debit[0])), centavos(balance[0])
                    active = False
                    continue
                if label.startswith(('ULTIMOS LANCAMENTOS', 'SALDOS INVEST')):
                    active = False
                    continue
                if 'SALDO ANTERIOR' in label:
                    values = [w['text'] for w in words if w['x0'] >= 520 and MOEDA.fullmatch(w['text'])]
                    if len(values) != 1 or opening is not None or records:
                        raise ValueError('Saldo anterior ausente ou repetido.')
                    opening = centavos(values[0])
                    continue
                date = next((w['text'] for w in words if w['x0'] < 100 and DATA.fullmatch(w['text'])), None)
                money = [(w['x0'], w['text']) for w in words if w['x0'] >= 320 and MOEDA.fullmatch(w['text'])]
                credit = [v for x, v in money if 320 <= x < 425]
                debit = [v for x, v in money if 425 <= x < 520]
                balance = [v for x, v in money if x >= 520]
                if len(balance) == 1 and len(credit) + len(debit) == 1:
                    if date:
                        current_date = datetime.strptime(date, '%d/%m/%Y').date()
                    if current_date is None:
                        raise ValueError('Movimentação sem data.')
                    if not start <= current_date <= end:
                        raise ValueError('Movimento fora da competência do extrato.')
                    amount = centavos(credit[0]) if credit else -abs(centavos(debit[0]))
                    if credit and amount <= 0 or debit and centavos(debit[0]) >= 0:
                        raise ValueError('Natureza do lançamento bancário inválida.')
                    inline = ' '.join(w['text'] for w in words if 100 <= w['x0'] < 260)
                    history = ' '.join(x for x in (heading, inline) if x).strip()
                    if not history:
                        raise ValueError('Movimento sem histórico bancário.')
                    heading = ''
                    records.append({'date': current_date, 'value': amount, 'history': history, 'balance': centavos(balance[0])})
                else:
                    detail = ' '.join(w['text'] for w in words if 95 <= w['x0'] < 320).strip()
                    if not detail:
                        continue
                    if normalizar(detail).startswith(INICIOS):
                        heading = detail
                    elif records and not heading:
                        records[-1]['history'] += ' ' + detail
        if opening is None or closing is None or total_credit is None or total_debit is None or not records or heading:
            raise ValueError('Extrato incompleto: movimentos e saldos obrigatórios.')
        running = opening
        for record in records:
            running += record['value']
            if running != record['balance']:
                raise ValueError('Saldo intermediário do Bradesco diverge das movimentações.')
        if running != closing or sum(max(r['value'], 0) for r in records) != total_credit or -sum(min(r['value'], 0) for r in records) != total_debit:
            raise ValueError('Entradas, saídas ou saldo final divergentes no extrato.')
        return pd.DataFrame([{
            'DESCRIÇÃO': 'BANCO BRADESCO',
            'DATA': pd.Timestamp(row['date']), 'VALOR': row['value'] / 100,
            'DÉBITO': '9' if row['value'] > 0 else '',
            'CRÉDITO': '9' if row['value'] < 0 else '',
            'HISTÓRICO': ('Recebido: ' if row['value'] > 0 else 'Pago: ') + row['history'],
        } for row in records], columns=COLUNAS)


def workflow_1033(roles, options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    uploads = roles.get('extrato') or []
    if not uploads:
        raise ValueError('Envie o extrato mensal Bradesco em PDF.')
    frames, periods = [], set()
    for filename, content in uploads:
        if not filename.lower().endswith('.pdf'):
            raise ValueError('O extrato da empresa 1033 deve ser PDF.')
        frame = read_statement(content)
        month = pd.Timestamp(frame['DATA'].iloc[0]).to_period('M')
        if month in periods:
            raise ValueError('Competência repetida: envie um extrato por mês.')
        periods.add(month)
        frames.append(frame)
    result = filter_frame(pd.concat(frames, ignore_index=True), options)
    if result.empty:
        raise ValueError('Nenhum lançamento encontrado no período selecionado.')
    result = result.sort_values('DATA', kind='stable')
    return gerar_modelo_abas({'Bradesco': result}, date_format='dd/mm/yyyy'), 'EMPRESA_1033_BRADESCO_MODELO_DOMINIO.xlsx'

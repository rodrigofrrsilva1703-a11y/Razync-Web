"""Santander consolidado mensal: conta corrente da empresa 1522, sem duplicar investimentos."""
from __future__ import annotations

import calendar
import hashlib
import io
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

import pdfplumber
import pandas as pd

COLUMNS = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
HOLDER = 'PRISCILA CAMARGO GARCIA DE OLIVEIRA LTDA'
MONTHS = {'janeiro':1,'fevereiro':2,'marco':3,'abril':4,'maio':5,'junho':6,
          'julho':7,'agosto':8,'setembro':9,'outubro':10,'novembro':11,'dezembro':12}
MONEY = re.compile(r'^-?\d+(?:\.\d{3})*,\d{2}-?$')


def normalize(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text)
                           if not unicodedata.combining(c)).upper().split())


def cents(text):
    negative = text.startswith('-') or text.endswith('-')
    amount = int(Decimal(text.strip('-').replace('.', '').replace(',', '.')) * 100)
    return -amount if negative else amount


def lines(words):
    rows = []
    for word in sorted(words, key=lambda w:(w['top'], w['x0'])):
        if not rows or abs(word['top'] - rows[-1][0]['top']) > 2:
            rows.append([word])
        else:
            rows[-1].append(word)
    return [sorted(row, key=lambda w:w['x0']) for row in rows]


def read_statement(content: bytes, filename: str = 'extrato.pdf') -> pd.DataFrame:
    if not filename.lower().endswith('.pdf') or not content.startswith(b'%PDF'):
        raise ValueError('Santander 513: envie o extrato consolidado original em PDF.')
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [(p.extract_text() or '', p.extract_words(x_tolerance=2, y_tolerance=2), p.height)
                     for p in pdf.pages]
    except Exception as exc:
        raise ValueError('Santander 513: não foi possível ler o PDF.') from exc
    header = normalize('\n'.join(p[0] for p in pages[:2]))
    if HOLDER not in header:
        raise ValueError('Santander 513: o titular do extrato não corresponde à empresa 1522.')
    if 'EXTRATO CONSOLIDADO' not in header:
        raise ValueError('Santander 513: use o extrato consolidado mensal do Santander.')
    period = re.search(r'\b('+'|'.join(MONTHS)+r')\s*/\s*(20\d{2})\b',header.lower())
    if not period:
        raise ValueError('Santander 513: mês e ano do extrato não identificados.')
    month, year = MONTHS[period[1]], int(period[2])
    start, end = date(year,month,1), date(year,month,calendar.monthrange(year,month)[1])
    records, pending = [], None
    active_date = None
    balance = None
    opening = None
    finished = False
    table_seen = False

    def flush():
        nonlocal pending
        if pending:
            history = ' '.join(pending.pop('_history'))
            history = re.sub(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', '', history)
            history = re.sub(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b', '', history)
            history = ' '.join(history.split())
            pending['HISTÓRICO'] = ('Pago: ' if pending['VALOR'] < 0 else 'Recebido: ') + history
            records.append(pending)
            pending = None

    for text, words, height in pages:
        if finished:
            break
        rows = lines(words)
        labels = next((r for r in rows if {'CREDITOS','DEBITOS'} <= {normalize(w['text']) for w in r}),None)
        if not labels:
            continue
        credit = next(w for w in labels if normalize(w['text']) == 'CREDITOS')
        debit = next(w for w in labels if normalize(w['text']) == 'DEBITOS')
        heading = next((r for r in rows if r[0]['top'] < credit['top'] and
                        {'DATA','DESCRICAO','DOCUMENTO','SALDO'} <= {normalize(w['text']) for w in r}),None)
        if not heading:
            raise ValueError('Santander 513: colunas da movimentação não reconhecidas.')
        description_x = next(w['x0'] for w in heading if normalize(w['text']) == 'DESCRICAO')
        document_x = min(w['x0'] for w in heading if normalize(w['text']) in {'Nº','DOCUMENTO'})
        saldo = next(w for w in heading if normalize(w['text']) == 'SALDO')
        split_credit = (credit['x1'] + debit['x0']) / 2
        split_balance = (debit['x1'] + saldo['x0']) / 2
        table_seen = True
        for row in rows:
            if row[0]['top'] <= credit['top']+2 or row[0]['top'] > height-55:
                continue
            description = ' '.join(w['text'] for w in row if description_x-2 <= w['x0'] < document_x-3)
            norm = normalize(description)
            if not description:
                continue
            amounts = [w for w in row if w['x0'] > document_x and MONEY.fullmatch(w['text'])]
            balances = [w for w in amounts if (w['x0']+w['x1'])/2 >= split_balance]
            if norm.startswith('SALDO EM '):
                flush()
                if len(balances) != 1:
                    raise ValueError('Santander 513: saldo da conta corrente não identificado.')
                observed = cents(balances[0]['text'])
                saldo_date = re.fullmatch(r'SALDO EM (\d{2})/(\d{2})',norm)
                expected_date = start-timedelta(days=1) if balance is None else end
                if not saldo_date or (int(saldo_date[1]),int(saldo_date[2])) != (expected_date.day,expected_date.month):
                    raise ValueError('Santander 513: datas dos saldos incompatíveis com o mês do extrato.')
                if balance is None:
                    balance = opening = observed
                else:
                    if observed != balance:
                        raise ValueError('Santander 513: os movimentos não fecham com o saldo final do extrato.')
                    finished = True
                    break
                continue
            movement = [w for w in amounts if (w['x0']+w['x1'])/2 < split_balance]
            if movement:
                flush()
                if len(movement) != 1 or balance is None:
                    raise ValueError('Santander 513: movimento ou saldo inicial ambíguo.')
                date_text = ' '.join(w['text'] for w in row if w['x0'] < description_x-2)
                if date_text:
                    if not re.fullmatch(r'\d{2}/\d{2}',date_text):
                        raise ValueError('Santander 513: data de movimento inválida.')
                    try:
                        day, movement_month = map(int,date_text.split('/'))
                        active_date = date(year,movement_month,day)
                    except ValueError as exc:
                        raise ValueError('Santander 513: data de movimento inválida.') from exc
                if active_date is None or not start <= active_date <= end:
                    raise ValueError('Santander 513: movimento fora do mês informado no extrato.')
                word = movement[0]
                debit_column = (word['x0']+word['x1'])/2 >= split_credit
                amount = cents(word['text'])
                if not debit_column and amount < 0:
                    raise ValueError('Santander 513: sinal incompatível com a coluna de créditos.')
                amount = -abs(amount) if debit_column else amount
                balance += amount
                if len(balances)>1 or balances and cents(balances[0]['text']) != balance:
                    raise ValueError(f'Santander 513: saldo divergente em {active_date:%d/%m/%Y}. Confira o PDF original.')
                pending = {'DESCRIÇÃO':'BANCO SANTANDER','DATA':active_date.strftime('%d/%m/%Y'),
                           'VALOR':amount/100,'DÉBITO':'513' if amount>0 else '',
                           'CRÉDITO':'513' if amount<0 else '', '_history':[description]}
            elif any(re.fullmatch(r'\d{2}/\d{2}',w['text']) for w in row if w['x0']<description_x-2):
                raise ValueError('Santander 513: linha com data, mas sem valor de movimento reconhecido.')
            elif pending:
                pending['_history'].append(description)
    flush()
    if not table_seen or not records or opening is None or not finished:
        raise ValueError('Santander 513: movimentação incompleta; faltam movimentos ou saldos da conta corrente.')
    frame = pd.DataFrame(records, columns=COLUMNS)
    frame.attrs.update(period=f'{year}-{month:02}',opening_balance=opening/100,closing_balance=balance/100)
    return frame


def workflow_1522(roles, options):
    from app.migration_services import filter_frame
    from app.excel import gerar_modelo_abas
    uploads = roles.get('santander') or []
    if not uploads:
        raise ValueError('Envie o extrato consolidado Santander da empresa 1522.')
    seen, periods, frames = set(), set(), []
    for filename, content in uploads:
        digest = hashlib.sha256(content).digest()
        if digest in seen:
            raise ValueError('Santander 513: o mesmo extrato foi enviado mais de uma vez.')
        seen.add(digest)
        frame = read_statement(content,filename)
        if frame.attrs['period'] in periods:
            raise ValueError('Santander 513: já existe um extrato consolidado deste mês. Evite duplicar movimentos.')
        periods.add(frame.attrs['period'])
        frames.append(frame)
    frame = filter_frame(pd.concat(frames,ignore_index=True),options)
    if frame.empty:
        raise ValueError('Nenhum movimento Santander no período selecionado.')
    order = pd.to_datetime(frame['DATA'],format='%d/%m/%Y')
    frame = frame.iloc[order.argsort(kind='stable')].reset_index(drop=True)
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(gerar_modelo_abas({'Santander':frame})))
    for row in workbook['Santander'].iter_rows(min_row=2,min_col=2,max_col=2):
        row[0].number_format = 'dd/mm/yyyy'
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), 'PRISCILA_1522_MODELO_DOMINIO.xlsx'

"""Persistent adapter for the complete original classification and review rules."""
from __future__ import annotations
import hashlib
import io
import json
import os
import sqlite3
import urllib.request
import urllib.parse
from pathlib import Path
import pandas as pd
from app import engine
from app.migration_services import accounts, slug

DB_PATH = Path(os.getenv('RAZYNC_DB_PATH', '/data/razync.db'))

def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript('''
      CREATE TABLE IF NOT EXISTS classification_records(
        company INTEGER NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(company,id));
      CREATE TABLE IF NOT EXISTS classification_imports(
        company INTEGER NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(company,digest));
    ''')
    return con

def _save(con, company, records):
    for record in records:
        record = dict(record)
        record['empresa'] = slug(company)
        identity = hashlib.sha256(f"{record['empresa']}|{record['banco']}|{record['assinatura']}|{record['debito']}|{record['credito']}".encode()).hexdigest()
        record['id'] = identity
        old = con.execute('SELECT payload FROM classification_records WHERE company=? AND id=?', (company, identity)).fetchone()
        if old:
            previous = json.loads(old['payload'])
            record['periodos'] = sorted(set(record.get('periodos', []) + previous.get('periodos', [])))
            record['ocorrencias'] = max(int(record.get('ocorrencias', 1)), int(previous.get('ocorrencias', 1)))
        con.execute('INSERT OR REPLACE INTO classification_records VALUES(?,?,?)', (company, identity, json.dumps(record, ensure_ascii=False)))

def records(company):
    con = _db()
    try:
        result = [json.loads(row['payload']) for row in con.execute('SELECT payload FROM classification_records WHERE company=?', (company,))]
        # Preserve all previously learned v0.3 records without rewriting the table.
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='patterns'").fetchone():
            known = {(r['banco'], r['assinatura'], r['debito'], r['credito']) for r in result}
            for row in con.execute('SELECT * FROM patterns WHERE company=?', (company,)):
                bank = row['bank']
                bank = 'bb' if company == 242 and bank == 'banco_brasil' else 'itau_512' if company == 1408 and bank == 'itau' else bank
                account = accounts(company).get(bank)
                if not account:
                    continue
                debit, credit = (row['counterpart'], account) if row['nature'] == 'pago' else (account, row['counterpart'])
                identity = (bank, row['signature'], debit, credit)
                if identity in known:
                    continue
                matching = next((r for r in result if (r['banco'], r['assinatura'], r['debito'], r['credito']) == identity), None)
                if matching:
                    matching['periodos'] = sorted(set(matching['periodos'] + [row['period']]))
                    matching['ocorrencias'] += row['occurrences']
                else:
                    result.append({'empresa': slug(company), 'banco': bank, 'assinatura': row['signature'],
                        'debito': debit, 'credito': credit, 'periodos': [row['period']],
                        'ocorrencias': row['occurrences'], 'exemplo_historico': row['example']})
        return result
    finally:
        con.close()

def status(company):
    rows = records(company)
    return {'patterns': len(rows), 'banks': len({r['banco'] for r in rows}),
            'periods': len({p for r in rows for p in r.get('periodos', [])})}

class SourceFile(io.BytesIO):
    def __init__(self, content, filename):
        super().__init__(content)
        self.name = filename

def learn(company, content, filename, data_inicial='', data_final=''):
    digest = hashlib.sha256(content).hexdigest()
    con = _db()
    try:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT 1 FROM classification_imports WHERE company=? AND digest=?', (company, digest)).fetchone():
            return 0
        if filename.lower().endswith('.json'):
            payload = json.loads(content)
            if not isinstance(payload, dict) or int(payload.get('company', -1)) != company:
                raise ValueError('A base importada pertence a outra empresa.')
            imported = payload.get('records', [])
            if not isinstance(imported, list):
                raise ValueError('Base de classificações inválida.')
        else:
            imported = engine.importar_arquivos_classificados([SourceFile(content, filename)], slug(company), accounts(company))
        if bool(data_inicial) != bool(data_final):
            raise ValueError('Informe as duas datas do período.')
        if data_inicial:
            inicio = pd.Timestamp(data_inicial).to_period('M')
            fim = pd.Timestamp(data_final).to_period('M')
            if fim < inicio:
                raise ValueError('A Data Final não pode ser anterior à Data Inicial.')
            meses = {str(periodo) for periodo in pd.period_range(inicio, fim, freq='M')}
            imported = [
                item for item in imported
                if any(str(periodo) in meses for periodo in (item.get('periodos') or []))
            ]
            if not imported:
                raise ValueError('Nenhum padrão revisado foi encontrado no período informado.')
        for item in imported:
            if not all(k in item for k in ('banco', 'assinatura', 'debito', 'credito', 'periodos')) or item['banco'] not in accounts(company):
                raise ValueError('Padrão inválido ou banco não configurado para esta empresa.')
        if not imported:
            raise ValueError('Nenhum padrão revisado foi encontrado. Envie um Modelo Domínio ou Razão com as contas preenchidas.')
        _save(con, company, imported)
        con.execute('INSERT INTO classification_imports VALUES(?,?)', (company, digest))
        con.commit()
        return sum(int(r.get('ocorrencias', 1)) for r in imported)
    finally:
        con.close()

def classify(company, content, filename, options=None):
    options = options or {}
    return engine.classificar_planilha_final(content, filename, records(company), accounts(company),
        empresa_classificacao=slug(company), coluna_substituir=options.get('coluna_substituir', ''),
        valores_substituiveis=options.get('valores_substituiveis', []),
        modo_consolidado_eletro_forte=bool(options.get('modo_consolidado', company in {242, 1408})),
        data_inicial=options.get('data_inicial', ''), data_final=options.get('data_final', ''))

def pending(company, content, data_inicial='', data_final=''):
    frame = engine.extrair_pendencias_revisao_inteligente(content, accounts(company))
    if bool(data_inicial) != bool(data_final):
        raise ValueError('Informe as duas datas do período.')
    if data_inicial and not frame.empty:
        inicio = pd.Timestamp(data_inicial).normalize()
        fim = pd.Timestamp(data_final).normalize()
        if fim < inicio:
            raise ValueError('A Data Final não pode ser anterior à Data Inicial.')
        datas = pd.to_datetime(frame['Data'], dayfirst=True, errors='coerce')
        frame = frame.loc[datas.between(inicio, fim, inclusive='both')].copy()
    return json.loads(frame.to_json(orient='records', date_format='iso', force_ascii=False))

def review(company, content, filename, revisions, remember=False):
    expected = pending(company, content)
    identities = {(r['_aba'], int(r['_linha'])): r for r in expected}
    validated = []
    for requested in revisions:
        identity = (requested.get('_aba'), int(requested.get('_linha', 0)))
        if identity not in identities:
            raise ValueError('O lançamento já está classificado ou não pertence à revisão deste arquivo.')
        row = dict(identities[identity])
        row['Conta da contrapartida'] = str(requested.get('Conta da contrapartida', '')).strip()
        validated.append(row)
    workbook, applied, new_records = engine.aplicar_revisoes_inteligentes(content, pd.DataFrame(validated), filename, slug(company), accounts(company))
    if remember:
        con = _db()
        try:
            _save(con, company, new_records)
            con.commit()
        finally:
            con.close()
    return workbook, {'aplicadas': applied, 'aprendizados': len(new_records) if remember else 0}

def import_original_online(company):
    """Explicit read-only copy; never write to the original database."""
    url = os.getenv('SUPABASE_URL', '').split('/rest/v1')[0].rstrip('/')
    key = os.getenv('SUPABASE_SERVICE_KEY', '')
    if not url.startswith('https://') or not key:
        raise ValueError('Configure SUPABASE_URL e SUPABASE_SERVICE_KEY somente no Railway para importar a base original.')
    query = urllib.parse.urlencode({'empresa': 'eq.' + slug(company), 'select': '*'})
    imported, offset = [], 0
    while True:
        request = urllib.request.Request(f'{url}/rest/v1/classificacoes_bancarias?{query}&limit=1000&offset={offset}', headers={'apikey': key, 'Authorization': f'Bearer {key}'})
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        imported.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return learn(company, json.dumps({'company': company, 'records': imported}).encode(), 'base-original.json')

def clear(company):
    con = _db()
    try:
        for table in ('classification_records', 'classification_imports'):
            con.execute(f'DELETE FROM {table} WHERE company=?', (company,))
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='patterns'").fetchone():
            con.execute('DELETE FROM patterns WHERE company=?', (company,))
        con.commit()
    finally:
        con.close()

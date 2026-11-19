"""Persistent adapter for the complete original classification and review rules."""
from __future__ import annotations
from functools import partial
import hashlib
import io
import json
from app.document_privacy import mask_identifiers
import os
import sqlite3
import urllib.request
import urllib.parse
from pathlib import Path
import pandas as pd
from app import engine, persistence
from app.migration_services import accounts, slug

DB_PATH = Path(os.getenv('RAZYNC_DB_PATH', '/data/razync.db'))

# Perfis originais da Base Inteligente da empresa 242 no Streamlit.
# O frontend envia apenas a origem; as contas elegíveis são decididas aqui.
ELETRO_242_CLASSIFICATION_PROFILES = {
    'consolidada': {
        'modo_consolidado': True,
        'coluna_substituir': '',
        'valores_substituiveis': [],
    },
    'despesa': {
        'modo_consolidado': False,
        'coluna_substituir': 'debito',
        'valores_substituiveis': ['0', ''],
    },
    'fornecedor': {
        'modo_consolidado': False,
        'coluna_substituir': 'debito',
        'valores_substituiveis': ['166', '0', ''],
    },
    'recebido': {
        'modo_consolidado': False,
        'coluna_substituir': 'credito',
        'valores_substituiveis': ['166', '0', '14', '16', ''],
    },
    'francesinhas': {
        'modo_consolidado': False,
        'coluna_substituir': 'credito',
        'valores_substituiveis': [''],
    },
}

def resolve_classification_options(company, options=None):
    resolved = dict(options or {})
    if int(company) == 242:
        origem = str(resolved.get('origem_242') or '').strip().casefold()
        if origem:
            if origem not in ELETRO_242_CLASSIFICATION_PROFILES:
                raise ValueError('Modo de classificação inválido para a empresa 242.')
            resolved.update(ELETRO_242_CLASSIFICATION_PROFILES[origem])
    elif int(company) == 1408:
        # No Streamlit a filial tem apenas "Modelo Domínio consolidado".
        # Pagamentos e recebimentos substituem somente conta vazia/0.
        resolved.update({
            'modo_consolidado': True,
            'coluna_substituir': '',
            'valores_substituiveis': [],
        })
    return resolved

def _db():
    con = persistence.connect(DB_PATH)
    if persistence.is_postgres(con):return con
    con.executescript('''
      CREATE TABLE IF NOT EXISTS classification_records(
        company INTEGER NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(company,id));
      CREATE TABLE IF NOT EXISTS classification_imports(
        company INTEGER NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(company,digest));
    ''')
    return con

def _save(con, company, records):
    from app.classification_chart import chart_approvals

    # One read and one upsert per batch instead of two network trips per pattern.
    # SQLite keeps batches below its traditional 999-parameter limit.
    batch_size = 1000 if persistence.is_postgres(con) else 250
    for offset in range(0, len(records), batch_size):
        prepared = []
        for source in records[offset:offset + batch_size]:
            record = dict(source)
            if "exemplo_historico" in record:
                record["exemplo_historico"] = mask_identifiers(record["exemplo_historico"])[:500]
            record['empresa'] = slug(company)
            record['id'] = hashlib.sha256(f"{record['empresa']}|{record['banco']}|{record['assinatura']}|{record['debito']}|{record['credito']}".encode()).hexdigest()
            prepared.append(record)
        identities = list(dict.fromkeys(record['id'] for record in prepared))
        placeholders = ','.join('?' for _ in identities)
        previous = {row['id']: json.loads(row['payload']) for row in con.execute(
            f'SELECT id,payload FROM classification_records WHERE company=? AND id IN ({placeholders})',
            (company, *identities))}
        updates = {}
        for record in prepared:
            identity = record['id']
            old = updates.get(identity, previous.get(identity))
            approvals = chart_approvals(record)
            if old:
                for name, periods in chart_approvals(old).items():
                    approvals.setdefault(name, set()).update(periods)
                record['periodos'] = sorted(set(record.get('periodos', []) + old.get('periodos', [])))
                record['ocorrencias'] = max(int(record.get('ocorrencias', 1)), int(old.get('ocorrencias', 1)))
            if approvals:
                record['aprovacoes_nome'] = {name: sorted(periods) for name, periods in approvals.items()}
            else:
                record.pop('aprovacoes_nome', None)
            updates[identity] = record
        values = ','.join('(?,?,?)' for _ in updates)
        parameters = tuple(value for record in updates.values()
                           for value in (company, record['id'], json.dumps(record, ensure_ascii=False)))
        con.execute('INSERT INTO classification_records(company,id,payload) VALUES ' + values +
                    ' ON CONFLICT(company,id) DO UPDATE SET payload=excluded.payload', parameters)

def records(company):
    con = _db()
    try:
        result = [json.loads(row['payload']) for row in con.execute('SELECT payload FROM classification_records WHERE company=?', (company,))]
        # Preserve all previously learned v0.3 records without rewriting the table.
        if persistence.table_exists(con, 'patterns'):
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

def _learning_records(company, content, filename, data_inicial='', data_final=''):
    if filename.lower().endswith('.json'):
        payload = json.loads(content)
        if not isinstance(payload, dict) or int(payload.get('company', -1)) != company:
            raise ValueError('A base importada pertence a outra empresa.')
        imported = payload.get('records', [])
        if not isinstance(imported, list):
            raise ValueError('Base de classificações inválida.')
    else:
        # Razões antigos exportados pelo Domínio podem ser OLE/BIFF com
        # apontadores internos de planilha inválidos. O leitor especializado
        # tenta a recuperação em memória, sem regravar o documento original.
        # Se não for possível, não submeter o mesmo XLS corrompido ao leitor
        # genérico, que expõe ao usuário "Expected BOF record".
        if filename.lower().endswith('.xls'):
            from razync.dominio_ledger import _ler_bruto
            recovered = _ler_bruto(content, filename)
            if recovered is None or recovered.empty:
                raise ValueError(
                    'Não foi possível ler este Razão .xls do Domínio: a estrutura '
                    'interna do arquivo está inconsistente. Exporte novamente '
                    'o Razão como XLSX no Domínio ou envie o XLS original para '
                    'análise da recuperação. Nenhum lançamento foi aprendido.'
                )
        try:
            imported = engine.importar_arquivos_classificados(
                [SourceFile(content, filename)], slug(company), accounts(company))
        except Exception as exc:
            if filename.lower().endswith('.xls') and (
                'BOF' in str(exc) or 'Unsupported format' in str(exc)
            ):
                raise ValueError(
                    'O Razão .xls não pôde ser interpretado integralmente. '
                    'Exporte novamente em XLSX ou envie o XLS original para '
                    'avaliar sua recuperação. Nenhum lançamento foi aprendido.'
                ) from exc
            raise
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
    return imported


def learn(company, content, filename, data_inicial='', data_final=''):
    digest_source = content + f"|{data_inicial}|{data_final}".encode("utf-8") if (data_inicial or data_final) else content
    digest = hashlib.sha256(digest_source).hexdigest()
    con = _db()
    try:
        if con.execute('SELECT 1 FROM classification_imports WHERE company=? AND digest=?', (company, digest)).fetchone():
            return 0
    finally:
        con.close()
    # Parsing and validating a large workbook must not hold the shared write lock.
    imported = _learning_records(company, content, filename, data_inicial, data_final)
    learned = sum(int(r.get('ocorrencias', 1)) for r in imported)
    con = _db()
    try:
        con.execute('BEGIN IMMEDIATE')
        # Another request may have learned this file while it was being parsed.
        if con.execute('SELECT 1 FROM classification_imports WHERE company=? AND digest=?', (company, digest)).fetchone():
            return 0
        _save(con, company, imported)
        con.execute('INSERT INTO classification_imports VALUES(?,?)', (company, digest))
        con.commit()
        return learned
    finally:
        con.close()

def _limit_classified_workbook_to_period(original_content, classified_content, data_inicial='', data_final=''):
    if bool(data_inicial) != bool(data_final):
        raise ValueError('Informe as duas datas do período.')
    if not data_inicial:
        return classified_content, None
    inicio = pd.Timestamp(data_inicial).normalize()
    fim = pd.Timestamp(data_final).normalize()
    if fim < inicio:
        raise ValueError('A Data Final não pode ser anterior à Data Inicial.')

    from openpyxl import load_workbook
    original = load_workbook(io.BytesIO(original_content), data_only=False)
    result = load_workbook(io.BytesIO(classified_content), data_only=False)
    changed = 0

    for ws in result.worksheets:
        if ws.title not in original.sheetnames or 'retir' in engine.normalizar_texto(ws.title):
            continue
        source = original[ws.title]
        header = None
        columns = {}
        for row_number in range(1, min(source.max_row, 30) + 1):
            test = {
                engine.normalizar_texto(engine.texto_celula_seguro(source.cell(row_number, col).value)).strip(): col
                for col in range(1, source.max_column + 1)
            }
            if all(name in test for name in ('historico', 'debito', 'credito')):
                header, columns = row_number, test
                break
        if header is None:
            continue
        data_col = columns.get('data')
        if data_col is None:
            raise ValueError(f'A aba {ws.title} não possui coluna DATA para aplicar o período.')
        debit_col, credit_col = columns['debito'], columns['credito']

        for row_number in range(header + 1, source.max_row + 1):
            raw_date = source.cell(row_number, data_col).value
            parsed = pd.to_datetime(raw_date, dayfirst=True, errors='coerce')
            inside = not pd.isna(parsed) and inicio <= parsed.normalize() <= fim
            source_debit = source.cell(row_number, debit_col).value
            source_credit = source.cell(row_number, credit_col).value
            if not inside:
                ws.cell(row_number, debit_col).value = source_debit
                ws.cell(row_number, credit_col).value = source_credit
            elif (
                ws.cell(row_number, debit_col).value != source_debit
                or ws.cell(row_number, credit_col).value != source_credit
            ):
                changed += 1

    output = io.BytesIO()
    result.save(output)
    return output.getvalue(), changed


def chart_directory():
    return Path(os.getenv('RAZYNC_CHART_DIRECTORY') or DB_PATH.parent / 'company-charts')


def save_chart(company, content, company_name):
    from app.classification_chart import parse_chart_pdf, save_company_chart

    chart = parse_chart_pdf(content, company_name)
    save_company_chart(chart_directory(), company, chart)
    return {'contas': len(chart), 'analiticas': sum(entry['analitica'] for entry in chart.values())}


def chart_status(company):
    from app.classification_chart import load_company_chart

    chart = load_company_chart(chart_directory(), company)
    return {'contas': len(chart or {}), 'analiticas': sum(entry['analitica'] for entry in (chart or {}).values())}


def classify(company, content, filename, options=None, *, plano_contas=None, titulos_baixados=None):
    from app import classification_decision

    options = resolve_classification_options(company, options)
    start, end = options.get('data_inicial', ''), options.get('data_final', '')
    if bool(start) != bool(end):
        raise ValueError('Informe as duas datas do período.')
    period = (pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()) if start else None
    if period and period[1] < period[0]:
        raise ValueError('A Data Final não pode ser anterior à Data Inicial.')
    # A empresa 266 usa apenas as regras e evidências locais na classificação automática.
    key = '' if int(company) == 266 else classification_decision.configured_key()
    learned = records(company)
    bank_accounts = accounts(company)
    history_lookup = None
    if int(company) == 266:
        from app.classification_history import HistoryMatcher

        history_lookup = HistoryMatcher(learned, bank_accounts).find
    chart_lookup = None
    transfer_lookup = None
    from app.classification_chart import (
        ChartNameMatcher, load_company_chart, match_internal_transfers, settled_titles_lookup,
    )
    if plano_contas is None:
        plano_contas = load_company_chart(chart_directory(), company)
    if titulos_baixados is not None:
        lookup_titles = settled_titles_lookup(titulos_baixados, plano_contas, bank_accounts)
    if plano_contas:
        learned_lookup = ChartNameMatcher(learned, bank_accounts, plano_contas).find
        chart_lookup = learned_lookup
        if titulos_baixados is not None:
            def chart_lookup(bank, nature, history, date):
                return lookup_titles(bank, nature, history, date) or learned_lookup(bank, nature, history, date)
        transfer_lookup = partial(match_internal_transfers, bank_accounts=bank_accounts, chart=plano_contas)
    workbook, summary = engine.classificar_planilha_final(
        content, filename, learned, bank_accounts,
        empresa_classificacao=slug(company), coluna_substituir=options.get('coluna_substituir', ''),
        valores_substituiveis=options.get('valores_substituiveis', []),
        modo_consolidado_eletro_forte=bool(options.get('modo_consolidado', company in {242, 1408})),
        decidir_pendencias=partial(classification_decision.classify_groups, key) if key else None,
        aplicar_decisoes=os.getenv('GEMINI_DECISION_AUTO_APPLY') == '1',
        periodo_decisao=period, localizar_conta_plano=chart_lookup,
        localizar_transferencias=transfer_lookup,
        localizar_conta_historico=history_lookup,
    )
    workbook, changed = _limit_classified_workbook_to_period(
        content, workbook, options.get('data_inicial', ''), options.get('data_final', '')
    )
    if changed is not None:
        summary = dict(summary)
        summary['automaticos'] = changed
        summary['periodo_aplicado'] = {
            'data_inicial': options.get('data_inicial', ''),
            'data_final': options.get('data_final', ''),
        }
    return workbook, summary


def classify_with_coverage(company, content, filename, options=None, *, plano_contas=None, titulos_baixados=None):
    """Acrescenta indicadores apenas à resposta web, preservando o contrato interno."""
    workbook, summary = classify(company, content, filename, options, plano_contas=plano_contas, titulos_baixados=titulos_baixados)
    resolved = resolve_classification_options(company, options)
    resolved.setdefault('modo_consolidado', int(company) in {242, 1408})
    from app.classification_coverage import coverage
    report = coverage(content, workbook, slug(company), resolved)
    return workbook, {**summary, 'cobertura': report}


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
        from app.classification_chart import remember_chart_approval

        for record in new_records:
            remember_chart_approval(record, normalize_unstructured=int(company) == 266)
        con = _db()
        try:
            con.execute('BEGIN IMMEDIATE')
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
        con.execute('BEGIN IMMEDIATE')
        for table in ('classification_records', 'classification_imports'):
            con.execute(f'DELETE FROM {table} WHERE company=?', (company,))
        if persistence.table_exists(con, 'patterns'):
            con.execute('DELETE FROM patterns WHERE company=?', (company,))
        con.commit()
    finally:
        con.close()

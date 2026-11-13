"""Exclusão exata de um banco/período, preservando os demais aprendizados."""
import hashlib
import json
from app import classification_service as base, persistence
from app.migration_services import accounts


class StaleSelection(ValueError):
    pass


def _bank(company, bank):
    if company == 242 and bank == 'banco_brasil':
        return 'bb'
    if company == 1408 and bank == 'itau':
        return 'itau_512'
    return bank


def _rows(con, company):
    modern = [(row['id'], json.loads(row['payload'])) for row in con.execute(
        'SELECT id,payload FROM classification_records WHERE company=? ORDER BY id', (company,))]
    legacy = []
    if persistence.table_exists(con, 'patterns'):
        legacy = [dict(row) for row in con.execute('SELECT * FROM patterns WHERE company=? ORDER BY bank,signature,nature,counterpart,period', (company,))]
    return modern, legacy


def slices(company):
    con = base._db()
    try:
        modern, legacy = _rows(con, company)
        found = {}
        for _, record in modern:
            found.setdefault(record['banco'], set()).update(record.get('periodos', []))
        for record in legacy:
            found.setdefault(_bank(company, record['bank']), set()).add(record['period'])
        return {'banks': [{'bank': bank, 'account': accounts(company).get(bank, ''),
                           'periods': sorted(periods, reverse=True)} for bank, periods in sorted(found.items()) if periods]}
    finally:
        con.close()


def _selection(con, company, bank, period):
    if not isinstance(bank, str) or not isinstance(period, str) or not bank or not period:
        raise ValueError('Selecione o banco e o período salvo na base.')
    modern, legacy = _rows(con, company)
    modern = [(identity, record) for identity, record in modern if record['banco'] == bank and period in record.get('periodos', [])]
    legacy = [record for record in legacy if _bank(company, record['bank']) == bank and record['period'] == period]
    if not modern and not legacy:
        raise ValueError('Não há registros para este banco e período.')
    token = hashlib.sha256(json.dumps([company, bank, period, modern, legacy], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    retained = sum(bool(set(record['periodos']) - {period}) for _, record in modern)
    return modern, legacy, {'company': company, 'bank': bank, 'period': period,
        'affected': len(modern) + len(legacy), 'retained': retained,
        'removed': len(modern) + len(legacy) - retained, 'token': token}


def preview(company, bank, period):
    con = base._db()
    try:
        con.execute('BEGIN')
        return _selection(con, company, bank, period)[2]
    finally:
        con.close()


def delete(company, bank, period, token):
    con = base._db()
    try:
        con.execute('BEGIN IMMEDIATE')
        modern, legacy, result = _selection(con, company, bank, period)
        if not token or token != result['token']:
            raise StaleSelection('A base mudou desde a prévia. Confira novamente antes de excluir.')
        for identity, record in modern:
            record['periodos'] = [p for p in record['periodos'] if p != period]
            if record['periodos']:
                con.execute('UPDATE classification_records SET payload=? WHERE company=? AND id=?',
                            (json.dumps(record, ensure_ascii=False), company, identity))
            else:
                con.execute('DELETE FROM classification_records WHERE company=? AND id=?', (company, identity))
        for record in legacy:
            con.execute('DELETE FROM patterns WHERE company=? AND bank=? AND signature=? AND nature=? AND counterpart=? AND period=?',
                        (company, record['bank'], record['signature'], record['nature'], record['counterpart'], period))
        # O histórico de importações não possui escopo por banco/período.
        # Liberar sua deduplicação permite reensinar o recorte removido; _save
        # continua mesclando os padrões restantes sem duplicá-los.
        con.execute('DELETE FROM classification_imports WHERE company=?', (company,))
        con.commit()
        return {'ok': True, **{key: value for key, value in result.items() if key != 'token'}}
    finally:
        con.close()

import hashlib
import json
import sqlite3
from copy import deepcopy
from app import classification_service as base, persistence


def row(signature='acme', period='2026-08', occurrences=1):
    return {'banco':'itau', 'assinatura':signature, 'debito':'166', 'credito':'508',
            'periodos':[period], 'ocorrencias':occurrences, 'exemplo_historico':period}


def test_bulk_save_coalesces_duplicates_in_and_across_batches_and_keeps_company_scope(monkeypatch):
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE classification_records(company INTEGER,id TEXT,payload TEXT,PRIMARY KEY(company,id))')
    base._save(con, 3, [row('0','2026-06',10)])
    identity=con.execute('SELECT id FROM classification_records').fetchone()['id']
    foreign={'periodos':['2025-01'],'ocorrencias':100}
    con.execute('INSERT INTO classification_records VALUES(?,?,?)',(88,identity,json.dumps(foreign)))
    incoming=[row('0','2026-07',2),row('0','2026-08',5)] + [row(str(i)) for i in range(1,1001)] + [row('0','2026-09',3)]
    unchanged=deepcopy(incoming)
    statements=[];con.set_trace_callback(statements.append)
    # Exercise the production batch size while using a real, isolated SQL store.
    monkeypatch.setattr(persistence,'is_postgres',lambda candidate: candidate is con)
    base._save(con,3,incoming)
    assert len([q for q in statements if q.startswith('SELECT')])==2
    assert len([q for q in statements if q.startswith('INSERT')])==2
    assert con.execute('SELECT COUNT(*) FROM classification_records WHERE company=3').fetchone()[0]==1001
    merged=json.loads(con.execute('SELECT payload FROM classification_records WHERE company=3 AND id=?',(identity,)).fetchone()[0])
    assert merged['periodos']==['2026-06','2026-07','2026-08','2026-09']
    assert merged['ocorrencias']==10
    assert merged['exemplo_historico']=='2026-09'
    assert json.loads(con.execute('SELECT payload FROM classification_records WHERE company=88').fetchone()[0])==foreign
    assert incoming==unchanged
    con.close()


def test_parse_holds_no_writer_lock_and_duplicate_file_is_not_parsed_again(monkeypatch):
    content=b'synthetic-workbook'
    parsed=[]
    def parse(*args):
        other=sqlite3.connect(base.DB_PATH, timeout=.1)
        try:
            other.execute('BEGIN IMMEDIATE')
            parsed.append(True)
        finally:other.close()
        return [row()]
    monkeypatch.setattr(base.engine,'importar_arquivos_classificados',parse)
    assert base.learn(3,content,'book.xlsx')==1
    assert base.learn(3,content,'book.xlsx')==0
    assert parsed==[True]


def test_duplicate_rechecked_after_parsing(monkeypatch):
    content=b'concurrent-file'
    digest=hashlib.sha256(content).hexdigest()
    def parse(*args):
        # Represent another worker completing the same import during parsing.
        con=base._db()
        try:
            con.execute('INSERT INTO classification_imports VALUES(?,?)',(3,digest));con.commit()
        finally:con.close()
        return [row()]
    monkeypatch.setattr(base.engine,'importar_arquivos_classificados',parse)
    assert base.learn(3,content,'book.xlsx')==0
    assert base.records(3)==[]


def test_failed_later_batch_rolls_back_entire_import():
    import pytest
    con=base._db()
    con.execute("""CREATE TRIGGER reject_test_record BEFORE INSERT ON classification_records
      WHEN json_extract(NEW.payload,'$.assinatura')='reject'
      BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
    con.commit();con.close()
    payload=json.dumps({'company':3,'records':[row(str(i)) for i in range(250)]+[row('reject')]}).encode()
    with pytest.raises(sqlite3.IntegrityError,match='synthetic failure'):
        base.learn(3,payload,'rollback.json')
    con=base._db()
    try:
        assert con.execute('SELECT COUNT(*) FROM classification_records').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM classification_imports').fetchone()[0]==0
    finally:con.close()

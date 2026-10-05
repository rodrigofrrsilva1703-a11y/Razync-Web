"""Encrypted A1 storage; original validation/crypto, server-only master key."""
import json
import os
from app.classification_service import _db
from razync.certificado_digital import validar_certificado, _cifrar, _cnpj_valido

def connection():
    con = _db()
    con.execute('CREATE TABLE IF NOT EXISTS certificates(company INTEGER PRIMARY KEY, metadata TEXT NOT NULL, encrypted TEXT NOT NULL)')
    return con

def get(company):
    con = connection()
    try:
        row = con.execute('SELECT metadata FROM certificates WHERE company=?', (company,)).fetchone()
        return json.loads(row['metadata']) if row else None
    finally:
        con.close()

def save(company, content, password, cnpj=''):
    import re
    secret = os.getenv('CERTIFICATES_MASTER_KEY', '')
    if not secret:
        raise ValueError('Configure CERTIFICATES_MASTER_KEY somente no Railway para armazenar A1 com criptografia.')
    metadata = validar_certificado(content, password)
    if not metadata['cnpj']:
        cnpj = re.sub(r'\D', '', cnpj)
        if not _cnpj_valido(cnpj):
            raise ValueError('Informe um CNPJ válido para este certificado.')
        metadata['cnpj'] = cnpj
    con = connection()
    try:
        con.execute('INSERT OR REPLACE INTO certificates VALUES(?,?,?)', (company, json.dumps(metadata), _cifrar(content, password, secret)))
        con.commit()
    finally:
        con.close()
    return metadata

def delete(company):
    con = connection()
    try:
        con.execute('DELETE FROM certificates WHERE company=?', (company,))
        con.commit()
    finally:
        con.close()

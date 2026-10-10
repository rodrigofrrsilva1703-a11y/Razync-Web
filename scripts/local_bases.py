"""Transferência explícita Railway -> computador; nunca altera a origem."""
from datetime import datetime
import html
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import urllib.error
import urllib.request

SOURCE = 'https://razync-api-production.up.railway.app'


def copy_bases(private, key):
    from app import classification_service as base
    from app.migration_services import SLUGS
    from concurrent.futures import ThreadPoolExecutor
    if not key.strip():
        raise ValueError('Informe a chave administrativa do Railway.')

    def fetch(code):
        request = urllib.request.Request(
            f'{SOURCE}/api/v1/base-inteligente/{code}/exportar',
            headers={'Authorization': 'Bearer ' + key.strip()})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise ValueError('A chave administrativa do Railway não foi aceita.') from None
            raise ValueError('Não foi possível baixar uma base. O banco local foi preservado.') from None
        if not isinstance(payload, dict) or payload.get('company') != code or not isinstance(payload.get('records'), list):
            raise ValueError('Formato de backup inesperado. O banco local foi preservado.')
        return code, payload

    # Baixar tudo antes de gravar; a senha não é persistida nem incluída em logs.
    with ThreadPoolExecutor(max_workers=4) as pool:
        exported = list(pool.map(fetch, sorted(SLUGS)))
    folder = private / 'backups' / datetime.now().strftime('railway-%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(base.DB_PATH) as source, sqlite3.connect(folder / 'antes-importacao.db') as target:
        source.backup(target)
    groups = 0
    total = 0
    for code, payload in exported:
        if not payload['records']:
            continue
        content = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        (folder / f'base-{code}.json').write_bytes(content)
        base.learn(code, content, f'base-{code}.json')
        groups += 1
        total += len(payload['records'])
    return groups, total


def register(app, private):
    from fastapi import Form, HTTPException, Request
    from fastapi.concurrency import run_in_threadpool
    from fastapi.responses import HTMLResponse
    nonce = secrets.token_urlsafe(32)
    hosts = {'127.0.0.1:8000', 'localhost:8000'}
    origins = {'http://127.0.0.1:8000', 'http://localhost:8000'}

    def verify(request):
        if request.headers.get('host') not in hosts:
            raise HTTPException(403, 'A transferência só pode ser aberta no computador local.')

    def page(message=''):
        return HTMLResponse('''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Transferir Base Inteligente</title>
<style>body{font:16px system-ui;background:#f4f7fc;color:#263e58;margin:0;padding:24px}main{max-width:650px;margin:40px auto;background:white;padding:28px;border-radius:18px}label,input,button{display:block}input{box-sizing:border-box;width:100%;padding:14px;margin:10px 0 20px;border:1px solid #bbc9df;border-radius:10px;font-size:16px}button{padding:14px 22px;background:#2853a0;color:white;border:0;border-radius:10px;font-size:16px}p{line-height:1.6}a{color:#2853a0}.result{font-weight:600}</style>
<main><h1>Trazer a Base Inteligente</h1><p>Copie as bases atuais do Railway para este computador. O servidor original não será alterado. Uma cópia de segurança local será criada antes da importação.</p>
<p>Use a chave administrativa que você já utiliza no site publicado. Ela será enviada somente ao seu servidor local e ao próprio Railway para autorizar a leitura. Não será salva na configuração.</p>
<p class="result">''' + html.escape(message) + '''</p>
<form method="post" action="/local/bases" onsubmit="this.querySelector('button').disabled=true;this.querySelector('button').textContent='Copiando bases, aguarde…'">
<input type="hidden" name="csrf" value="''' + nonce + '''">
<label for="key">Chave administrativa do Railway</label><input id="key" name="chave" type="password" required autocomplete="off">
<button>Copiar bases atuais</button></form><p>Após a cópia, continue usando “Aprender com arquivos revisados” na Base Inteligente. Os novos padrões serão salvos em seu banco local.</p><a href="/">Voltar ao Razync local</a></main></html>''',
            headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"})

    @app.get('/local/bases', include_in_schema=False)
    def form(request: Request):
        verify(request)
        return page()

    @app.post('/local/bases', include_in_schema=False)
    async def transfer(request: Request, chave: str = Form(...), csrf: str = Form(...)):
        verify(request)
        if request.headers.get('origin') not in origins or not hmac.compare_digest(csrf, nonce):
            raise HTTPException(403, 'Abra a página de transferência pelo endereço local.')
        try:
            groups, total = await run_in_threadpool(copy_bases, private, chave)
            return page(f'Concluído: {total} padrões copiados em {groups} empresas. Atualize o Razync local.')
        except (ValueError, OSError):
            return page('Não foi possível concluir a cópia. Confira a chave administrativa e a conexão. As bases existentes não foram apagadas.')

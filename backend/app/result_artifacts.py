"""Resultados temporários em memória, sem disco nem armazenamento dos uploads.

O orçamento limita apenas o cache; relatórios maiores continuam disponíveis
pelo caminho normal, sem limite novo de tamanho ou quantidade de arquivos.
"""
import secrets
import threading
import time
from collections import OrderedDict
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.report_helpers import _download, _excel_report, _preview_records

TTL_SECONDS = 900
MAX_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 16
_guard = threading.RLock()
_items = OrderedDict()
_bytes = 0
router = APIRouter(prefix='/api/v1/resultados')

def _prune():
    global _bytes
    now = time.monotonic()
    for token, item in list(_items.items()):
        if item['expires'] <= now:
            _bytes -= len(_items.pop(token)['data'])

def store(data, filename):
    global _bytes
    if len(data) > MAX_BYTES:
        return None
    with _guard:
        _prune()
        while _items and (_bytes + len(data) > MAX_BYTES or len(_items) >= MAX_ITEMS):
            _, old = _items.popitem(last=False)
            _bytes -= len(old['data'])
        token = secrets.token_urlsafe(32)
        _items[token] = {'data':data, 'filename':filename, 'expires':time.monotonic()+TTL_SECONDS}
        _bytes += len(data)
        return token

def retrieve(token):
    with _guard:
        _prune()
        item = _items.get(token)
        if item is not None:
            _items.move_to_end(token)
            return item['data'], item['filename']
    raise HTTPException(404, 'Resultado temporário expirou. Refaça o download pela conferência.')

@router.get('/{token}')
def download_result(token: str):
    data, filename = retrieve(token)
    response = _download(data, filename)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

def workbook_response(data, filename, inline=False):
    if inline:
        from app.migration_routes import workbook_preview
        # Se o cache não comportar este relatório, usa a resposta binária original.
        if len(data) <= MAX_BYTES:
            preview = {'sheets':workbook_preview(data), 'diagnostics':[]}
            token = store(data, filename)
            if token:
                return JSONResponse({'preview':preview, 'report_token':token},
                    media_type='application/vnd.razync.preview+json',
                    headers={'Cache-Control':'no-store'})
    return _download(data, filename)

def reconciliation_response(summary, rows, sheets, filename, reuse=False):
    result = {'summary':summary, 'rows':rows}
    # Expõe os movimentos do próprio upload para auditoria da leitura na tela.
    # A conferência diária e o Excel continuam usando os mesmos dados.
    movements = []
    labels = list(dict.fromkeys(str(row.get('BANCO') or '') for row in rows))
    for name, frame in sheets.items():
        if 'Extrato analis' not in str(name) or frame is None or frame.empty:
            continue
        if not {'DATA', 'VALOR', 'HISTÓRICO'}.issubset(frame.columns):
            continue
        prefix = str(name).split(' - ', 1)[0] if ' - ' in str(name) else ''
        bank_label = next((label for label in labels if label and label.startswith(prefix)), prefix) if prefix else ''
        for row in _preview_records(frame):
            movements.append({'BANCO':bank_label or str(row.get('DESCRIÇÃO') or ''),
                              'DATA':row['DATA'], 'VALOR':row['VALOR'], 'HISTÓRICO':row['HISTÓRICO']})
    if movements:
        result['statement_movements'] = movements
    if reuse:
        try:
            token = store(_excel_report(sheets), filename)
            if token:
                result['report_token'] = token
        except Exception as exc:
            # Reuse is optional: export failure must not remove a valid preview.
            import logging
            logging.getLogger(__name__).warning('Resultado não armazenado: %s', type(exc).__name__)
    return result

"""Fila temporária do organizador: uma execução pesada por vez, sem uploads em disco."""
import contextvars
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

router = APIRouter(prefix='/api/v1/organizador')
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='organizador')
_guard = threading.RLock()
_jobs = {}
_current = contextvars.ContextVar('organizer_job', default=None)
TTL = 900
MAX_PENDING = 2
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_RESULT_BYTES = 64 * 1024 * 1024


class Cancelled(Exception):
    pass


def progress(index=None, total=None):
    job = _current.get()
    if job is None:
        return
    with _guard:
        if job['cancelled']:
            raise Cancelled()
        if index is not None:
            job.update(current=index, total=total)


def _prune():
    now = time.monotonic()
    for token, job in list(_jobs.items()):
        if job['state'] not in {'queued', 'processing'} and job['finished'] + TTL <= now:
            del _jobs[token]
    done = [token for token, job in _jobs.items() if job['state'] not in {'queued', 'processing'}]
    for token in done[:-8]:
        del _jobs[token]


def submit(work, size, count):
    with _guard:
        _prune()
        pending = [job for job in _jobs.values() if job['state'] in {'queued', 'processing'}]
        if len(pending) >= MAX_PENDING:
            raise HTTPException(429, 'O organizador está ocupado. Aguarde o lote atual terminar antes de enviar outro.')
        if size > MAX_INPUT_BYTES or sum(job['size'] for job in pending) + size > MAX_INPUT_BYTES:
            raise HTTPException(413, 'Este lote excede a memória disponível. Divida os anexos em lotes menores.')
        token = secrets.token_urlsafe(32)
        job = dict(state='queued', cancelled=False, size=size, current=0, total=count)
        _jobs[token] = job
        job['future'] = _executor.submit(_run, job, work)
    return JSONResponse({'job_token':token}, status_code=202, headers={'Cache-Control':'no-store'})


def _run(job, work):
    handle = _current.set(job)
    try:
        progress()
        with _guard:
            job['state'] = 'processing'
        data, filename = work()
        progress()
        from app.result_artifacts import workbook_response
        response = workbook_response(data, filename, True)
        if isinstance(response, JSONResponse):
            body, headers = response.body, dict(response.headers)
        else:
            body = data
            headers = {'content-type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       'content-disposition':f'attachment; filename="{filename}"'}
        with _guard:
            progress()
            # Não acumular relatórios antigos de lotes grandes na memória.
            for token, old in list(_jobs.items()):
                if old is not job and old['state'] == 'ready' and sum(len(j.get('body', b'')) for j in _jobs.values()) + len(body) > MAX_RESULT_BYTES:
                    del _jobs[token]
            job.update(state='ready', body=body, headers=headers)
    except Cancelled:
        with _guard:
            job['state'] = 'cancelled'
    except Exception as exc:
        with _guard:
            job.update(state='error', error=str(exc))
    finally:
        with _guard:
            job['finished'] = time.monotonic()
            job['size'] = 0
        _current.reset(handle)


def _get(token):
    _prune()
    job = _jobs.get(token)
    if job is None:
        raise HTTPException(404, 'O processamento expirou ou o servidor reiniciou. Gere o lote novamente.')
    return job


@router.get('/{token}')
def status(token: str):
    with _guard:
        job = _get(token)
        return JSONResponse({key:job[key] for key in ('state','current','total','error') if key in job},
                            headers={'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'})


@router.get('/{token}/resultado')
def result(token: str):
    with _guard:
        job = _get(token)
        if job['state'] != 'ready':
            raise HTTPException(409, 'O lote ainda não está pronto.')
        return Response(job['body'], headers={**job['headers'], 'Cache-Control':'private, no-store', 'Referrer-Policy':'no-referrer'})


@router.delete('/{token}')
def cancel(token: str):
    with _guard:
        job = _get(token)
        job['cancelled'] = True
        # A fila mantém a reserva até o worker liberar a referência aos uploads.
    return {'cancelled':True}

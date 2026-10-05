from __future__ import annotations
import io
import json
import os
import hmac
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from app import classification_service as base
from app import migration_services as services

router = APIRouter(prefix='/api/v1')

@router.post('/workflow/{company_code}/preview')
async def workflow_preview(company_code: int, roles_json: str = Form(...), options_json: str = Form('{}'), files: list[UploadFile] = File(...)):
    try:
        from openpyxl import load_workbook
        from openpyxl.utils.datetime import from_excel
        import datetime
        names, options = json.loads(roles_json), json.loads(options_json)
        if not isinstance(names, list) or len(names) != len(files) or not isinstance(options, dict):
            raise ValueError('Configuração dos arquivos inválida.')
        roles = {}
        for name, upload in zip(names, files):
            roles.setdefault(str(name), []).append((upload.filename or 'arquivo.xlsx', await upload.read()))
        content, filename = await run_in_threadpool(services.workflow, company_code, roles, options)
        book = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        sheets = []
        try:
            for sheet in book:
                if sheet.title.casefold() == 'principal':
                    continue
                rows = list(sheet.iter_rows(values_only=True))
                header = next((i for i, row in enumerate(rows) if any(str(c or '').strip().upper() == 'HISTÓRICO' for c in row)), None)
                if header is None:
                    continue
                columns = [str(c or '') for c in rows[header]]
                values = [r for r in rows[header+1:] if any(c is not None for c in r)]
                index = next((i for i,c in enumerate(columns) if c.strip().upper() == 'VALOR'), None)
                amounts = [float(r[index]) for r in values if index is not None and isinstance(r[index], (int,float))]
                date_index = next((i for i,c in enumerate(columns) if c.strip().upper() == 'DATA'), None)
                display = []
                for row in values[:500]:
                    formatted = []
                    for i,c in enumerate(row):
                        if i == date_index and isinstance(c,(int,float)):
                            c = from_excel(c, book.epoch)
                        formatted.append(c.strftime('%d/%m/%Y') if isinstance(c,(datetime.datetime,datetime.date)) else c)
                    display.append(formatted)
                sheets.append({'name':sheet.title,'count':len(values),'columns':columns,'rows':display,
                    'entradas':round(sum(v for v in amounts if v > 0),2),'saidas':round(-sum(v for v in amounts if v < 0),2)})
        finally:
            book.close()
        tables = await run_in_threadpool(services.diagnostics, company_code, roles, options)
        diagnostics = [{'name':name,'columns':list(frame.columns),'rows':json.loads(frame.head(500).to_json(orient='values',date_format='iso',force_ascii=False)), 'count':len(frame)} for name,frame in tables.items()]
        return {'filename':filename,'sheets':sheets,'diagnostics':diagnostics}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

def download(content, filename, summary=None, mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    if summary is not None:
        headers['X-Razync-Summary'] = json.dumps(summary, ensure_ascii=True)
    return StreamingResponse(io.BytesIO(content), media_type=mime, headers=headers)

def require_admin(authorization: str = Header('')):
    expected = os.getenv('RAZYNC_ACCESS_TOKEN') or os.getenv('CLASSIFICATION_ADMIN_PASSWORD')
    if not expected:
        raise HTTPException(503, 'Configure RAZYNC_ACCESS_TOKEN no Railway para gerenciar bases e certificados.')
    if not hmac.compare_digest(authorization, f'Bearer {expected}'):
        raise HTTPException(401, 'Informe a chave de acesso administrativa.')

@router.get('/migration-status')
def migration_status():
    manifest = Path(__file__).resolve().parents[1] / 'resources' / 'engine_manifest.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    return {'reference': data['reference_repository'], 'extracted_functions': len(data['functions']),
            'validation': 'pending_real_files', 'certificates_configured': bool(os.getenv('CERTIFICATES_MASTER_KEY') and os.getenv('RAZYNC_ACCESS_TOKEN')),
            'original_base_import_configured': bool(os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_SERVICE_KEY'))}

@router.post('/workflow/{company_code}/reports')
async def report_package(company_code: int, roles_json: str = Form(...), options_json: str = Form('{}'), files: list[UploadFile] = File(...)):
    if services.CAPABILITIES.get(company_code, {}).get('workflow') != 'advanced':
        raise HTTPException(404, 'Empresa sem fluxo de arquivos complementares.')
    try:
        names, options = json.loads(roles_json), json.loads(options_json)
        if not isinstance(names, list) or len(names) != len(files) or not isinstance(options, dict):
            raise ValueError('Configuração dos arquivos inválida.')
        roles = {}
        for name, upload in zip(names, files):
            roles.setdefault(str(name), []).append((upload.filename or 'arquivo.xlsx', await upload.read()))
        reports = await run_in_threadpool(services.workflow_reports, company_code, roles, options)
        return download(services.package(reports), f'RAZYNC_{company_code}_RELATORIOS.zip', {'arquivos': list(reports)}, 'application/zip')
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post('/francesinhas/{company_code}')
async def standalone_francesinhas(company_code: int, files: list[UploadFile] = File(...)):
    if company_code not in {242, 1408}:
        raise HTTPException(404, 'Francesinhas disponíveis para Eletro Forte 242 e 1408.')
    try:
        uploads = [(u.filename or 'francesinhas.zip', await u.read()) for u in files]
        book, summary = await run_in_threadpool(services.francesinhas, company_code, uploads)
        return download(book, f'ELETRO_FORTE_{company_code}_FRANCESINHAS.xlsx', summary)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

@router.get('/base-inteligente/{company_code}/exportar', dependencies=[Depends(require_admin)])
def export_base(company_code: int):
    content = json.dumps({'version': 1, 'company': company_code, 'records': base.records(company_code)}, ensure_ascii=False).encode()
    return download(content, f'RAZYNC_{company_code}_BASE.json', mime='application/json')

@router.post('/base-inteligente/{company_code}/importar-original', dependencies=[Depends(require_admin)])
def import_base(company_code: int):
    try:
        return {'learned': base.import_original_online(company_code), **base.status(company_code)}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

@router.delete('/base-inteligente/{company_code}', dependencies=[Depends(require_admin)])
def clear_base(company_code: int):
    base.clear(company_code)
    return {'ok': True}

@router.post('/base-inteligente/{company_code}/pendencias')
async def review_pending(company_code: int, file: UploadFile = File(...)):
    try:
        return {'pendencias': base.pending(company_code, await file.read())}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post('/base-inteligente/{company_code}/revisar')
async def apply_review(company_code: int, file: UploadFile = File(...), revisoes_json: str = Form(...), aprender: bool = Form(False)):
    try:
        revisions = json.loads(revisoes_json)
        if not isinstance(revisions, list):
            raise ValueError('Revisões inválidas.')
        book, summary = base.review(company_code, await file.read(), file.filename or 'modelo.xlsx', revisions, aprender)
        return download(book, f'RAZYNC_{company_code}_REVISADO.xlsx', summary)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

@router.get('/connector/download')
def download_connector():
    source = Path(__file__).resolve().parents[1] / 'legacy' / 'connector_windows'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in source.rglob('*'):
            if path.is_file() and path.suffix.lower() in {'.py', '.ps1', '.bat', '.js', '.json'}:
                archive.write(path, path.relative_to(source).as_posix())
        archive.writestr('INSTALAR_RAZYNC_WEB.bat', '@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"\r\npause\r\n')
        archive.writestr('LEIA-ME.txt', 'Extraia todos os arquivos e execute INSTALAR_RAZYNC_WEB.bat.\nAbra o painel fiscal no Razync-Web e informe o codigo de pareamento.\n')
    return download(buffer.getvalue(), 'RAZYNC_WEB_CONECTOR_WINDOWS.zip', mime='application/zip')

@router.post('/modelo-dominio-txt')
async def export_txt(file: UploadFile = File(...)):
    try:
        from app import engine
        import pandas as pd
        def convert(content):
            book = pd.ExcelFile(io.BytesIO(content))
            frames = []
            for name in book.sheet_names:
                if name.casefold() == 'principal' or 'retir' in name.casefold():
                    continue
                raw = pd.read_excel(book, sheet_name=name, header=None)
                header = next((i for i in range(min(30,len(raw))) if {'DATA','VALOR','HISTÓRICO'} <= {str(v or '').strip().upper() for v in raw.iloc[i]}), None)
                if header is None:
                    continue
                frame = raw.iloc[header+1:].copy()
                frame.columns = [str(v or '').strip().upper() for v in raw.iloc[header]]
                if all(c in frame for c in services.COLUNAS):
                    frame = frame[services.COLUNAS].dropna(subset=['DATA','VALOR'])
                    frame['DATA'] = frame['DATA'].map(lambda v: pd.to_datetime(v,unit='D',origin='1899-12-30') if isinstance(v,(int,float)) else v)
                    frame['DATA'] = pd.to_datetime(frame['DATA'],dayfirst=True,errors='coerce').dt.strftime('%d/%m/%Y')
                    frames.append(frame)
            if not frames:
                raise ValueError('Nenhuma aba do Modelo Domínio encontrada.')
            return engine.gerar_txt_dominio(pd.concat(frames,ignore_index=True)).encode('utf-8')
        content = await run_in_threadpool(convert, await file.read())
        return download(content, 'RAZYNC_MODELO_DOMINIO.txt', mime='text/plain; charset=utf-8')
    except Exception as exc:
        raise HTTPException(422,str(exc)) from exc

@router.get('/certificates/{company_code}', dependencies=[Depends(require_admin)])
def certificate_metadata(company_code: int):
    from app.certificates_service import get
    return {'certificate': get(company_code)}

@router.post('/certificates/{company_code}', dependencies=[Depends(require_admin)])
async def save_certificate(company_code: int, file: UploadFile = File(...), password: str = Form(...), cnpj: str = Form('')):
    try:
        from app.certificates_service import save
        return {'certificate': save(company_code, await file.read(), password, cnpj)}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

@router.delete('/certificates/{company_code}', dependencies=[Depends(require_admin)])
def delete_certificate(company_code: int):
    from app.certificates_service import delete
    delete(company_code)
    return {'ok': True}

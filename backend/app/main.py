from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy"
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

from razync.company_catalog import EMPRESAS
from app.custom_adapters import processar_custom
from app.excel import gerar_modelo_abas
from app.registry import CAPABILITIES, COMMON_TOOLS
from app.advanced import workflow_modelo, processar_itau_generico, processar_daycoval_generico
from app.conferencia import ler_modelo_excel, conciliar
from app.classification_service import learn as base_learn, status as base_status, classify as base_classify
from app.migration_services import workflow as migrated_workflow, statement as migrated_statement
from app.global_tools import processar_arquivo, processar_razao, conciliar_razao
from app.tasks import dashboard as task_dashboard, set_company_status, create_task, update_task, delete_task

app = FastAPI(title="Razync Web API", version="0.4.0")

origins = [
    "https://rodrigofrrsilva1703-a11y.github.io",
    "http://localhost:5173",
    "http://localhost:8000",
]
extra = os.getenv("RAZYNC_FRONTEND_ORIGINS", "")
origins.extend([x.strip() for x in extra.split(",") if x.strip()])
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Razync-Summary"],
)


def _excel_report(sheets: dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in sheets.items():
            frame = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
            frame.to_excel(writer, sheet_name=str(name)[:31], index=False)
    return out.getvalue()


def _download(data: bytes, filename: str):
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "razync-web-api",
        "version": app.version,
        "persistent_data": str(os.getenv("RAZYNC_DB_PATH", "/data/razync.db")),
    }


@app.get("/api/v1/companies")
def companies():
    result = []
    for item in EMPRESAS:
        row = dict(item)
        cap = dict(CAPABILITIES.get(int(item["codigo"]), {"status": "fiscal_only", "tools": ["conferencia_fiscal", "conferencia_impostos"]}))
        if cap.get("status") == "api_ready":
            cap["tools"] = COMMON_TOOLS
        row["capabilities"] = cap
        result.append(row)
    return result


@app.get("/api/v1/companies/{company_code}")
def company(company_code: int):
    item = next((x for x in EMPRESAS if int(x["codigo"]) == company_code), None)
    if not item:
        raise HTTPException(status_code=404, detail="Empresa não cadastrada.")
    row = dict(item)
    cap = dict(CAPABILITIES.get(company_code, {"status": "fiscal_only", "tools": ["conferencia_fiscal", "conferencia_impostos"]}))
    if cap.get("status") == "api_ready":
        cap["tools"] = COMMON_TOOLS
    row["capabilities"] = cap
    return row


def _process_modular(company_code: int, bank: str, content: bytes, filename: str) -> pd.DataFrame:
    bank = (bank or "").strip().casefold()
    name = (filename or "").lower()

    if company_code in {47, 154, 912, 964, 1532}:
        return migrated_statement(company_code, bank, content, filename)

    if company_code == 88:
        from razync.hw_88 import processar_extrato_hw88
        return processar_extrato_hw88(content)

    if company_code == 625:
        from razync.valean_625 import processar_extrato_625
        return processar_extrato_625(content, bank)

    if company_code == 626:
        from razync.valean_626 import processar_extrato_626
        return processar_extrato_626(content, bank)

    if company_code == 841:
        from razync.lucrativite_841 import processar_extrato_inter_841, processar_extrato_inter_pdf_841
        return processar_extrato_inter_pdf_841(content) if name.endswith(".pdf") else processar_extrato_inter_841(content)

    if company_code == 969:
        from razync.engekraft_969 import processar_extrato_engekraft_969
        return processar_extrato_engekraft_969(content)

    if company_code == 1208:
        from razync.kairos_1208 import processar_extrato_1208
        return processar_extrato_1208(content, bank)

    if company_code == 1530:
        from razync.dias_pereira_1530 import processar_extrato_itau_xls_1530
        if not name.endswith((".xls", ".xlsx")):
            raise ValueError("A empresa 1530 espera o extrato Itaú em XLS/XLSX.")
        return processar_extrato_itau_xls_1530(content)

    raise NotImplementedError("Use o endpoint de fluxo avançado para esta empresa.")


def _process_statement(company_code: int, bank: str, content: bytes, filename: str) -> pd.DataFrame:
    return migrated_statement(company_code, bank, content, filename)


def _validated_bank(company_code: int, bank: str) -> str:
    banks = CAPABILITIES.get(company_code, {}).get('banks', {})
    if not banks:
        raise HTTPException(404, 'Empresa sem processador bancário específico.')
    bank = bank.strip().casefold()
    if not bank and len(banks) == 1:
        bank = next(iter(banks))
    if bank not in banks:
        raise HTTPException(400, 'Banco não configurado para esta empresa.')
    return bank


def _original_export(company_code, groups):
    from app import engine
    with engine.processing_context():
        if company_code in {969,1532} and len(groups) == 1:
            from razync.engekraft_969 import gerar_modelo_dominio_engekraft_969
            return gerar_modelo_dominio_engekraft_969(next(iter(groups.values())), engine.TEMPLATE.read_bytes())
        if company_code in {47,88,841,912,964,1530} and len(groups) == 1:
            return engine.gerar_excel_modelo_dominio(next(iter(groups.values())), formato_data='dd/mm/yyyy' if company_code in {47,912,964,1530,1532} else None)
        blocks = {name:{'principal':frame,'retirados':pd.DataFrame()} for name,frame in groups.items()}
        return engine.gerar_excel_nova_geracao(blocks, prefixar_historicos=company_code not in {154,1208})


def _sheet_name(bank: str) -> str:
    names = {
        "itau": "Itaú", "itau_508": "Itaú 508", "itau_509": "Itaú 509",
        "bradesco": "Bradesco", "sicredi": "Sicredi", "banco_brasil": "Banco do Brasil",
        "bb": "Banco do Brasil", "caixa": "Caixa", "inter": "Banco Inter",
        "safra": "Safra", "btg": "BTG", "santander": "Santander",
        "daycoval": "Daycoval", "fibra": "Fibra",
    }
    return names.get((bank or "").casefold(), bank or "Banco")


@app.post("/api/v1/modelo-dominio/{company_code}")
async def modelo_dominio(
    company_code: int,
    bank: str = Form(""),
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="Envie pelo menos um arquivo.")
    cap = CAPABILITIES.get(company_code, {})
    bank = _validated_bank(company_code, bank)
    if cap.get("workflow") == "advanced":
        raise HTTPException(status_code=400, detail="Esta empresa usa o fluxo avançado de múltiplos arquivos.")
    banks = cap.get("banks", {})
    if not bank and len(banks) == 1:
        bank = next(iter(banks))
    if not bank and company_code not in {88, 969, 1530}:
        raise HTTPException(status_code=400, detail="Informe o banco para esta empresa.")
    try:
        frames = []
        for upload in files:
            content = await upload.read()
            frames.append(await run_in_threadpool(_process_modular, company_code, bank, content, upload.filename or "arquivo"))
        df = pd.concat(frames, ignore_index=True).sort_values("DATA", kind="stable").reset_index(drop=True)
        workbook = await run_in_threadpool(_original_export, company_code, {_sheet_name(bank): df})
        return _download(workbook, f"RAZYNC_{company_code}_{(bank or 'BANCO').upper()}_MODELO_DOMINIO.xlsx")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/modelo-dominio/{company_code}/multi")
async def modelo_dominio_multi(
    company_code: int,
    banks_json: str = Form(...),
    files: list[UploadFile] = File(...),
):
    try:
        banks = json.loads(banks_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="banks_json inválido.") from exc
    if not isinstance(banks, list) or len(banks) != len(files):
        raise HTTPException(status_code=400, detail="Envie um banco para cada arquivo.")
    groups: dict[str, list[pd.DataFrame]] = {}
    banks = [_validated_bank(company_code, str(bank)) for bank in banks]
    try:
        for bank, upload in zip(banks, files):
            content = await upload.read()
            frame = await run_in_threadpool(_process_modular, company_code, str(bank), content, upload.filename or "arquivo")
            groups.setdefault(str(bank), []).append(frame)
        sheets = {
            _sheet_name(bank): pd.concat(frames, ignore_index=True).sort_values("DATA", kind="stable").reset_index(drop=True)
            for bank, frames in groups.items()
        }
        return _download(await run_in_threadpool(_original_export, company_code, sheets), f"RAZYNC_{company_code}_MODELO_DOMINIO.xlsx")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/workflow/{company_code}")
async def advanced_workflow(
    company_code: int,
    roles_json: str = Form(...),
    options_json: str = Form("{}"),
    files: list[UploadFile] = File(...),
):
    try:
        role_names = json.loads(roles_json)
        options = json.loads(options_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Configuração do fluxo inválida.") from exc
    if not isinstance(role_names, list) or len(role_names) != len(files):
        raise HTTPException(status_code=400, detail="Cada arquivo precisa ter uma função/role.")
    roles: dict[str, list[tuple[str, bytes]]] = {}
    for role, upload in zip(role_names, files):
        roles.setdefault(str(role), []).append((upload.filename or "arquivo", await upload.read()))
    try:
        workbook, filename = await run_in_threadpool(migrated_workflow, company_code, roles, options if isinstance(options, dict) else {})
        return _download(workbook, filename)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/base-inteligente/{company_code}/status")
def intelligent_base_status(company_code: int):
    return {"company": company_code, **base_status(company_code)}


@app.post("/api/v1/base-inteligente/{company_code}/aprender")
async def intelligent_base_learn(company_code: int, files: list[UploadFile] = File(...)):
    total = 0
    errors = []
    for upload in files:
        try:
            total += await run_in_threadpool(base_learn, company_code, await upload.read(), upload.filename or "arquivo.xlsx")
        except Exception as exc:
            errors.append(f"{upload.filename}: {exc}")
    if total == 0 and errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    return {"ok": True, "learned": total, "errors": errors, **base_status(company_code)}


@app.post("/api/v1/base-inteligente/{company_code}/classificar")
async def intelligent_base_classify(company_code: int, file: UploadFile = File(...), options_json: str = Form('{}')):
    try:
        options = json.loads(options_json)
        if not isinstance(options, dict):
            raise ValueError('Opções de classificação inválidas.')
        workbook, summary = await run_in_threadpool(base_classify, company_code, await file.read(), file.filename or "modelo.xlsx", options)
        headers = {"X-Razync-Summary": json.dumps(summary, ensure_ascii=False)}
        response = _download(workbook, f"RAZYNC_{company_code}_CLASSIFICADO.xlsx")
        response.headers.update(headers)
        return response
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/conferencia-extrato/{company_code}")
async def conferencia_extrato(
    company_code: int,
    bank: str = Form(...),
    model_file: UploadFile = File(...),
    statement_files: list[UploadFile] = File(...),
    options_json: str = Form("{}"),
):
    try:
        from app.migration_services import reconcile
        options = json.loads(options_json)
        statements = [(upload.filename or 'extrato', await upload.read()) for upload in statement_files]
        bank = _validated_bank(company_code, bank)
        resumo, sheets = await run_in_threadpool(reconcile, company_code, bank, await model_file.read(), statements, options)
        report = _excel_report(sheets)
        response = _download(report, f"RAZYNC_{company_code}_CONFERENCIA_EXTRATO.xlsx")
        response.headers["X-Razync-Summary"] = json.dumps(resumo, ensure_ascii=False)
        return response
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/conferencia-fiscal/{company_code}")
async def conferencia_fiscal(
    company_code: int,
    acumuladores: UploadFile = File(...),
    razao: UploadFile = File(...),
    filial: str = Form(""),
):
    try:
        from razync.conferencia_fiscal import processar_conferencia, gerar_relatorio_excel
        resultado = await run_in_threadpool(processar_conferencia,
            await acumuladores.read(), acumuladores.filename or "acumuladores",
            await razao.read(), razao.filename or "razao",
            filial or None,
        )
        report = await run_in_threadpool(gerar_relatorio_excel, resultado)
        resumo = resultado.get("resumo", pd.DataFrame())
        response = _download(report, f"RAZYNC_{company_code}_CONFERENCIA_FISCAL.xlsx")
        response.headers["X-Razync-Summary"] = json.dumps({
            "linhas_resumo": int(len(resumo)),
            "filial_aplicada": resultado.get("filial_aplicada", ""),
            "periodo_fiscal": str(resultado.get("periodo_fiscal", "")),
            "periodo_razao": str(resultado.get("periodo_razao", "")),
        }, ensure_ascii=False)
        return response
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/conversor-extratos")
async def conversor_extratos(files: list[UploadFile] = File(...)):
    try:
        sheets = {}
        frames = []
        for idx, upload in enumerate(files, start=1):
            df = await run_in_threadpool(processar_arquivo, await upload.read(), upload.filename or f"arquivo_{idx}")
            frames.append(df)
            nome = Path(upload.filename or f"Arquivo {idx}").stem[:24]
            sheets[f"{idx:02d} {nome}"[:31]] = df
        if not frames:
            raise ValueError("Nenhum arquivo foi processado.")
        consolidado = pd.concat(frames, ignore_index=True).sort_values("DATA", kind="stable")
        sheets = {"Consolidado": consolidado, **sheets}
        return _download(gerar_modelo_abas(sheets), "RAZYNC_CONVERSOR_EXTRATOS_MODELO_DOMINIO.xlsx")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/conciliacao-razao")
async def conciliacao_razao(
    extrato: UploadFile = File(...),
    razao: UploadFile = File(...),
):
    try:
        df_ext = await run_in_threadpool(processar_arquivo, await extrato.read(), extrato.filename or "extrato")
        df_raz = await run_in_threadpool(processar_razao, await razao.read(), razao.filename or "razao")
        diario, resumo = conciliar_razao(df_ext, df_raz)
        report = _excel_report({
            "Resumo": pd.DataFrame([resumo]),
            "Conciliação diária": diario,
            "Extrato": df_ext,
            "Razão": df_raz,
        })
        response = _download(report, "RAZYNC_CONCILIACAO_RAZAO.xlsx")
        response.headers["X-Razync-Summary"] = json.dumps(resumo, ensure_ascii=False)
        return response
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/conferencia-impostos/{company_code}")
async def conferencia_impostos(
    company_code: int,
    receita: UploadFile = File(...),
    balancete: UploadFile = File(...),
    competencia: str = Form(""),
):
    try:
        from datetime import date
        from razync.conferencia_impostos import processar_conferencia_impostos, gerar_relatorio_impostos
        resultado = await run_in_threadpool(processar_conferencia_impostos,
            await receita.read(), receita.filename or "receita",
            await balancete.read(), balancete.filename or "balancete",
        )
        empresa = next((x for x in EMPRESAS if int(x["codigo"]) == company_code), {"nome": str(company_code)})
        if competencia and re.match(r"^\d{4}-\d{2}$", competencia):
            ano, mes = map(int, competencia.split("-"))
            comp = date(ano, mes, 1)
        else:
            hoje = date.today()
            comp = hoje.replace(day=1)
        report = await run_in_threadpool(gerar_relatorio_impostos, resultado, f"{company_code} - {empresa['nome']}", comp)
        response = _download(report, f"RAZYNC_{company_code}_CONFERENCIA_IMPOSTOS.xlsx")
        response.headers["X-Razync-Summary"] = json.dumps({
            "impostos": int(len(resultado)),
            "conferem": int((resultado["SITUAÇÃO"] == "CONFERE").sum()),
            "revisar": int((resultado["SITUAÇÃO"] == "REVISAR").sum()),
        }, ensure_ascii=False)
        return response
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/impostos/{company_code}/identificar-cnpj")
async def identificar_cnpj(company_code: int, balancete: UploadFile = File(...)):
    try:
        from razync.conferencia_impostos import extrair_cnpjs
        cnpjs = await run_in_threadpool(extrair_cnpjs, await balancete.read(), balancete.filename or "balancete")
        return {"company": company_code, "cnpjs": cnpjs}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/tasks")
def tasks_get():
    return task_dashboard()


@app.post("/api/v1/tasks/company/{company_code}")
async def tasks_company(company_code: int, payload: dict):
    try:
        competencia = str(payload.get("competencia") or task_dashboard()["competencia"])
        set_company_status(str(company_code), competencia, bool(payload.get("concluida", True)))
        return task_dashboard()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/tasks/manual")
async def tasks_create(payload: dict):
    try:
        task = create_task(payload)
        return {"ok": True, "task": task}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/v1/tasks/manual/{task_id}")
async def tasks_update(task_id: str, payload: dict):
    try:
        update_task(task_id, str(payload.get("status") or "Pendente"))
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/v1/tasks/manual/{task_id}")
def tasks_delete(task_id: str):
    try:
        delete_task(task_id)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


from app.migration_routes import router as migration_router
app.include_router(migration_router)

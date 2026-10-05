from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy"
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

from razync.company_catalog import EMPRESAS
from app.custom_adapters import processar_custom
from app.excel import gerar_modelo_abas
from app.registry import CAPABILITIES

app = FastAPI(title="Razync Web API", version="0.1.0")

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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "service": "razync-web-api", "version": app.version}


@app.get("/api/v1/companies")
def companies():
    result = []
    for item in EMPRESAS:
        row = dict(item)
        row["capabilities"] = CAPABILITIES.get(int(item["codigo"]), {"status": "catalog_only"})
        result.append(row)
    return result


@app.get("/api/v1/companies/{company_code}")
def company(company_code: int):
    item = next((x for x in EMPRESAS if int(x["codigo"]) == company_code), None)
    if not item:
        raise HTTPException(status_code=404, detail="Empresa não cadastrada.")
    row = dict(item)
    row["capabilities"] = CAPABILITIES.get(company_code, {"status": "catalog_only"})
    return row


def _process_modular(company_code: int, bank: str, content: bytes, filename: str) -> pd.DataFrame:
    bank = (bank or "").strip().casefold()
    name = (filename or "").lower()

    if company_code in {47, 154, 912, 964, 1532}:
        return processar_custom(company_code, bank, content)

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
            raise ValueError("A API inicial da empresa 1530 espera o extrato Itaú em XLS/XLSX.")
        return processar_extrato_itau_xls_1530(content)

    raise NotImplementedError(
        "Esta ferramenta já foi copiada para o backend, mas ainda exige um adaptador de fluxo multi-arquivo."
    )


def _sheet_name(bank: str) -> str:
    names = {
        "itau": "Itaú",
        "bradesco": "Bradesco",
        "sicredi": "Sicredi",
        "banco_brasil": "Banco do Brasil",
        "bb": "Banco do Brasil",
        "caixa": "Caixa",
        "inter": "Banco Inter",
        "safra": "Safra",
        "btg": "BTG",
        "santander": "Santander",
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
    banks = cap.get("banks", {})
    if not bank and len(banks) == 1:
        bank = next(iter(banks))
    if not bank and company_code not in {88, 969, 1530}:
        raise HTTPException(status_code=400, detail="Informe o banco para esta empresa.")

    frames = []
    try:
        for upload in files:
            content = await upload.read()
            frames.append(_process_modular(company_code, bank, content, upload.filename or "arquivo"))
        df = pd.concat(frames, ignore_index=True).sort_values("DATA", kind="stable").reset_index(drop=True)
        workbook = gerar_modelo_abas({_sheet_name(bank): df})
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = f"RAZYNC_{company_code}_{(bank or 'BANCO').upper()}_MODELO_DOMINIO.xlsx"
    return StreamingResponse(
        io.BytesIO(workbook),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    try:
        for bank, upload in zip(banks, files):
            content = await upload.read()
            frame = _process_modular(company_code, str(bank), content, upload.filename or "arquivo")
            groups.setdefault(str(bank), []).append(frame)
        sheets = {
            _sheet_name(bank): pd.concat(frames, ignore_index=True)
            .sort_values("DATA", kind="stable")
            .reset_index(drop=True)
            for bank, frames in groups.items()
        }
        workbook = gerar_modelo_abas(sheets)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return StreamingResponse(
        io.BytesIO(workbook),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="RAZYNC_{company_code}_MODELO_DOMINIO.xlsx"'},
    )

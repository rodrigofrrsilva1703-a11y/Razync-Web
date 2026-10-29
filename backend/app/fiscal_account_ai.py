"""Análise solicitada explicitamente para uma única conta/natureza."""
import hashlib
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from app.attachments import upload_group
from app import fiscal_ai_sessions as sessions
from app.fiscal_242 import conferencia_fiscal_preview
from app.fiscal_documentos import investigar_documentos, recortar_acumulador_ia
from app import fiscal_hybrid

router = APIRouter(prefix="/api/v1/conferencia-fiscal/ia/conta")


def scope_account(report, account, tipo):
    accounts = [r for r in report["contas"] if str(r["conta"]) == account and r["tipo"] == tipo]
    if len(accounts) != 1:
        raise ValueError("A conta e o tipo selecionados não foram encontrados nesta conferência.")
    scoped = sessions._scope_report(report, accounts)
    side = "CRÉDITO" if tipo == "SAÍDAS" else "DÉBITO"
    scoped["lancamentos"] = [m for m in scoped["lancamentos"]
        if m.get("_tipo_ia") == tipo or (not m.get("_tipo_ia") and side in str(m.get("natureza", "")))]
    return scoped


def review_context(report, scope, filial, empresa_codigo):
    source = {"escopo": scope, "filial": filial, "empresa_codigo": empresa_codigo, "relatorio": report}
    return hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


@router.post("")
async def analyze_account(acumuladores: list[UploadFile] = File(...), razao: list[UploadFile] = File(...),
                          conta: str = Form(...), tipo: str = Form(...),
                          origem: str = Form("resumo"), acumulador: str = Form(""),
                          filial: str = Form(""), empresa_codigo: str = Form(""),
                          usar_ia: bool = Form(True),
                          entradas: list[UploadFile] | None = File(None), saidas: list[UploadFile] | None = File(None)):
    acumuladores = await upload_group(acumuladores)
    razao = await upload_group(razao)
    entradas = await upload_group(entradas)
    saidas = await upload_group(saidas)
    if not conta.isdigit() or tipo not in {"ENTRADAS", "SAÍDAS"} or origem not in {"resumo", "documentos"}:
        raise HTTPException(422, "Selecione uma conta, um tipo e uma origem válidos.")
    if any(value and not value.isdigit() for value in (filial, empresa_codigo, acumulador)):
        raise HTTPException(422, "Empresa, filial e acumulador devem conter apenas números.")
    if acumulador and origem != "documentos":
        raise HTTPException(422, "O recorte por acumulador exige a investigação documental.")
    if origem == "documentos" and not (entradas if tipo == "ENTRADAS" else saidas):
        raise HTTPException(422, "Anexe o acompanhamento do tipo selecionado.")
    try:
        args = (await acumuladores.read(), acumuladores.filename or "resumo.xls",
                await razao.read(), razao.filename or "razao.xls")
        preview = await run_in_threadpool(conferencia_fiscal_preview, *args,
            int(empresa_codigo) if empresa_codigo else None, filial or None, incluir_razao_completo=True)
        selected = [r for r in preview["contas"] if str(r["conta"]) == conta and r["tipo"] == tipo]
        if len(selected) != 1:
            raise ValueError("A conta e o tipo selecionados não foram encontrados nesta conferência.")
        documentary = None
        contents = [args[0], args[2]]
        if origem == "documentos":
            attachment = entradas if tipo == "ENTRADAS" else saidas
            content = (await attachment.read(), attachment.filename or "documentos.xls")
            contents.append(content[0])
            investigation = await run_in_threadpool(investigar_documentos, *args,
                content if tipo == "ENTRADAS" else None, content if tipo == "SAÍDAS" else None, filial,
                completo=True, preview=preview)
            documentary = next((r for r in investigation["contas"] if str(r["conta"]) == conta and r["tipo"] == tipo), None)
            preview = dict(preview, avisos=[*preview.get("avisos", []), *investigation.get("avisos", [])])
            if acumulador:
                if not documentary:
                    raise ValueError("Sem detalhamento documental para recortar este acumulador.")
                documentary, selected_row = recortar_acumulador_ia(documentary, selected[0], acumulador)
                selected = [selected_row]
        # Keep global record positions for the documentary R-n references.
        report = dict(preview, contas=selected)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    scope = {"conta": conta, "tipo": tipo, "acumulador": acumulador, "origem": origem}
    def blob_hash(value):
        if isinstance(value, bytes):
            return hashlib.sha256(value).hexdigest()
        if isinstance(value, (list, tuple)):
            return [blob_hash(v) for v in value]
        return str(value)
    # Raw file hashes invalidate the cache even if an unrelated report row changes.
    source_hash = json.dumps({"files": blob_hash(contents), "empresa": empresa_codigo, "filial": filial}, sort_keys=True)
    context_id = review_context(dict(report, documentary=documentary, source_hash=source_hash,
        regras=fiscal_hybrid.RULES_VERSION), scope, filial, empresa_codigo)
    try:
        result = await run_in_threadpool(fiscal_hybrid.run, report, scope, documentary,
                                        source_hash=source_hash, use_ai=usar_ia)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"analises": [result], "provedor": result["provedor"], "gratuito": True,
            "cache_reutilizado": result.get("cache_reutilizado", False), "escopo": scope,
            "contexto_revisao": context_id, "aviso": "Investigação somente de leitura; nenhuma alteração contábil foi executada."}

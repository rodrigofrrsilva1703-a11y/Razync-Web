"""Análise solicitada explicitamente para uma única conta/natureza."""
import hashlib
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from app import fiscal_ai_sessions as sessions
from app.fiscal_242 import conferencia_fiscal_preview
from app.fiscal_documentos import preparar_relatorio_pendencias_para_ia

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
async def analyze_account(acumuladores: UploadFile = File(...), razao: UploadFile = File(...),
                          conta: str = Form(...), tipo: str = Form(...),
                          origem: str = Form("resumo"), acumulador: str = Form(""),
                          filial: str = Form(""), empresa_codigo: str = Form(""),
                          entradas: UploadFile | None = File(None), saidas: UploadFile | None = File(None)):
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
        if origem == "documentos":
            attachment = entradas if tipo == "ENTRADAS" else saidas
            content = (await attachment.read(), attachment.filename or "documentos.xls")
            report = await run_in_threadpool(preparar_relatorio_pendencias_para_ia, *args,
                content if tipo == "ENTRADAS" else None, content if tipo == "SAÍDAS" else None, filial,
                conta_alvo=conta, tipo_alvo=tipo, acumulador_alvo=acumulador)
            if report["contas"]:
                report = scope_account(report, conta, tipo)
        else:
            report = await run_in_threadpool(conferencia_fiscal_preview, *args,
                int(empresa_codigo) if empresa_codigo else None, filial or None)
            report = scope_account(report, conta, tipo)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    scope = {"conta": conta, "tipo": tipo, "acumulador": acumulador, "origem": origem}
    context_id = review_context(report, scope, filial, empresa_codigo)
    if not report["contas"] or all(r["situacao"] == "CONFERE" for r in report["contas"]):
        return {"analises": [], "provedor": "local", "gratuito": True, "escopo": scope, "contexto_revisao": context_id,
                "aviso": "Não há pendências nesta seleção para enviar à IA. A igualdade dos totais não substitui a conferência dos documentos."}
    manifest = await run_in_threadpool(sessions.prepare, report)
    try:
        results = [await run_in_threadpool(sessions.process, manifest["sessao"], lot["id"]) for lot in manifest["lotes"]]
        if len(results) != 1 or len(results[0].get("analises", [])) != 1:
            raise HTTPException(502, "A análise não retornou exclusivamente a conta selecionada.")
        return dict(results[0], escopo=scope, contexto_revisao=context_id)
    finally:
        sessions.discard(manifest["sessao"])

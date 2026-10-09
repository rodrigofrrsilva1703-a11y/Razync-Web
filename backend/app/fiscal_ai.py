"""Optional Gemini explanations. Never send source files or free text to Google."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from app.fiscal_242 import conferencia_fiscal_preview

router = APIRouter(prefix="/api/v1/conferencia-fiscal/242/ia")
lock = threading.Lock()
last_request = 0.0


def sanitized(report):
    """Allowlist only qualitative facts; identity, amounts and dates stay local."""
    groups, mapping = [], {}
    valid = {"CONFERE", "CONFERE COM ALERTAS", "REVISAR", "AUSENTE NO CONTÁBIL"}
    for row in report["contas"]:
        if row["situacao"] == "CONFERE":
            continue
        if len(groups) == 60:
            break
        ident = f"G{len(groups) + 1}"
        mapping[ident] = {"conta": row["conta"], "tipo": row["tipo"]}
        groups.append({"grupo": ident,
            "situacao": row["situacao"] if row["situacao"] in valid else "REVISAR",
            "natureza": "credito" if row["tipo"] == "SAÍDAS" else "debito",
            "diferenca": "excesso" if row["diferenca"] > .01 else "falta" if row["diferenca"] < -.01 else "zero",
            "adicionais": bool(row["extras"])})
    return groups, mapping


def explain(report):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Gemini ainda não configurado. Defina GEMINI_API_KEY no Railway.")
    groups, mapping = sanitized(report)
    if not groups:
        return {"analises": [], "aviso": "Nenhuma divergência ou alerta para explicar."}
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+", model):
        raise HTTPException(503, "Revise GEMINI_MODEL no Railway.")
    global last_request
    with lock:
        if time.monotonic() - last_request < 15:
            raise HTTPException(429, "Aguarde 15 segundos antes de analisar novamente.")
        last_request = time.monotonic()
    schema = {"type":"OBJECT", "properties":{"analises":{"type":"ARRAY", "items":{
        "type":"OBJECT", "properties":{
            "grupo":{"type":"STRING", "enum":list(mapping)},
            "explicacao":{"type":"STRING"}, "verificar":{"type":"STRING"}},
        "required":["grupo","explicacao","verificar"]}}}, "required":["analises"]}
    payload = {
        "systemInstruction":{"parts":[{"text":
            "Você auxilia revisão fiscal contábil em português. Receberá somente categorias anônimas. "
            "Explique cada grupo em até duas frases e sugira uma verificação concreta. "
            "Não invente valores, datas, documentos ou lançamentos; não afirme fraude, duplicidade ou erro comprovado. "
            "A classificação é preliminar. Natureza indica a coluna analisada. Diferenca compara contábil compatível com fiscal. "
            "Adicionais indica movimentos não classificados como fiscais. Sugestões são hipóteses, nunca alteram cálculos."}]},
        "contents":[{"role":"user","parts":[{"text":json.dumps(groups, ensure_ascii=False)}]}],
        "generationConfig":{"responseMimeType":"application/json", "responseSchema":schema,
                            "temperature":0.2, "maxOutputTokens":4096}}
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode(), headers={"Content-Type":"application/json","x-goog-api-key":key})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = json.loads(response.read(150000))
        candidate = raw["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Incomplete answer")
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
        result = json.loads(text)
        output, seen = [], set()
        for item in result["analises"]:
            ident = item["grupo"]
            if ident not in mapping or ident in seen:
                raise ValueError("Unknown or repeated group")
            if not all(isinstance(item.get(k), str) and 0 < len(item[k]) <= 1500 for k in ("explicacao", "verificar")):
                raise ValueError("Invalid explanation")
            seen.add(ident)
            output.append({**mapping[ident], "explicacao":item["explicacao"], "verificar":item["verificar"]})
        if not output:
            raise ValueError("Empty answer")
        return {"analises":output, "aviso":"Sugestões da IA para revisão humana. Nenhum cálculo ou arquivo foi alterado.",
                "limite":"Até 60 grupos com divergências ou alertas por análise."}
    except urllib.error.HTTPError as exc:
        raise HTTPException(429 if exc.code == 429 else 502,
            "Limite do Gemini atingido. Tente mais tarde." if exc.code == 429 else "Gemini indisponível. Confira a chave e o modelo no Railway.") from None
    except Exception:
        raise HTTPException(502, "Não foi possível obter uma análise válida do Gemini. A conferência permanece disponível.") from None


@router.get("/status")
def status():
    return {"configurado":bool(os.getenv("GEMINI_API_KEY", "").strip())}


@router.post("")
async def analyze(acumuladores: UploadFile = File(...), razao: UploadFile = File(...)):
    if not os.getenv("GEMINI_API_KEY", "").strip():
        raise HTTPException(503, "Gemini ainda não configurado. Defina GEMINI_API_KEY no Railway.")
    try:
        report = await run_in_threadpool(conferencia_fiscal_preview,
            await acumuladores.read(), acumuladores.filename or "fiscal.xlsx",
            await razao.read(), razao.filename or "razao.xlsx", 242)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await run_in_threadpool(explain, report)

from __future__ import annotations

import io
import os
import re
import unicodedata

import pandas as pd
from pypdf import PdfReader

from app.advanced import limpar_valor_monetario, normalizar_texto, processar_itau_generico, processar_daycoval_generico
from app.custom_adapters import processar_bradesco_padrao
from app.conferencia import preparar


COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]


def identificar_banco(texto: str, filename: str = "") -> str:
    t = normalizar_texto(f"{filename} {texto[:12000]}")
    if "itau" in t: return "itau"
    if "bradesco" in t: return "bradesco"
    if "sicredi" in t: return "sicredi"
    if "santander" in t: return "santander"
    if "daycoval" in t or "dayconnect" in t: return "daycoval"
    if "banco do brasil" in t or "bb.com.br" in t: return "banco_brasil"
    if "caixa economica" in t or "caixa.gov" in t: return "caixa"
    if "banco inter" in t or "inter pj" in t: return "inter"
    if "banco safra" in t: return "safra"
    if "btg" in t or "pactual" in t: return "btg"
    if "banco fibra" in t: return "fibra"
    return "banco"


def _prefixar(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in COLUNAS:
        if col not in out.columns:
            out[col] = ""
    out["DATA"] = pd.to_datetime(out["DATA"], dayfirst=True, errors="coerce")
    out["VALOR"] = pd.to_numeric(out["VALOR"], errors="coerce")
    out = out.dropna(subset=["DATA", "VALOR"])
    out = out[out["VALOR"].abs() >= 0.005].copy()
    def h(row):
        hist = str(row.get("HISTÓRICO") or "").strip()
        hist = re.sub(r"^(?:Pago|Recebido)\s*:\s*", "", hist, flags=re.I).strip()
        return ("Recebido: " if float(row["VALOR"]) > 0 else "Pago: ") + (hist or "MOVIMENTO BANCÁRIO")
    out["HISTÓRICO"] = out.apply(h, axis=1)
    # O conversor global não presume a conta contábil da empresa.
    out["DÉBITO"] = ""
    out["CRÉDITO"] = ""
    return out[COLUNAS].sort_values("DATA", kind="stable").reset_index(drop=True)


def processar_ofx(file_bytes: bytes, filename: str) -> pd.DataFrame:
    texto = ""
    for enc in ["utf-8", "latin1", "cp1252", "iso-8859-1"]:
        try:
            texto = file_bytes.decode(enc)
            break
        except Exception:
            pass
    if not texto:
        texto = file_bytes.decode("latin1", errors="ignore")
    banco = identificar_banco(texto, filename)
    rows = []
    for block in re.split(r"<STMTTRN>", texto, flags=re.I)[1:]:
        block = re.split(r"</STMTTRN>|</BANKTRANLIST>", block, flags=re.I)[0]
        md = re.search(r"<DTPOSTED>\s*(\d{8})", block, re.I)
        ma = re.search(r"<TRNAMT>\s*([+\-]?[\d\.,]+)", block, re.I)
        mh = re.search(r"<(?:MEMO|NAME|PAYEE)>\s*(.*?)(?:\r|\n|<|$)", block, re.I)
        mt = re.search(r"<TRNTYPE>\s*([A-Z]+)", block, re.I)
        if not md or not ma:
            continue
        raw = md.group(1)
        data = pd.to_datetime(raw[:8], format="%Y%m%d", errors="coerce")
        if pd.isna(data):
            continue
        valor = limpar_valor_monetario(ma.group(1))
        tipo = mt.group(1).upper() if mt else ""
        hist = (mh.group(1) if mh else "TRANSACAO OFX").replace("&amp;", "&").strip()
        if "saldo" in normalizar_texto(hist):
            continue
        if tipo in {"DEBIT", "PAYMENT", "FEE", "CHECK"}:
            valor = -abs(valor)
        elif tipo in {"CREDIT", "DEP", "DIRECTDEP"}:
            valor = abs(valor)
        rows.append({
            "DESCRIÇÃO": f"BANCO {banco.upper()}",
            "DATA": data, "VALOR": valor, "DÉBITO": "", "CRÉDITO": "", "HISTÓRICO": hist,
        })
    if not rows:
        raise ValueError("Nenhum lançamento foi reconhecido no OFX.")
    return _prefixar(pd.DataFrame(rows))


def processar_planilha_universal(file_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(filename)[1].lower()
    df = None
    if ext in {".xlsx", ".xls"}:
        try:
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            for sheet in xls.sheet_names:
                candidate = pd.read_excel(xls, sheet_name=sheet, dtype=object, header=None)
                if not candidate.empty and candidate.shape[1] > 1:
                    df = candidate
                    break
        except Exception:
            try:
                tables = pd.read_html(io.BytesIO(file_bytes), header=None)
                if tables: df = tables[0]
            except Exception:
                pass
    else:
        for enc in ["utf-8", "latin1", "cp1252", "utf-16"]:
            for sep in [";", ",", "\t", "|"]:
                try:
                    candidate = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, dtype=object, header=None)
                    if candidate.shape[1] > 1:
                        df = candidate
                        break
                except Exception:
                    pass
            if df is not None:
                break
    if df is None or df.empty:
        raise ValueError("Não foi possível ler a planilha.")

    header_idx = None
    for idx, row in df.head(40).iterrows():
        text = normalizar_texto(" ".join(str(v) for v in row if pd.notna(v)))
        if ("data" in text or " dt " in f" {text} ") and any(x in text for x in ["valor", "credito", "debito", "entrada", "saida"]):
            header_idx = idx
            break
    if header_idx is None:
        header_idx = 0
    headers = [normalizar_texto(v) or f"col_{i}" for i, v in enumerate(df.iloc[header_idx].tolist())]
    frame = df.iloc[header_idx + 1:].copy()
    frame.columns = headers

    def find(parts):
        return next((c for c in frame.columns if any(p in c for p in parts)), None)
    cdata = find(["data", "dt", "date", "dia"])
    chist = find(["historico", "hist", "descricao", "lancamento", "memo", "complemento"])
    cval = find(["valor", "amount", "monto"])
    ccred = find(["credito", "entrada", "credit"])
    cdeb = find(["debito", "saida", "debit"])
    if not cdata:
        raise ValueError("Coluna de data não localizada.")

    banco = identificar_banco(" ".join(frame.columns), filename)
    rows = []
    for _, row in frame.iterrows():
        dt = pd.to_datetime(row[cdata], dayfirst=True, errors="coerce")
        if pd.isna(dt):
            continue
        hist = str(row[chist] if chist and pd.notna(row[chist]) else "MOVIMENTO BANCARIO").strip()
        if any(x in normalizar_texto(hist) for x in ["saldo anterior", "subtotal", "total geral"]):
            continue
        valor = 0.0
        if ccred or cdeb:
            cred = limpar_valor_monetario(row[ccred]) if ccred and pd.notna(row[ccred]) else 0
            deb = limpar_valor_monetario(row[cdeb]) if cdeb and pd.notna(row[cdeb]) else 0
            valor = abs(cred) if cred else (-abs(deb) if deb else 0)
        elif cval and pd.notna(row[cval]):
            valor = limpar_valor_monetario(row[cval])
        if abs(valor) < 0.005:
            continue
        rows.append({"DESCRIÇÃO": f"BANCO {banco.upper()}","DATA":dt,"VALOR":valor,"DÉBITO":"","CRÉDITO":"","HISTÓRICO":hist})
    if not rows:
        raise ValueError("Nenhum lançamento válido foi encontrado na planilha.")
    return _prefixar(pd.DataFrame(rows))


def processar_pdf(file_bytes: bytes, filename: str) -> pd.DataFrame:
    reader = PdfReader(io.BytesIO(file_bytes))
    texto = "\n".join((p.extract_text() or "") for p in reader.pages)
    bank = identificar_banco(texto, filename)

    if bank == "itau":
        return _prefixar(processar_itau_generico(file_bytes, ""))
    if bank == "bradesco":
        return _prefixar(processar_bradesco_padrao(file_bytes, "", ()))
    if bank == "daycoval":
        return _prefixar(processar_daycoval_generico(file_bytes))
    if bank == "santander":
        from razync.santander_statement import parece_extrato_santander_empresarial, processar_extrato_santander_empresarial_texto
        if parece_extrato_santander_empresarial(texto):
            return _prefixar(pd.DataFrame(processar_extrato_santander_empresarial_texto(texto)))
    if bank == "banco_brasil":
        from razync.bb_statement import parece_extrato_bb_autorizavel, processar_extrato_bb_autorizavel
        if parece_extrato_bb_autorizavel(texto):
            return _prefixar(pd.DataFrame(processar_extrato_bb_autorizavel(file_bytes)))
        from razync.valean_625 import processar_bb_625
        return _prefixar(processar_bb_625(file_bytes))
    if bank == "sicredi":
        from razync.valean_625 import processar_sicredi_625
        return _prefixar(processar_sicredi_625(file_bytes))
    if bank == "caixa":
        from razync.valean_625 import processar_caixa_625
        return _prefixar(processar_caixa_625(file_bytes))
    if bank == "inter":
        from razync.lucrativite_841 import processar_extrato_inter_pdf_841
        return _prefixar(processar_extrato_inter_pdf_841(file_bytes))
    if bank == "btg":
        from razync.vgv_1402 import processar_extrato_btg_vgv
        return _prefixar(processar_extrato_btg_vgv(file_bytes))
    raise ValueError(f"Banco não reconhecido automaticamente no PDF ({bank}).")


def processar_arquivo(file_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return processar_pdf(file_bytes, filename)
    if ext == ".ofx":
        return processar_ofx(file_bytes, filename)
    if ext in {".xls", ".xlsx", ".csv"}:
        return processar_planilha_universal(file_bytes, filename)
    raise ValueError(f"Formato não suportado: {ext}")


def processar_razao(file_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(filename)[1].lower()
    raw = None
    if ext in {".xlsx", ".xls"}:
        try:
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            for sheet in xls.sheet_names:
                candidate = pd.read_excel(xls, sheet_name=sheet, dtype=object, header=None)
                if not candidate.empty and candidate.shape[1] > 1:
                    raw = candidate
                    break
        except Exception:
            try:
                tables = pd.read_html(io.BytesIO(file_bytes), header=None)
                raw = tables[0] if tables else None
            except Exception:
                pass
    else:
        for enc in ["utf-8", "latin1", "cp1252"]:
            for sep in [";", "\t", "|", ","]:
                try:
                    candidate = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, dtype=object, header=None, on_bad_lines="skip")
                    if candidate.shape[1] > 1:
                        raw = candidate
                        break
                except Exception:
                    pass
            if raw is not None: break
    if raw is None or raw.empty:
        raise ValueError("Não foi possível ler o Razão.")

    header = 0
    for i, row in raw.head(50).iterrows():
        text = normalizar_texto(" ".join(str(v) for v in row if pd.notna(v)))
        if "data" in text and any(x in text for x in ["debito","credito","valor"]):
            header = i
            break
    headers = [normalizar_texto(v).upper() for v in raw.iloc[header].tolist()]
    df = raw.iloc[header+1:].copy(); df.columns = headers
    cols = list(df.columns)
    cdata = next((c for c in cols if "DATA" in c or c=="DT"), None)
    cdeb = next((c for c in cols if "DEBIT" in c or "SAIDA" in c), None)
    ccred = next((c for c in cols if "CREDIT" in c or "ENTRADA" in c), None)
    cval = next((c for c in cols if "VALOR" in c or c=="VL"), None)
    chist = next((c for c in cols if any(x in c for x in ["HISTOR","COMPLEMENT","LANCAMENTO","DESCRI"])), None)
    if not cdata:
        raise ValueError("Coluna de data não localizada no Razão.")
    rows=[]
    for _,row in df.iterrows():
        dt=pd.to_datetime(row[cdata],dayfirst=True,errors="coerce")
        if pd.isna(dt): continue
        entrada=saida=0.0
        if cdeb and ccred:
            saida=abs(limpar_valor_monetario(row[cdeb])) if pd.notna(row[cdeb]) else 0
            entrada=abs(limpar_valor_monetario(row[ccred])) if pd.notna(row[ccred]) else 0
        elif cval and pd.notna(row[cval]):
            v=limpar_valor_monetario(row[cval])
            entrada=max(v,0); saida=max(-v,0)
        if not entrada and not saida: continue
        rows.append({"DATA":dt.normalize(),"ENTRADAS_RAZAO":entrada,"SAIDAS_RAZAO":saida,"HISTÓRICO":str(row[chist] if chist and pd.notna(row[chist]) else "LANCAMENTO RAZAO")})
    if not rows:
        raise ValueError("Nenhum lançamento válido localizado no Razão.")
    return pd.DataFrame(rows)


def conciliar_razao(extrato: pd.DataFrame, razao: pd.DataFrame):
    e = preparar(extrato)
    diario_e = e.assign(
        ENTRADAS_EXTRATO=e["VALOR"].where(e["VALOR"]>0,0),
        SAIDAS_EXTRATO=-e["VALOR"].where(e["VALOR"]<0,0),
    ).groupby("DATA",as_index=False)[["ENTRADAS_EXTRATO","SAIDAS_EXTRATO"]].sum()

    r=razao.copy()
    r["DATA"]=pd.to_datetime(r["DATA"],errors="coerce").dt.normalize()
    diario_r=r.groupby("DATA",as_index=False)[["ENTRADAS_RAZAO","SAIDAS_RAZAO"]].sum()
    out=pd.merge(diario_e,diario_r,on="DATA",how="outer").fillna(0)
    out["DIFERENÇA ENTRADAS"]=(out["ENTRADAS_RAZAO"]-out["ENTRADAS_EXTRATO"]).round(2)
    out["DIFERENÇA SAÍDAS"]=(out["SAIDAS_RAZAO"]-out["SAIDAS_EXTRATO"]).round(2)
    out["SITUAÇÃO"]=out.apply(lambda x:"CONFERE" if abs(x["DIFERENÇA ENTRADAS"])<0.01 and abs(x["DIFERENÇA SAÍDAS"])<0.01 else "REVISAR",axis=1)
    summary={
        "dias":len(out),
        "dias_conferidos":int((out["SITUAÇÃO"]=="CONFERE").sum()),
        "dias_revisar":int((out["SITUAÇÃO"]=="REVISAR").sum()),
        "entradas_extrato":round(float(diario_e["ENTRADAS_EXTRATO"].sum()),2),
        "saidas_extrato":round(float(diario_e["SAIDAS_EXTRATO"].sum()),2),
        "entradas_razao":round(float(diario_r["ENTRADAS_RAZAO"].sum()),2),
        "saidas_razao":round(float(diario_r["SAIDAS_RAZAO"].sum()),2),
    }
    return out.sort_values("DATA"), summary


# Adapters preserve the original universal readers instead of reduced copies.
def processar_arquivo(file_bytes: bytes, filename: str) -> pd.DataFrame:
    from app import engine
    with engine.processing_context():
        rows = engine.processar_extrato_conferencia_empresa(file_bytes, filename)
        frame = pd.DataFrame(rows, columns=COLUNAS)
        if frame.empty:
            raise ValueError('Nenhum lançamento válido encontrado no arquivo.')
        return frame


def processar_razao(file_bytes: bytes, filename: str) -> pd.DataFrame:
    from app import engine
    with engine.processing_context():
        frame = engine.processar_razao_dominio(file_bytes, filename)
        if frame is None or frame.empty:
            raise ValueError('Nenhum lançamento válido encontrado no Razão.')
        frame = frame.copy()
        frame['DATA'] = frame['DATA_DT'].dt.normalize()
        return frame

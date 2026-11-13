from __future__ import annotations

import io, re, unicodedata
from collections import defaultdict
import pandas as pd


BASE_COLS = ["DESCRIÇÃO", "DATA", "VALOR", "HISTÓRICO"]


def _norm(v):
    t=unicodedata.normalize("NFKD",str(v or ""))
    t="".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+","",t.casefold())


def ler_modelo_excel(content:bytes, bank:str="") -> pd.DataFrame:
    xls=pd.ExcelFile(io.BytesIO(content))
    parts=[]
    for sheet in xls.sheet_names:
        raw=pd.read_excel(xls,sheet_name=sheet,header=None,dtype=object)
        header=None
        for i in range(min(30,len(raw))):
            mp={_norm(v):j for j,v in enumerate(raw.iloc[i].tolist())}
            if all(k in mp for k in ["data","valor","historico"]):
                header=(i,mp); break
        if not header: continue
        i,mp=header
        df=raw.iloc[i+1:].copy()
        out=pd.DataFrame()
        out["DESCRIÇÃO"]=df.iloc[:,mp.get("descricao",mp.get("descrição",-1))] if ("descricao" in mp or "descrição" in mp) else sheet
        out["DATA"]=pd.to_datetime(df.iloc[:,mp["data"]],dayfirst=True,errors="coerce")
        vals=df.iloc[:,mp["valor"]]
        out["VALOR"]=pd.to_numeric(vals,errors="coerce")
        if out["VALOR"].isna().all():
            def money(x):
                s=str(x or "").replace("R$","").replace(" ","")
                if "," in s: s=s.replace(".","").replace(",",".")
                try:return float(s)
                except:return None
            out["VALOR"]=vals.map(money)
        out["HISTÓRICO"]=df.iloc[:,mp["historico"]].fillna("").astype(str)
        out["ABA"]=sheet
        out=out.dropna(subset=["DATA","VALOR"])
        out=out[out["VALOR"].abs()>=0.005]
        if bank:
            bn=_norm(bank)
            # Só restringe por nome de aba quando existe indicação explícita.
            if any(x in _norm(sheet) for x in ["itau","bradesco","sicredi","caixa","inter","safra","btg","santander","brasil","daycoval","fibra"]):
                aliases={
                    "bancobrasil":["brasil","bb"],"banco_brasil":["brasil","bb"],
                    "itau":["itau"],"bradesco":["bradesco"],"sicredi":["sicredi"],
                    "caixa":["caixa"],"inter":["inter"],"safra":["safra"],"btg":["btg"],
                    "santander":["santander"],"daycoval":["daycoval"],"fibra":["fibra"]
                }
                al=aliases.get(bn,[bn])
                if not any(a in _norm(sheet) for a in al):
                    continue
        parts.append(out)
    if not parts:
        raise ValueError("Nenhum lançamento do Modelo Domínio foi encontrado.")
    return pd.concat(parts,ignore_index=True)


def preparar(data) -> pd.DataFrame:
    df=data.copy() if isinstance(data,pd.DataFrame) else pd.DataFrame(data or [])
    for c in BASE_COLS:
        if c not in df.columns: df[c]="" if c!="VALOR" else 0.0
    df["DATA"]=pd.to_datetime(df["DATA"],dayfirst=True,errors="coerce").dt.normalize()
    df["VALOR"]=pd.to_numeric(df["VALOR"],errors="coerce").fillna(0).round(2)
    df["HISTÓRICO"]=df["HISTÓRICO"].fillna("").astype(str)
    df["DESCRIÇÃO"]=df["DESCRIÇÃO"].fillna("").astype(str)
    df=df.dropna(subset=["DATA"])
    df=df[df["VALOR"].abs()>=0.005].copy()
    df["_CENTS"]=(df["VALOR"]*100).round().astype(int)
    return df.reset_index(drop=True)


def conciliar(modelo, extrato):
    m=preparar(modelo); e=preparar(extrato)
    avail=defaultdict(list)
    for i,row in m.iterrows():
        avail[(row["DATA"],int(row["_CENTS"]))].append(i)
    matched_m=set(); unmatched_e=[]
    for i,row in e.iterrows():
        key=(row["DATA"],int(row["_CENTS"]))
        if avail[key]:
            matched_m.add(avail[key].pop(0))
        else:
            unmatched_e.append(i)
    unmatched_m=[i for i in range(len(m)) if i not in matched_m]

    faltando=e.loc[unmatched_e,BASE_COLS].copy()
    a_mais=m.loc[unmatched_m,BASE_COLS].copy()

    def daily(df,prefix):
        t=df[["DATA","VALOR"]].copy()
        t[f"ENTRADAS {prefix}"]=t["VALOR"].where(t["VALOR"]>0,0)
        t[f"SAÍDAS {prefix}"]=-t["VALOR"].where(t["VALOR"]<0,0)
        return t.groupby("DATA",as_index=False)[[f"ENTRADAS {prefix}",f"SAÍDAS {prefix}"]].sum()
    diario=pd.merge(daily(e,"EXTRATO"),daily(m,"PLANILHA"),on="DATA",how="outer").fillna(0)
    diario["DIFERENÇA ENTRADAS"]=(diario["ENTRADAS PLANILHA"]-diario["ENTRADAS EXTRATO"]).round(2)
    diario["DIFERENÇA SAÍDAS"]=(diario["SAÍDAS PLANILHA"]-diario["SAÍDAS EXTRATO"]).round(2)
    resumo={
        "planilha":len(m),"extrato":len(e),"conferidos":len(matched_m),
        "faltando_planilha":len(faltando),"a_mais_planilha":len(a_mais),
        "entradas_planilha":round(float(m.loc[m["VALOR"]>0,"VALOR"].sum()),2),
        "saidas_planilha":round(float(-m.loc[m["VALOR"]<0,"VALOR"].sum()),2),
        "entradas_extrato":round(float(e.loc[e["VALOR"]>0,"VALOR"].sum()),2),
        "saidas_extrato":round(float(-e.loc[e["VALOR"]<0,"VALOR"].sum()),2),
    }
    resumo["ok"]=not len(faltando) and not len(a_mais)
    return resumo,diario,faltando,a_mais

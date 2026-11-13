from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime

import pandas as pd
from pypdf import PdfReader


COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _money(value: str) -> float:
    text = str(value or "").replace("R$", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    return round(float(text), 2)


def _prefix(value: float, history: str) -> str:
    history = re.sub(r"^(?:Pago|Recebido)\s*:\s*", "", str(history or "").strip(), flags=re.I)
    return ("Recebido: " if value > 0 else "Pago: ") + (history or "MOVIMENTO BANCÁRIO")


def processar_bb_47(conteudo: bytes) -> pd.DataFrame:
    reader = PdfReader(io.BytesIO(conteudo))
    linhas = []
    for pagina in reader.pages:
        linhas.extend((pagina.extract_text() or "").splitlines())

    regex_mov = re.compile(
        r"^(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})\s*"
        r"\((?P<natureza>[+-])\)(?P<data>\d{2}/\d{2}/\d{4})\s*(?P<resto>.*)$"
    )
    brutos, atual = [], None
    for raw in linhas:
        linha = re.sub(r"\s+", " ", raw).strip()
        if not linha:
            continue
        m = regex_mov.match(linha)
        if m:
            if atual:
                brutos.append(atual)
            valor = _money(m.group("valor"))
            valor = abs(valor) if m.group("natureza") == "+" else -abs(valor)
            atual = {
                "data": m.group("data"),
                "valor": valor,
                "resto": m.group("resto").strip(),
                "compl": [],
            }
        elif atual:
            atual["compl"].append(linha)
    if atual:
        brutos.append(atual)

    rows = []
    for item in brutos:
        texto = re.sub(r"\s+", " ", " ".join([item["resto"]] + item["compl"])).strip()
        n = _norm(texto)
        if (
            item["data"] == "00/00/0000"
            or "saldo anterior" in n
            or "saldo do dia" in n
            or re.sub(r"\s+", "", texto).upper() == "SALDO"
        ):
            continue
        data = pd.to_datetime(item["data"], dayfirst=True, errors="coerce")
        if pd.isna(data):
            continue
        parts = item["resto"].split()
        first = " ".join(parts[2:]).strip() if len(parts) >= 2 and parts[0].isdigit() else item["resto"]
        history = re.sub(r"\s+", " ", " ".join([first] + item["compl"])).strip()
        valor = float(item["valor"])
        rows.append({
            "DESCRIÇÃO": "BANCO DO BRASIL",
            "DATA": data,
            "VALOR": round(valor, 2),
            "DÉBITO": "8" if valor > 0 else "",
            "CRÉDITO": "8" if valor < 0 else "",
            "HISTÓRICO": _prefix(valor, history),
        })
    if not rows:
        raise ValueError("Nenhum lançamento válido encontrado no Banco do Brasil da empresa 47.")
    return pd.DataFrame(rows, columns=COLUNAS).sort_values("DATA", kind="stable").reset_index(drop=True)


def _periodo_bradesco(texto: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    m = re.search(r"Entre\s+(\d{2}/\d{2}/\d{4})\s+e\s+(\d{2}/\d{2}/\d{4})", texto, flags=re.I)
    if m:
        return (
            pd.to_datetime(m.group(1), dayfirst=True),
            pd.to_datetime(m.group(2), dayfirst=True),
        )
    datas = re.findall(r"\d{2}/\d{2}/\d{4}", texto[:1400])
    if len(datas) >= 2:
        a = pd.to_datetime(datas[0], dayfirst=True)
        b = pd.to_datetime(datas[1], dayfirst=True)
        if a <= b:
            return a, b
    raise ValueError("Período principal do extrato Bradesco não identificado.")


def processar_bradesco_padrao(conteudo: bytes, conta: str, identificadores: tuple[str, ...]) -> pd.DataFrame:
    reader = PdfReader(io.BytesIO(conteudo))
    textos = [p.extract_text() or "" for p in reader.pages]
    texto = "\n".join(textos)
    topo = texto.upper()
    if identificadores and not any(i.upper() in topo for i in identificadores):
        raise ValueError("O PDF não corresponde à empresa/banco selecionado.")

    inicio, fim = _periodo_bradesco(texto)
    regex_data = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*(.*)$")
    regex_moeda = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")

    data_atual = None
    saldo_anterior = None
    partes = []
    rows = []
    inside_invest = False

    for pagina in textos:
        for raw in pagina.splitlines():
            linha = re.sub(r"\s+", " ", raw).strip()
            if not linha:
                continue
            n = _norm(linha)
            if n.startswith("saldos invest facil"):
                inside_invest = True
                partes = []
                continue
            if inside_invest:
                continue
            if n.startswith(("folha ", "extrato mensal", "nome do usuario:", "data da operacao:", "total ")):
                continue

            m = regex_data.match(linha)
            if m:
                data_atual = m.group(1)
                linha = m.group(2).strip()
                n = _norm(linha)
                if not linha:
                    continue

            if "saldo anterior" in n:
                moedas = regex_moeda.findall(linha)
                if moedas:
                    saldo_anterior = _money(moedas[-1])
                partes = []
                continue

            if not data_atual:
                continue
            dt = pd.to_datetime(data_atual, dayfirst=True, errors="coerce")
            if pd.isna(dt) or dt < inicio or dt > fim:
                continue

            moedas = regex_moeda.findall(linha)
            if len(moedas) >= 2:
                mov_txt, saldo_txt = moedas[-2], moedas[-1]
                impresso = _money(mov_txt)
                saldo = _money(saldo_txt)
                if saldo_anterior is not None:
                    variacao = round(saldo - saldo_anterior, 2)
                    valor = variacao if abs(abs(variacao) - abs(impresso)) <= 0.02 else impresso
                else:
                    valor = impresso
                saldo_anterior = saldo

                pos = linha.rfind(mov_txt)
                trecho = linha[:pos].strip()
                history = re.sub(r"\s+", " ", " ".join(partes + ([trecho] if trecho else []))).strip(" |-")
                partes = []
                hn = _norm(history)
                if not history or hn.startswith(("saldo ", "total ")):
                    continue
                if abs(valor) < 0.005:
                    continue
                rows.append({
                    "DESCRIÇÃO": "BANCO BRADESCO",
                    "DATA": dt,
                    "VALOR": round(float(valor), 2),
                    "DÉBITO": conta if valor > 0 else "",
                    "CRÉDITO": conta if valor < 0 else "",
                    "HISTÓRICO": _prefix(valor, history),
                })
            else:
                partes.append(linha)
                if len(partes) > 8:
                    partes = partes[-8:]

    if not rows:
        raise ValueError("Nenhum lançamento válido encontrado no extrato Bradesco.")
    return pd.DataFrame(rows, columns=COLUNAS).sort_values("DATA", kind="stable").reset_index(drop=True)


def processar_912_sicredi(conteudo: bytes) -> pd.DataFrame:
    from razync.valean_625 import processar_sicredi_625

    df = processar_sicredi_625(conteudo).copy()
    df["DÉBITO"] = df["VALOR"].apply(lambda v: "515" if float(v) > 0 else "")
    df["CRÉDITO"] = df["VALOR"].apply(lambda v: "515" if float(v) < 0 else "")

    reader = PdfReader(io.BytesIO(conteudo))
    texto = "\n".join((p.extract_text() or "") for p in reader.pages)
    m = re.search(r"Per[ií]odo\s+de\s+(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})", texto, flags=re.I)
    if m:
        ini = pd.to_datetime(m.group(1), dayfirst=True)
        fim = pd.to_datetime(m.group(2), dayfirst=True)
        datas = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
        df = df[(datas >= ini) & (datas <= fim)].copy()
    return df.sort_values("DATA", kind="stable").reset_index(drop=True)


def processar_itau_identificado(
    conteudo: bytes,
    conta: str,
    identificadores: tuple[str, ...],
    rotulo: str,
) -> pd.DataFrame:
    from razync.engekraft_969 import processar_extrato_itau_modelo
    return processar_extrato_itau_modelo(conteudo, conta, identificadores, rotulo)


def processar_custom(company_code: int, bank: str, conteudo: bytes) -> pd.DataFrame:
    bank = (bank or "").strip().casefold()
    if company_code == 47:
        return processar_bb_47(conteudo)
    if company_code == 154 and bank == "bradesco":
        return processar_bradesco_padrao(conteudo, "9", ("0004700-7", "R M SERVICOS POSTAIS", "68.370.568/0001-38"))
    if company_code == 154 and bank == "itau":
        return processar_itau_identificado(conteudo, "508", ("R M SERVICOS POSTAIS", "68.370.568/0001-38", "0015961-9"), "empresa 154")
    if company_code == 912:
        return processar_912_sicredi(conteudo)
    if company_code == 964:
        return processar_bradesco_padrao(conteudo, "9", ("WILLIANS VENANCIO", "964"))
    if company_code == 1532:
        return processar_itau_identificado(conteudo, "508", ("MARIA A D P NARB", "59.124.979/0001-52", "0097731-6"), "empresa 1532")
    raise KeyError(f"Sem adaptador customizado para empresa {company_code}/{bank}.")

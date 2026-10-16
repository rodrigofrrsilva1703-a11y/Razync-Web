"""Empresa 734 — extratos bancários PDF do BTG 510 e Bradesco 2721.

Não assume conta bancária/agência sem um extrato real; as contas 510 e 2721
são contas contábeis do Modelo Domínio, informadas pelo usuário.
"""
from __future__ import annotations

import io
import pandas as pd
from pypdf import PdfReader

from app import engine

COLUNAS = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
BANKS = {"btg": ("BTG 510", "BANCO BTG", "510"),
         "bradesco": ("Bradesco 2721", "BANCO BRADESCO", "2721")}


def read_bank_pdf(bank: str, data: bytes, filename: str) -> pd.DataFrame:
    if bank not in BANKS:
        raise ValueError("Banco não configurado para a empresa 734.")
    if not str(filename).lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise ValueError(f"{BANKS[bank][0]}: envie o extrato original em PDF.")
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Extrato PDF excede 25 MB.")
    try:
        pdf = PdfReader(io.BytesIO(data), strict=False)
        if not 0 < len(pdf.pages) <= 80 or not any((page.extract_text() or "").strip() for page in pdf.pages):
            raise ValueError("Extrato PDF não contém texto legível; envie a versão original do banco.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Extrato bancário PDF inválido ou protegido.") from exc

    # O BTG usa o leitor de PDF já presente no Razync; o Bradesco usa o
    # leitor bancário genérico. Não alteramos as regras das demais empresas.
    rows = engine.processar_extrato_conferencia_empresa(data, filename, bank)
    if not rows:
        raise ValueError(
            f"{BANKS[bank][0]}: nenhum lançamento identificado. "
            "O layout do extrato pode exigir adaptação com um PDF de exemplo."
        )
    frame = pd.DataFrame(rows)
    if any(field not in frame.columns for field in ("DATA", "VALOR", "HISTÓRICO")):
        raise ValueError("Extrato incompleto: data, valor ou histórico ausente.")
    frame["DATA"] = pd.to_datetime(frame["DATA"], dayfirst=True, errors="coerce")
    frame["VALOR"] = pd.to_numeric(frame["VALOR"], errors="coerce")
    frame = frame.dropna(subset=["DATA", "VALOR"]).copy()
    frame = frame.loc[frame["VALOR"].abs() >= 0.005].copy()
    if frame.empty:
        raise ValueError("Nenhuma movimentação válida identificada no extrato.")
    _, description, account = BANKS[bank]
    frame["DESCRIÇÃO"] = description
    frame["DÉBITO"] = frame["VALOR"].apply(lambda value: account if value > 0 else "")
    frame["CRÉDITO"] = frame["VALOR"].apply(lambda value: account if value < 0 else "")
    return frame[COLUNAS]


def workflow_734(roles: dict, options: dict):
    from app.migration_services import filter_frame
    sheets = {}
    for bank, (sheet, _, _) in BANKS.items():
        files = roles.get(bank) or []
        if not files:
            continue
        parts = [read_bank_pdf(bank, data, filename) for filename, data in files]
        frame = filter_frame(pd.concat(parts, ignore_index=True), options)
        if not frame.empty:
            sheets[sheet] = frame.sort_values("DATA", kind="stable").reset_index(drop=True)
    if not sheets:
        raise ValueError("Envie extrato BTG e/ou Bradesco em PDF com movimentações no período.")
    # Abas separadas e contas bancárias do Domínio preservadas.
    return engine.gerar_excel_nova_geracao(
        {sheet: {"principal": frame, "retirados": pd.DataFrame()} for sheet, frame in sheets.items()},
        prefixar_historicos=True,
    ), "RAZYNC_734_MODELO_DOMINIO.xlsx"

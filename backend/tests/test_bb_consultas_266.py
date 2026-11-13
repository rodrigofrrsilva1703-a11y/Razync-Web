"""Regressão do PDF BB Consultas (empresa 266), sem dados bancários reais."""
import io
import json
from datetime import datetime

import fitz
import pytest
from fastapi.testclient import TestClient

from app import operating_hours
from app.bb_consultas_266 import (
    parece_extrato_bb_consultas_266,
    ler_extrato_bb_consultas_266,
)
from app.main import app
from app.migration_services import statement, reconcile
from test_migration import xlsx


MOVES = [
    ("TED", -500000.0, "31/08/2026"),
    ("BB Rende Fácil", 192321.02, "31/08/2026"),
    ("Resgate BB CDB DI", 308000.0, "31/08/2026"),
    ("BB Rende Fácil", -321.02, "31/08/2026"),
    ("CDB/RDB", 75180.12, "31/08/2026"),
    ("CDB/RDB", 1453.20, "31/08/2026"),
    ("CDB/RDB", 2380.68, "31/08/2026"),
]


def bb_consultas_pdf(account="200076-8", saldo_final="79.014,00", include_closing=True):
    lines = [
        "Consultas - Extrato de conta corrente",
        "Cliente - Conta atual",
        "Agência 1557-1",
        f"Conta corrente {account}NOVA G C ELETRICA LTDA",
        "Período do extrato 08 / 2026",
        "Lançamentos",
        "Dt. balancete Dt. movimento Ag. origem Lote Histórico Documento Valor R$ Saldo",
        "06/07/2026 0000 00000 000 Saldo Anterior 0,00 C",
        "31/08/2026 0000 13105 438 TED 83.101 500.000,00 D",
        "237 7732 067801142000129 NOVA GERACAO",
        "31/08/2026 0000 00000 798 BB Rende Fácil 9.903 192.321,02 C",
        "31/08/2026 0000 00000 989 Resgate BB CDB DI 98 308.000,00 C",
        "31/08/2026 0000 00000 351 BB Rende Fácil 9.903 321,02 D",
        "31/08/2026 01/09/2026 9103 12060 798 CDB/RDB 800.962.908.215 75.180,12 C",
        "31/08/2026 01/09/2026 9103 12060 798 CDB/RDB 901.000.389.118 1.453,20 C",
        "31/08/2026 01/09/2026 9103 12060 798 CDB/RDB 4.900.954.411.098 2.380,68 C",
    ]
    if include_closing:
        lines.append(f"31/08/2026 0000 00000 999 S A L D O {saldo_final} C")
    lines.extend(["BB, sou eu. Com os cartoes BB, seu negocio", "Transação efetuada com sucesso."])
    doc = fitz.open()
    page = doc.new_page(width=1050, height=842)
    for i, line in enumerate(lines):
        page.insert_text((20, 30 + i * 23), line, fontsize=10)
    content = doc.tobytes()
    doc.close()
    return content


def model_266_bb():
    rows = [["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]]
    for history, value, date in MOVES:
        rows.append(["BANCO DO BRASIL", date, value,
                     "8" if value > 0 else "", "8" if value < 0 else "", history])
    return xlsx(rows, title="Banco do Brasil 200076-8")


def test_bb_pdf_real_layout_sete_movimentos_e_saldo_reconciliado():
    pdf = bb_consultas_pdf()
    assert parece_extrato_bb_consultas_266(pdf)
    rows = ler_extrato_bb_consultas_266(pdf)
    assert len(rows) == 7
    assert [x["VALOR"] for x in rows] == [v for _, v, _ in MOVES]
    assert all(row["DATA"] == datetime(2026, 8, 31) for row in rows)
    assert sum(round(row["VALOR"] * 100) for row in rows) == 7901400
    assert all("SALDO" not in row["HISTÓRICO"].upper() for row in rows)
    assert "237 7732" in rows[0]["HISTÓRICO"]
    assert "800.962.908.215" in rows[4]["HISTÓRICO"]


def test_bb_pdf_conta_errada_nao_eh_aceita():
    with pytest.raises(ValueError, match="200076-8"):
        ler_extrato_bb_consultas_266(bb_consultas_pdf(account="200076-9"))


def test_bb_pdf_detecta_movimento_nao_lido_e_falta_de_fechamento():
    with pytest.raises(ValueError, match="não confere"):
        ler_extrato_bb_consultas_266(bb_consultas_pdf(saldo_final="79.015,00"))
    with pytest.raises(ValueError, match="saldos inicial ou final ausentes"):
        ler_extrato_bb_consultas_266(bb_consultas_pdf(include_closing=False))


def test_bb_pdf_266_vai_para_conferencia_com_extrato():
    pdf = bb_consultas_pdf()
    frame = statement(266, "banco_brasil", pdf, "BB - 08.2026.pdf")
    assert len(frame) == 7
    assert frame["VALOR"].tolist() == [v for _, v, _ in MOVES]
    summary, sheets = reconcile(
        266, "banco_brasil", model_266_bb(),
        [("BB - 08.2026.pdf", pdf)], {"data_inicial": "2026-08-01", "data_final": "2026-08-31"}
    )
    assert summary["extrato"] == 7
    assert summary["planilha"] == 7
    assert summary["ok"] is True
    assert len(sheets["Extrato analisado"]) == 7


def test_api_preview_bb_pdf_266(monkeypatch):
    monkeypatch.setattr(operating_hours, "is_open", lambda *a: True)
    response = TestClient(app).post(
        "/api/v1/conferencia-extrato/266/preview",
        data={"bank": "banco_brasil", "options_json": "{}"},
        files=[
            ("model_file", ("modelo.xlsx", model_266_bb(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("statement_files", ("BB - 08.2026.pdf", bb_consultas_pdf(), "application/pdf")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["extrato"] == 7
    assert response.json()["summary"]["ok"] is True

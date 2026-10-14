"""Integração Santander (conta 513) exclusiva da empresa 1001."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import engine, operating_hours
from app.advanced import processar_planilha_accede_sig
from app.main import app
from app.migration_services import workflow
from app.registry import CAPABILITIES
from razync.companies import CONFIGURACOES_ACCEDE
from test_migration import xlsx


def sample_sig(bank):
    return xlsx([
        ["Data", "D/C", "Complemento", "Conf", "Entrada", "Saída", "Saldo", "Conta Vinculada"],
        ["01/10/2026", "CRÉDITO", f"RECEBIMENTO {bank}", "DOC-01", 150.75, None, 150.75, None],
        ["02/10/2026", "DÉBITO", f"PAGAMENTO {bank}", "DOC-02", None, 45.20, 105.55, None],
    ], title=bank.title())


def test_cadastro_empresa_1001_possui_santander_513_sem_mudar_demais_contas():
    cap = CAPABILITIES[1001]
    assert cap["banks"] == {"itau": "508", "sicredi": "505", "santander": "513"}
    santander = next(role for role in cap["roles"] if role["name"] == "santander")
    assert santander["accept"] == ".xls,.xlsx"
    assert santander["multiple"] is True and santander["optional"] is True
    assert CONFIGURACOES_ACCEDE["accede_equipamentos"]["contas_bancarias"]["santander"] == "513"
    assert "santander" not in CAPABILITIES[1000]["banks"]


def test_parser_sig_santander_identifica_banco_e_conserva_lancamentos():
    with engine.processing_context("accede_equipamentos"):
        frame = processar_planilha_accede_sig(sample_sig("santander"), "santander", "accede_equipamentos")
    assert frame["DESCRIÇÃO"].tolist() == ["BANCO SANTANDER", "BANCO SANTANDER"]
    assert frame["VALOR"].tolist() == [150.75, -45.2]
    assert "RECEBIMENTO" in frame.iloc[0]["HISTÓRICO"]
    assert "PAGAMENTO" in frame.iloc[1]["HISTÓRICO"]


def test_1001_santander_sozinho_gera_aba_e_conta_513():
    raw, filename = workflow(1001, {"santander": [("santander.xlsx", sample_sig("santander"))]}, {})
    assert filename == "ACCEDE_1001_MODELO_DOMINIO.xlsx"
    wb = load_workbook(io.BytesIO(raw))
    assert wb.sheetnames == ["Santander"]
    rows = list(wb.active.values)
    assert rows[1][0] == "BANCO SANTANDER"
    assert rows[1][2] == 150.75 and str(rows[1][3]) == "513" and not rows[1][4]
    assert rows[2][2] == -45.2 and not rows[2][3] and str(rows[2][4]) == "513"


def test_1001_multibanco_preserva_abas_e_nao_altera_saldos_anteriores():
    roles = {name: [(f"{name}.xlsx", sample_sig(name))] for name in ("itau", "sicredi", "santander")}
    raw, _ = workflow(1001, roles, {})
    wb = load_workbook(io.BytesIO(raw))
    assert wb.sheetnames == ["Itau", "Sicredi", "Santander"]
    assert [ws["C2"].value for ws in wb.worksheets] == [150.75, 150.75, 150.75]
    assert wb["Itau"]["A2"].value == "BANCO ITAÚ"
    assert wb["Sicredi"]["A2"].value == "SICREDI"
    assert wb["Santander"]["A2"].value == "BANCO SANTANDER"


def test_1001_workflow_endpoint_aceita_santander(monkeypatch):
    monkeypatch.setattr(operating_hours, "is_open", lambda *a: True)
    client = TestClient(app)
    company = client.get("/api/v1/companies/1001")
    assert company.status_code == 200
    assert company.json()["capabilities"]["banks"]["santander"] == "513"
    response = client.post(
        "/api/v1/workflow/1001",
        data={"roles_json": json.dumps(["santander"]), "options_json": "{}"},
        files={"files": ("santander.xlsx", sample_sig("santander"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200, response.text
    assert load_workbook(io.BytesIO(response.content)).sheetnames == ["Santander"]

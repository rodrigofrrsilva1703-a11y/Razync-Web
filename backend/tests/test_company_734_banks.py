"""734 BTG: apenas PDF, leitura de todas as linhas e reconciliação de saldos."""
import io
from unittest.mock import patch

import fitz
import pytest
import pandas as pd
from openpyxl import load_workbook

from app.bank_734 import read_bank_pdf, workflow_734, _clean_history
from app.registry import CAPABILITIES
from app.migration_services import _workflow


def btg_pdf(with_bad_total=False):
    doc = fitz.open()
    page = doc.new_page()
    first = [
        "Conta corrente - PJ",
        "Razao social",
        "EMPRESA DE EXEMPLO LTDA",
        "Periodo do extrato: 01/07/2026 - 31/07/2026",
        "Período do extrato: 01/07/2026 - 31/07/2026",
        "Saldo de abertura em 01/07/2026:",
        "R$ 100,00",
        "Saldo de fechamento em 31/07/2026:",
        "R$ 150,27",
        "Total de entradas",
        "R$ 100,27",
        "Total de saídas",
        ("R$ 50,01" if with_bad_total else "R$ 50,00"),
        "Data lançamento",
        "Descrição do lançamento",
        "31/07/2026",
        "Saldo de fechamento",
        "150,27",
        "31/07/2026",
        "Valor de Rendimento Remunera+",
        "0,27",
        "150,27",
        "30/07/2026",
        "Pix recebido de CLIENTE TESTE",
        "Banco 341 | CPF ***.123.456-**",
        "100,00",
        "150,00",
        "30/07/2026",
        "Pagamento de Conta / Tributo - TESTE",
        "-50,00",
        "50,00",
        "Fale com nossa central",
    ]
    for i, line in enumerate(first):
        page.insert_text((28, 36 + 18 * i), line, fontsize=8)
    page = doc.new_page()
    second = [
        "Data lançamento",
        "Descrição do lançamento",
        "01/07/2026",
        "Saldo de abertura",
        "100,00",
        "Fale com nossa central",
    ]
    for i, line in enumerate(second):
        page.insert_text((28, 36 + 18 * i), line, fontsize=8)
    content = doc.tobytes()
    doc.close()
    return content


def test_734_tem_somente_btg_e_conta_510():
    cap = CAPABILITIES[734]
    assert cap["banks"] == {"btg": "510"}
    assert [role["name"] for role in cap["roles"]] == ["btg"]
    assert cap["roles"][0]["accept"] == ".pdf"
    assert cap["roles"][0]["multiple"] is True
    assert CAPABILITIES[1402]["banks"]["btg"] == "510"


def test_leitor_btg_confere_totais_saldos_e_multilinhas():
    result = read_bank_pdf("btg", btg_pdf(), "extrato.pdf")
    assert len(result) == 2
    assert result["VALOR"].tolist() == [100, -50]
    assert result["DÉBITO"].tolist() == ["510", ""]
    assert result["CRÉDITO"].tolist() == ["", "510"]
    assert "Banco 341" in result.iloc[0]["HISTÓRICO"]
    assert "Saldo" not in " ".join(result["HISTÓRICO"])


def test_btg_recusa_saldo_que_nao_fecha_e_arquivo_invalido():
    with pytest.raises(ValueError, match="não conferem"):
        read_bank_pdf("btg", btg_pdf(with_bad_total=True), "extrato.pdf")
    with pytest.raises(ValueError, match="PDF"):
        read_bank_pdf("btg", b"not pdf", "extrato.xlsx")
    with pytest.raises(ValueError, match="somente o BTG"):
        read_bank_pdf("bradesco", btg_pdf(), "extrato.pdf")


def test_modelo_734_tem_uma_aba_btg_e_respeita_periodo():
    result, filename = _workflow(734, {"btg": [("extrato.pdf", btg_pdf())]}, {
        "data_inicial": "2026-07-01", "data_final": "2026-07-31",
    })
    assert filename == "RAZYNC_734_BTG_510_MODELO_DOMINIO.xlsx"
    wb = load_workbook(io.BytesIO(result))
    assert any("BTG 510" in name for name in wb.sheetnames)
    assert not any("Bradesco" in name for name in wb.sheetnames)
    with pytest.raises(ValueError, match="período"):
        workflow_734({"btg": [("extrato.pdf", btg_pdf())]}, {
            "data_inicial": "2026-08-01", "data_final": "2026-08-31",
        })


def test_upload_repetido_recusado_e_bradesco_adiado():
    file = btg_pdf()
    with pytest.raises(ValueError, match="mais de uma vez"):
        workflow_734({"btg": [("a.pdf", file), ("b.pdf", file)]}, {})
    with pytest.raises(ValueError, match="somente para o BTG"):
        workflow_734({"bradesco": [("bradesco.pdf", file)]}, {})


def test_remove_cpf_mascarado_mantendo_nome_banco_e_mensagem():
    source = "Pix recebido de CLIENTE TESTE Banco 341 | CPF ***.558.948-** | Mensagem - consulta julho"
    cleaned = _clean_history(source)
    assert "CPF" not in cleaned
    assert "558.948" not in cleaned
    assert "CLIENTE TESTE" in cleaned
    assert "Banco 341" in cleaned
    assert "Mensagem - consulta julho" in cleaned


def test_remove_cpf_completo_e_sem_pontuacao():
    assert "123.456.789-09" not in _clean_history("Pagamento CPF 123.456.789-09 referente junho")
    assert "12345678909" not in _clean_history("CPF 12345678909 Pix recebido")
    assert _clean_history("Rendimento Remunera+") == "Rendimento Remunera+"


def test_historico_do_excel_734_nao_contem_cpf():
    # Usa o mesmo formato de PIX e CPF mascarado presente no extrato real.
    from app.bank_734 import _clean_history
    history = _clean_history("Pix recebido de CLIENTE Banco 341 | CPF ***.558.948-** | Mensagem - julho")
    assert "CPF" not in history
    assert "Mensagem - julho" in history


def test_btg_descarta_debito_e_credito_na_conta_corrente_sem_descartar_outros():
    from app.bank_734 import _skip_current_account_transfer
    assert _skip_current_account_transfer("Débito na conta corrente")
    assert _skip_current_account_transfer("Credito na conta corrente")
    assert _skip_current_account_transfer("Crédito na conta corrente - movimento BTG")
    assert _skip_current_account_transfer("  DEBITO  NA CONTA CORRENTE ")
    assert not _skip_current_account_transfer("Pix recebido na conta corrente")
    assert not _skip_current_account_transfer("Pagamento de Conta / Tributo")
    assert not _skip_current_account_transfer("Rendimento Remunera+")


def test_btg_exclui_movimentos_somente_depois_de_validar_saldo(monkeypatch):
    from app import bank_734
    base = [
        {"DESCRIÇÃO": "BANCO BTG", "DATA": pd.Timestamp("2026-07-03"), "VALOR": 200,
         "DÉBITO": "510", "CRÉDITO": "", "HISTÓRICO": "Credito na conta corrente"},
        {"DESCRIÇÃO": "BANCO BTG", "DATA": pd.Timestamp("2026-07-03"), "VALOR": -100,
         "DÉBITO": "", "CRÉDITO": "510", "HISTÓRICO": "Débito na conta corrente"},
        {"DESCRIÇÃO": "BANCO BTG", "DATA": pd.Timestamp("2026-07-04"), "VALOR": -50,
         "DÉBITO": "", "CRÉDITO": "510", "HISTÓRICO": "Pix enviado"},
    ]
    monkeypatch.setattr(bank_734, "_parse_pdf", lambda pdf: base)
    result = read_bank_pdf("btg", btg_pdf(), "extrato.pdf")
    assert len(result) == 1
    assert result.iloc[0]["HISTÓRICO"] == "Pix enviado"
    assert result.iloc[0]["CRÉDITO"] == "510"


def modern_btg_pdf():
    """Fixture sem dados bancários pessoais do novo layout BTG."""
    doc = fitz.open()
    page = doc.new_page()
    lines = [
        "Resumo do saldo", "Saldo total", "Saldo de abertura", "01/09/2026",
        "R$ 1.000,00", "Saldo de fechamento", "30/09/2026", "R$ 1.030,00",
        "Total de entradas", "R$ 150,00", "Total de saídas", "R$ 120,00",
        "Lançamentos", "Data de", "lançamento", "Descrição do lançamento",
        "Entradas/Saídas", "Saldo", "30/09/2026", "Saldo de fechamento", "R$ 1.030,00",
        "30/09/2026", "Pix recebido de CLIENTE EXEMPLO", "CPF ***.123.456-**",
        "R$ 150,00", "R$ 1.030,00", "29/09/2026", "Débito na Conta Corrente",
        "- R$ 100,00", "R$ 880,00", "29/09/2026", "Pagamento de Tributo",
        "- R$ 20,00", "R$ 980,00", "R$ 0", "R$ 50.000",
        "Extrato conta corrente", "Período de 01/09/2026 a 30/09/2026",
    ]
    for index, line in enumerate(lines):
        page.insert_text((25, 30 + 13 * index), line, fontsize=8)
    result = doc.tobytes()
    doc.close()
    return result


def test_novo_layout_btg_extrato_conta_corrente_com_valores_r_ou_sinal():
    from app.bank_734 import _parse_pdf
    raw = _parse_pdf(modern_btg_pdf())
    assert len(raw) == 3
    assert sum(round(row["VALOR"] * 100) for row in raw) == 3000
    output = read_bank_pdf("btg", modern_btg_pdf(), "EXTRATOS.pdf")
    assert len(output) == 2
    assert output["VALOR"].tolist() == [150.0, -20.0]
    assert all("CPF" not in history for history in output["HISTÓRICO"])
    assert output["DÉBITO"].tolist() == ["510", ""]
    assert output["CRÉDITO"].tolist() == ["", "510"]


def test_btg_inverte_aplicacao_resgate_e_remove_rendimento(monkeypatch):
    from app import bank_734
    def transaction(history, amount):
        return {"DESCRIÇÃO":"BANCO BTG","DATA":pd.Timestamp("2026-09-01"),
                "VALOR":amount,"DÉBITO":"510" if amount > 0 else "",
                "CRÉDITO":"510" if amount < 0 else "","HISTÓRICO":history}
    rows = [transaction("Valor de Rendimento Remunera+", 0.27),
            transaction("Aplicação Conta Remunerada", 200),
            transaction("Resgate Conta Remunerada", -75),
            transaction("Pix enviado", -120),
            transaction("Débito na Conta Corrente", -200)]
    monkeypatch.setattr(bank_734, "_parse_pdf", lambda _: rows)
    result = read_bank_pdf("btg", btg_pdf(), "extrato.pdf")
    assert result["VALOR"].tolist() == [-200, 75, -120]
    assert result["DÉBITO"].tolist() == ["", "510", ""]
    assert result["CRÉDITO"].tolist() == ["510", "", "510"]


def test_modelo_btg_734_nao_prefixa_aplicacao_resgate(monkeypatch):
    from app import bank_734
    def movement(history, amount):
        return {"DESCRIÇÃO":"BANCO BTG","DATA":pd.Timestamp("2026-09-01"),
                "VALOR":amount,"DÉBITO":"510" if amount > 0 else "",
                "CRÉDITO":"510" if amount < 0 else "", "HISTÓRICO":history}
    rows = [movement("Aplicação Conta Remunerada", -100),
            movement("Resgate Conta Remunerada", 50),
            movement("Pix recebido", 35),
            movement("Pagamento de conta", -15)]
    monkeypatch.setattr(bank_734, "_parse_pdf", lambda _: rows)
    data, _ = workflow_734({"btg":[("extrato.pdf",btg_pdf())]}, {})
    wb = load_workbook(io.BytesIO(data))
    histories = [row[5] for row in list(wb.active.values)[1:]]
    assert histories[:2] == ["Aplicação Conta Remunerada", "Resgate Conta Remunerada"]
    assert histories[2].startswith("Recebido:")
    assert histories[3].startswith("Pago:")

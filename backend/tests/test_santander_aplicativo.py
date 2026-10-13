"""Regressões: Santander Aplicativo Empresas, sinais e históricos multilinha."""
import pytest

from app import engine
from app.migration_services import statement
from app import santander_aplicativo as novo
from razync.santander_statement import (
    parece_extrato_santander_empresarial,
    processar_extrato_santander_empresarial_texto,
)


def texto_exemplo():
    return """Aplicativo Santander Empresas
Empresa Fictícia Ltda Agência: 0000 Conta: 000000000
Períodos: 01/09/2026 a 30/09/2026
Data Histórico Documento Valor (R$) Saldo (R$)
30/09/2026 Cr Cob Bloq Comp Conf Recebimento
REFERENCIA123 200,00 1.200,00
29/09/2026 Pix Enviado Fornecedor Exemplo -100,00 1.000,00
28/09/2026 Pagamento De Boleto Outros Bancos 0000000000
100,00 1.100,00
CLIENTE COMPLEMENTAR
27/09/2026 Rendimento Liquido De Contamax 7000
RENDIMENTO LIQUIDO DE CONTAMAX 1.000,00 1.000,00
Saldo de ContaMax 1.050,00
Saldo Disponível 0,00
Saldo
Posição em: 01/10/2026
A – Saldo de Conta Corrente 5.000,00
"""


def test_santander_app_novo_layout_multilinha_e_saldos():
    texto = texto_exemplo()
    assert novo.parece_extrato_santander_aplicativo(texto)
    rows = novo.processar_extrato_santander_aplicativo_texto(texto)
    assert len(rows) == 4
    assert [x["VALOR"] for x in rows] == [200.0, -100.0, 100.0, 1000.0]
    assert all(set(x) == {"DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"} for x in rows)
    assert "CLIENTE COMPLEMENTAR" in rows[2]["HISTÓRICO"]
    assert "REFERENCIA123" in rows[0]["HISTÓRICO"]
    assert "Saldo" not in rows[-1]["HISTÓRICO"]


def test_santander_app_historico_apos_quebra_de_pagina():
    text = texto_exemplo().replace(
        "28/09/2026 Pagamento De Boleto Outros Bancos 0000000000\n100,00 1.100,00\nCLIENTE COMPLEMENTAR",
        "28/09/2026 Pagamento De Boleto Outros Bancos 0000000000\n"
        "100,00 1.100,00\n1/5\nCLIENTE COMPLEMENTAR",
    )
    rows = novo.processar_extrato_santander_aplicativo_texto(text)
    assert "CLIENTE COMPLEMENTAR" in rows[2]["HISTÓRICO"]
    assert len(rows) == 4


def test_santander_app_nao_omite_lancamento_quando_saldos_nao_batem():
    text = texto_exemplo().replace("100,00 1.100,00", "99,99 1.100,00")
    with pytest.raises(ValueError, match="sequência de saldos"):
        novo.processar_extrato_santander_aplicativo_texto(text)


def test_santander_app_nao_confunde_saldo_da_pagina_com_transacao():
    text = texto_exemplo().replace(
        "Saldo de ContaMax 1.050,00",
        "Saldo de ContaMax 1.050,00\nSaldo disponível 1.050,00\n01/10/2026 10,00 3.000,00",
    )
    rows = novo.processar_extrato_santander_aplicativo_texto(text)
    assert len(rows) == 4
    assert rows[0]["DATA"] == "30/09/2026"


def test_layout_anterior_santander_continua_funcionando():
    antigo = """Santander
Internet Banking Empresarial
30/07/2026 Saldo do dia R$ 999,99
30/07/2026 Pix Enviado TESTE - R$ 50,00
30/07/2026 Pix Recebido TESTE R$ 120,00
"""
    assert not novo.parece_extrato_santander_aplicativo(antigo)
    assert parece_extrato_santander_empresarial(antigo)
    valores = [i["VALOR"] for i in processar_extrato_santander_empresarial_texto(antigo)]
    assert valores == [-50.0, 120.0]


def test_santander_app_aceito_na_conferencia_de_empresa_santander(monkeypatch):
    text = texto_exemplo()
    class Page:
        def extract_text(self): return text
    class Reader:
        pages = [Page()]
    monkeypatch.setattr(novo, "PdfReader", lambda *args, **kwargs: Reader())
    monkeypatch.setattr(engine, "PdfReader", lambda *args, **kwargs: Reader())
    frame = statement(285, "santander", b"%PDF-mock-only", "santander.pdf")
    assert len(frame) == 4
    assert frame["VALOR"].sum() == 1200.0
    assert frame["HISTÓRICO"].str.contains("CLIENTE COMPLEMENTAR").sum() == 1

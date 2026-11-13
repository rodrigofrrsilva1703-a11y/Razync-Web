"""Regressões sintéticas da empresa 799: Santander, Bradesco OCR e contas."""
from unittest.mock import patch
import pandas as pd
import pytest

from app.company_799 import parse_bradesco_text, read_santander, workflow_799
from app import migration_services as services


SANTANDER = """Aplicativo Santander Empresas
UROCABRAL SERVICOS MEDICOS LTDA.
Agência: 4354
Conta: 130032285
Períodos: 01/08/2026 a 31/08/2026
Data/Hora: 31/08/2026 as 11h47
Saldo disponível para uso: R$ 9.049,01
Data
Histórico
Documento
Valor (R$)
Saldo (R$)
10/08/2026 Ted Recebida 57596645000156
2.700,06
2.769,89
07/08/2026 Rendimento Liquido De Contamax 7000
RENDIMENTO LIQUIDO DE CONTAMAX
0,03
69,83
07/08/2026 Tarifa Mensalidade Pacote Servicos
JULHO / 2026
-237,00
69,80
Saldo de ContaMax
2.770,01
Saldo Disponível
0,00
Saldo
Posição em: 31/08/2026
"""

BRADESCO = """REDE BRADESCO - CONSULTA DE SALDO
UROCABRAL SERVICOS MEDICOS LTDA. 12:13 HRS
AGENCIA 7732 CONTA 0024739-1 31/AGO/2026
-----Julho/2026-----
DIA HISTORICO N.DOCTO VALOR
31 SALDO ANTERIOR 0,00
-----AgostO/2026-----
DIA HISTORICO N.DOCTO VALOR
04 RENT. INV.FACIL 8624216 0,02
PAGTO COBRANCA 0000138 520,00-
JAGUAR
SALDO EM 04/08 27.180,15
13 RENT. INV.FACIL 8624216 0,03
CONTA TELEFONE 9847835 280,11-
VIVO MOVEL-SP-21398478352
SALDO EM 13/08 26.900,07
14 RENT. INV.FACIL 8624216 0,02
TARIFA BANCARIA 0030826 183,60-
CestaEmpresarial2
SALDO EM 14/08 26.716,49
20 TED-T ELET DISP 8496223 50.961,52
REMET.HOSPITAL E MATERNIDA
SALDO EM 20/08 77.678,01
21 APLICACAO CDB 2327732 1,00
RENT. INV.FACIL 6301396 0,03
RENT. INV.FACIL 8624216 5,18
APLICACAO CDB 2337732 77.683,22-
SALDO EM 21/08 1,00
24 APLICACAO CDB 2337732 334,06
APLICACAO CDB 2337732 56.219,75
PAGTO COBRANCA 0000139 7.553,61-
JAGUAR PJ
TRANSF CONTAS 7732553 49.000,00-
OSWALDO FARIA DE PAULA CAB
SALDO EM 24/08 1,00
"""


class DummyPage:
    def __init__(self,text):self.text=text
    def get_text(self):return self.text


class DummyDoc:
    def __init__(self,text):self.pages=[DummyPage(text)]
    def __len__(self):return len(self.pages)
    def __iter__(self):return iter(self.pages)
    def __getitem__(self,index):return self.pages[index]
    def __enter__(self):return self
    def __exit__(self,*args):return False


def test_santander_three_movements_signed_and_ordered():
    with patch("app.company_799.fitz.open",return_value=DummyDoc(SANTANDER)):
        frame=read_santander(b"%PDF synthetic")
    assert frame["VALOR"].tolist()==[-237.0,0.03,2700.06]
    assert frame["CRÉDITO"].tolist()==["513","",""]
    assert frame["DÉBITO"].tolist()==["","513","513"]
    assert "57596645000156" not in frame.iloc[2]["HISTÓRICO"]


def test_santander_rejects_mismatching_bank_balance():
    wrong=SANTANDER.replace("2.769,89","2.769,88")
    with patch("app.company_799.fitz.open",return_value=DummyDoc(wrong)):
        with pytest.raises(ValueError,match="saldo não confere"):
            read_santander(b"%PDF synthetic")


def test_bradesco_15_movements_and_all_daily_balances():
    rows=parse_bradesco_text(BRADESCO)
    assert len(rows)==15
    assert sum(value for _,value,_ in rows if value>0)==10714264
    assert any(row[1]==-755381 for row in rows)
    assert rows[-1][1]==-4900000


def test_bradesco_rejects_wrong_balance_and_wrong_account():
    with pytest.raises(ValueError,match="OCR não conferiu saldo"):
        parse_bradesco_text(BRADESCO.replace("26.900,07","26.900,08"))
    with pytest.raises(ValueError,match="agência ou conta"):
        parse_bradesco_text(BRADESCO.replace("0024739-1","0024739-2"))


def _fake(account,bank):
    return pd.DataFrame([{"DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-08-07"),
        "VALOR":-10.0,"DÉBITO":"","CRÉDITO":account,"HISTÓRICO":"Pago: TESTE"}])


def test_799_workflow_keeps_bank_tabs_and_accounts():
    from app import company_799
    with patch.object(company_799,"read_bradesco",return_value=_fake("9","BANCO BRADESCO")), \
         patch.object(company_799,"read_santander",return_value=_fake("513","BANCO SANTANDER")), \
         patch("app.excel.gerar_modelo_abas",return_value=b"xlsx") as exporter:
        content,name=workflow_799({"bradesco":[("a.pdf",b"%PDF")],
                                    "santander":[("b.pdf",b"%PDF")]},{})
    assert content==b"xlsx" and "799" in name
    sheets=exporter.call_args.args[0]
    assert sheets["Bradesco"]["CRÉDITO"].tolist()==["9"]
    assert sheets["Santander"]["CRÉDITO"].tolist()==["513"]


def test_799_routes_banks_and_rejects_wrong_bank():
    from app import company_799
    with patch.object(company_799,"read_bradesco",return_value=_fake("9","BANCO BRADESCO")) as reader:
        services.statement(799,"bradesco",b"%PDF","a.pdf")
        reader.assert_called_once()
    with patch.object(company_799,"read_santander",return_value=_fake("513","BANCO SANTANDER")) as reader:
        services.statement(799,"santander",b"%PDF","b.pdf")
        reader.assert_called_once()
    with pytest.raises(ValueError,match="banco não cadastrado"):
        services.statement(799,"itau",b"%PDF","c.pdf")
    with patch.object(company_799,"workflow_799",return_value=(b"xlsx","799.xlsx")):
        assert services._workflow(799,{}, {})==(b"xlsx","799.xlsx")

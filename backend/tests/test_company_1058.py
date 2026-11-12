"""Cobertura da empresa 1058 sem anexar dados reais de clientes ao Git."""
from datetime import datetime
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest

from app.company_1058 import read_itau, read_caixa


def synthetic_excel():
    data = [[None] * 6 for _ in range(6)]
    data += [[None, 'DATA', 'TIPO', 'FAVORECIDO', 'VALOR', 'DESCRIÇÃO']]
    data += [[None, 46237, 'Boletos de cobrança', 'FORNECEDOR TESTE', 123.45, 'Serviço']]
    data += [[None, 46238, 'Crédito em conta', 'BENEFICIARIO TESTE', 200.00, 'Transferencia']]
    output=BytesIO()
    pd.DataFrame(data).to_excel(output,index=False,header=False)
    return output.getvalue()


def test_itau_credito_em_conta_e_saida_na_conta_origem():
    frame = read_itau(synthetic_excel())
    assert frame['VALOR'].tolist() == [-123.45,-200.0]
    assert frame['CRÉDITO'].tolist() == ['514','514']
    assert all(value.startswith('Pago: ') for value in frame['HISTÓRICO'])
    assert frame['DATA'].dt.strftime('%d/%m/%Y').tolist() == ['03/08/2026','04/08/2026']


def test_caixa_valida_saldo_e_ignora_saldo_dia():
    from unittest.mock import MagicMock
    text = '''Extrato por período
Cliente: QUARTETO DE OBRAS LTDA
Conta: 4115 | 1292 | 000578789424-0
Mês: Abril/2026
Extrato
Data Mov. Nr. Doc. Histórico Valor Saldo
27/04/2026000000 TAR MAN CC 71,33 D 0,03 D
27/04/2026000000 RESG AUT 0,03 C 0,00 C
27/04/2026000000 SALDO DIA 0,00 C 0,00 C'''
    with patch('app.company_1058.PdfReader') as reader:
        reader.return_value.pages = [MagicMock(extract_text=lambda: text)]
        frame = read_caixa(b'%PDF synthetic')
    assert frame['VALOR'].tolist() == [-71.33,0.03]
    assert frame['CRÉDITO'].tolist() == ['504','']
    assert frame['DÉBITO'].tolist() == ['', '504']


def test_caixa_rejeita_saldo_divergente():
    from unittest.mock import MagicMock
    text = '''Extrato por período
Cliente: QUARTETO DE OBRAS LTDA
Conta: 4115 | 1292 | 000578789424-0
Mês: Abril/2026
Extrato
Data Mov. Nr. Doc. Histórico Valor Saldo
27/04/2026000000 TAR MAN CC 71,33 D 0,03 D
27/04/2026000000 RESG AUT 0,03 C 0,01 C'''
    with patch('app.company_1058.PdfReader') as reader:
        reader.return_value.pages = [MagicMock(extract_text=lambda: text)]
        with pytest.raises(ValueError,match='Saldo bancário'):
            read_caixa(b'%PDF synthetic')


def test_1058_usa_workflow_especifico():
    from app.migration_services import _workflow
    with patch('app.company_1058.workflow_1058', return_value=(b'file','ok.xlsx')) as process:
        assert _workflow(1058, {'itau': [],'caixa': []}, {}) == (b'file','ok.xlsx')
    process.assert_called_once()

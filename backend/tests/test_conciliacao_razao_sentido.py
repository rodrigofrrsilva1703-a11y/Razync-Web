import io

import pandas as pd

from app.engine import processar_razao_dominio
from app.global_tools import conciliar_razao


def test_conciliacao_razao_bancario_debito_entrada_credito_saida():
    original = pd.DataFrame([
        {"DATA": "08/04/2026", "HISTÓRICO": "Cliente", "DÉBITO": "1.500,00", "CRÉDITO": ""},
        {"DATA": "08/04/2026", "HISTÓRICO": "Fornecedor", "DÉBITO": "", "CRÉDITO": "350,00"},
    ])
    data = io.BytesIO()
    original.to_excel(data, index=False)
    razao = processar_razao_dominio(data.getvalue(), "Razao.xlsx")

    assert razao is not None
    assert razao["ENTRADAS_RAZAO"].sum() == 1500
    assert razao["SAIDAS_RAZAO"].sum() == 350

    extrato = pd.DataFrame([
        {"DATA": "08/04/2026", "VALOR": 1500, "HISTÓRICO": "Crédito cliente"},
        {"DATA": "08/04/2026", "VALOR": -350, "HISTÓRICO": "Débito fornecedor"},
    ])
    diario, resumo = conciliar_razao(extrato, razao)
    assert diario.iloc[0]["SITUAÇÃO"] == "CONFERE"
    assert resumo["dias_conferidos"] == 1
    assert resumo["entradas_razao"] == 1500
    assert resumo["saidas_razao"] == 350

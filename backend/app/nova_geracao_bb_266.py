"""Processamento Banco do Brasil da empresa 266 (Nova Geração).

Conta do extrato/relatório: 200076-8. Conta contábil Domínio: 8.
Mantém o leitor original da Nova Geração e valida a conta por igualdade exata,
sem confundir movimentações de outros bancos presentes no mesmo relatório.
"""
from __future__ import annotations

import pandas as pd

from app import engine

CONTA_BANCARIA = "200076-8"
CONTA_CONTABIL = "8"
ABA_MODELO = "Banco do Brasil 200076-8"


def processar_nova_geracao_bb_266(content: bytes):
    principal, retirados = engine.processar_nova_geracao_banco(
        content, "Banco do Brasil", CONTA_BANCARIA, "BANCO DO BRASIL"
    )

    def identificar_conta(frame: pd.DataFrame) -> pd.DataFrame:
        resultado = frame.copy()
        if not resultado.empty:
            # Entradas debitam o banco; saídas creditam o banco.
            valores = pd.to_numeric(resultado["VALOR"], errors="raise")
            resultado["DÉBITO"] = valores.apply(
                lambda valor: CONTA_CONTABIL if valor > 0 else ""
            )
            resultado["CRÉDITO"] = valores.apply(
                lambda valor: CONTA_CONTABIL if valor < 0 else ""
            )
        return resultado

    return identificar_conta(principal), identificar_conta(retirados)

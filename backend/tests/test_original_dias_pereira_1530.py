from pathlib import Path

import pandas as pd

from razync.dias_pereira_1530 import (
    CONTA_ITAU_1530,
    processar_extrato_itau_xls_1530,
)


ARQUIVO_REAL = Path(
    "/workspace/scratch/5e34a0486359/upload/Extrato_0775-984586-07-2026 BAHIA.xls"
)


def test_le_extrato_itau_xls_real_quando_disponivel():
    if not ARQUIVO_REAL.exists():
        return
    resultado = processar_extrato_itau_xls_1530(ARQUIVO_REAL.read_bytes())

    assert not resultado.empty
    assert not resultado["HISTÓRICO"].str.contains("SALDO", case=False).any()
    assert set(resultado.loc[resultado["VALOR"] > 0, "DÉBITO"]) == {CONTA_ITAU_1530}
    assert set(resultado.loc[resultado["VALOR"] < 0, "CRÉDITO"]) == {CONTA_ITAU_1530}
    assert resultado["DATA"].min() == pd.Timestamp("2026-07-02")
    assert resultado["DATA"].max() == pd.Timestamp("2026-07-31")



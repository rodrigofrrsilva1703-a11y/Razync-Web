"""Regression tests for the Base Inteligente XLS/BIFF import path.

No customer ledger or bank records are stored in this repository.
"""
from io import BytesIO

import pandas as pd
import pytest

from app import classification_service
from razync.dominio_ledger import _ler_bruto, ler_razao_dominio_base


def _ledger_xlsx():
    frame = pd.DataFrame([
        ["DATA", "HISTÓRICO", "Cta.CPart", "DÉBITO", "CRÉDITO"],
        ["Conta", "8", None, None, None],
        ["03/07/2026", "Pagamento de fornecedor", "166", None, 125.60],
    ])
    buffer = BytesIO()
    frame.to_excel(buffer,index=False,header=False)
    return buffer.getvalue()


def test_mislabeled_xlsx_as_xls_is_read_by_signature():
    content = _ledger_xlsx()
    assert content.startswith(b"PK\x03\x04")
    table = _ler_bruto(content, "Razão 1167.xls")
    assert table is not None
    assert table.iloc[0, 0] == "DATA"
    records = ler_razao_dominio_base(
        content, "Razão 1167.xls", {"banco_brasil":"8"})
    assert len(records) == 1
    assert records[0]["banco"] == "banco_brasil"
    assert records[0]["debito"] == "166"
    assert records[0]["credito"] == "8"


def test_classification_ingests_ledger_without_exposing_bof():
    content = _ledger_xlsx()
    records = classification_service._learning_records(
        1167, content, "Razão 1167.xls")
    assert len(records) == 1
    assert records[0]["banco"] == "banco_brasil"
    assert records[0]["periodos"] == ["2026-07"]


def test_corrupt_xls_gives_actionable_message_and_imports_nothing():
    # BOF is at an invalid offset, the report cannot be reconstructed.
    invalid = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00"*128 + b"\x01\x02\x06\x00"
    with pytest.raises(ValueError,match="Nenhum lançamento foi aprendido"):
        classification_service._learning_records(
            1167,invalid,"Razão 1167.xls")

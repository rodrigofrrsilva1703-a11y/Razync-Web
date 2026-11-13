"""Unit tests without storing client statements or spreadsheets in Git."""
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from app.empresa_1024 import enrich


class Empresa1024Tests(unittest.TestCase):
    def test_workflow_dispatch_uses_company_1024(self):
        from app.migration_services import _workflow
        with patch("app.empresa_1024.workflow_1024", return_value=(b"file", "1024.xlsx")) as processor:
            result = _workflow(1024, {"extrato": [], "planilha": []}, {})
        self.assertEqual(result, (b"file", "1024.xlsx"))
        processor.assert_called_once()

    def test_unique_value_replaces_only_history(self):
        frame = pd.DataFrame([{
            "DESCRIÇÃO": "BANCO DO BRASIL",
            "DATA": pd.Timestamp("2026-08-03"),
            "VALOR": -678.05, "DÉBITO": "", "CRÉDITO": "",
            "HISTÓRICO": "Pagamento de Boleto",
        }])
        ledger = [{"date": date(2026, 8, 3), "cents": -67805,
                   "history": "Sala 303 - Administradora", "row": 3}]
        with patch("app.empresa_1024._statement", return_value=(frame, (2026, 8))), patch(
            "app.empresa_1024._ledger", return_value=ledger
        ):
            result, matched, pending = enrich(b"pdf", b"sheet")
        self.assertEqual(result.loc[0, "HISTÓRICO"], "Sala 303 - Administradora")
        self.assertEqual(result.loc[0, "VALOR"], -678.05)
        self.assertEqual(len(matched), 1)
        self.assertTrue(pending.empty)

    def test_ambiguous_amount_keeps_original(self):
        frame = pd.DataFrame([
            {"DATA": pd.Timestamp("2026-08-03"), "VALOR": -100.0, "HISTÓRICO": "Original A"},
            {"DATA": pd.Timestamp("2026-08-03"), "VALOR": -100.0, "HISTÓRICO": "Original B"},
        ])
        ledger = [{"date": date(2026, 8, 3), "cents": -10000,
                   "history": "Outra descrição", "row": 3}]
        with patch("app.empresa_1024._statement", return_value=(frame, (2026, 8))), patch(
            "app.empresa_1024._ledger", return_value=ledger
        ):
            result, matched, pending = enrich(b"pdf", b"sheet")
        self.assertEqual(result["HISTÓRICO"].tolist(), ["Original A", "Original B"])
        self.assertTrue(matched.empty)
        self.assertEqual(len(pending), 1)

    def test_three_components_preserve_bank_amount(self):
        frame = pd.DataFrame([{
            "DATA": pd.Timestamp("2026-08-24"), "VALOR": -3432.03,
            "HISTÓRICO": "Pix - Enviado MAYARA",
        }])
        ledger = [
            {"date": date(2026, 8, 24), "cents": -225437, "history": "Mayara salário", "row": 26},
            {"date": date(2026, 8, 24), "cents": -25960, "history": "Mayara transporte", "row": 27},
            {"date": date(2026, 8, 24), "cents": -91806, "history": "Mayara refeição", "row": 28},
        ]
        with patch("app.empresa_1024._statement", return_value=(frame, (2026, 8))), patch(
            "app.empresa_1024._ledger", return_value=ledger
        ):
            result, matched, pending = enrich(b"pdf", b"sheet")
        self.assertEqual(result.loc[0, "VALOR"], -3432.03)
        self.assertIn("Mayara transporte", result.loc[0, "HISTÓRICO"])
        self.assertEqual(len(matched), 3)
        self.assertTrue(pending.empty)


if __name__ == "__main__":
    unittest.main()

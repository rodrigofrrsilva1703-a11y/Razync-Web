"""Report of Caixa payments used by company 521."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from app.excel import COLUNAS

ACCOUNT = "5"
HEADERS = ("data de pagamento", "categoria", "nome fornecedor (razão social)", "valor (r$)", "observações")


def clean(value):
    return " ".join(str(value if value is not None else "").split())


def read_payments(content, *, optional=False):
    book = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        sheet = next((tab for tab in book if tab.title.strip().casefold() == "caixa"), None)
        if sheet is not None:
            rows = enumerate(sheet.values, 1)
            for line, row in rows:
                columns = {clean(value).casefold(): i for i, value in enumerate(row) if clean(value)}
                if set(HEADERS).issubset(columns):
                    break
                if line >= 20:
                    sheet = None
                    break
            else:
                sheet = None
        if sheet is None:
            if optional:
                return None
            raise ValueError("O arquivo precisa ter a aba Caixa com o cabeçalho do relatório de pagamentos.")

        payments = []
        for line, row in rows:
            payment_date, category, supplier, value, notes = (row[columns[key]] for key in HEADERS)
            if payment_date is None and value is None:
                continue
            if payment_date is None and clean(supplier or category).casefold() in {"total", "total geral", "subtotal"}:
                continue
            try:
                if isinstance(payment_date, datetime):
                    payment_date = payment_date.date()
                elif not isinstance(payment_date, date):
                    payment_date = datetime.strptime(clean(payment_date), "%d/%m/%Y").date()
                amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if not amount.is_finite() or amount <= 0:
                    raise ValueError()
            except (ValueError, TypeError, InvalidOperation) as exc:
                raise ValueError(f"Aba Caixa, linha {line}: confira a data e o valor do pagamento.") from exc
            history = " - ".join(filter(None, (clean(supplier), clean(category), clean(notes))))
            if not history:
                raise ValueError(f"Aba Caixa, linha {line}: informe o fornecedor ou a categoria.")
            payments.append(("CAIXA", pd.Timestamp(payment_date), float(-amount), "", ACCOUNT, f"Pago: {history}"))
        if not payments:
            raise ValueError("A aba Caixa não contém pagamentos.")
        return pd.DataFrame(payments, columns=COLUNAS).sort_values("DATA", kind="stable")
    finally:
        book.close()

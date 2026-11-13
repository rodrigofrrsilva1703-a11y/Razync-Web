import io
from datetime import datetime
from openpyxl import Workbook
from fastapi.testclient import TestClient
from app.main import app


def test_preview_reads_exported_dates_accounts_and_complete_totals():
    book = Workbook()
    sheet = book.active
    sheet.title = 'Itaú'
    sheet.append(['DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO'])
    for index in range(501):
        sheet.append([datetime(2026, 7, 9), 10 if index < 500 else -5, '508', '12', 'MOVIMENTO'])
    content = io.BytesIO()
    book.save(content)
    response = TestClient(app).post('/api/v1/modelo-preview', files={'file': ('modelo.xlsx', content.getvalue())})
    assert response.status_code == 200
    sheet = response.json()['sheets'][0]
    assert sheet['count'] == 501
    assert len(sheet['rows']) == 500
    assert sheet['rows'][0] == ['09/07/2026', 10, '508', '12', 'MOVIMENTO']
    assert sheet['entradas'] == 5000
    assert sheet['saidas'] == 5

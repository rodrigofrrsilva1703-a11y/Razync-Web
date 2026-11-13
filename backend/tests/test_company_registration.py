from fastapi.testclient import TestClient
from app.main import app


def test_company_registration_persists_without_tools(monkeypatch):
    monkeypatch.setenv('RAZYNC_ACCESS_TOKEN', 'test-company-key')
    client = TestClient(app)
    headers = {'Authorization': 'Bearer test-company-key'}
    assert client.post('/api/v1/companies', json={'codigo': 999999}).status_code == 401
    response = client.post('/api/v1/companies', headers=headers, json={'codigo': '999999'})
    assert response.status_code == 201
    row = response.json()
    assert row['nome'] == 'Empresa 999999'
    assert row['capabilities']['tools'] == []
    assert row['capabilities']['status'] == 'catalog_only'
    assert client.get('/api/v1/companies/999999').json()['nome'] == row['nome']
    assert any(item['codigo'] == 999999 for item in client.get('/api/v1/companies').json())
    assert client.post('/api/v1/companies', headers=headers, json={'codigo': 999999}).status_code == 409
    assert client.post('/api/v1/companies', headers=headers, json={'codigo': 626}).status_code == 409
    for code in [0, -1, 'abc', True, 1000000000]:
        assert client.post('/api/v1/companies', headers=headers, json={'codigo': code}).status_code == 422

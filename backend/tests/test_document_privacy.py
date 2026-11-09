from io import BytesIO

from openpyxl import Workbook
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import document_privacy, organizer_jobs, result_artifacts, site_access


def test_only_minimized_evidence_leaves_the_server():
    original = {"historico": "Pagamento [MARIA SOUZA] CPF 123.456.789-09 "
                "PIX conta 888-1 contato maria@example.test",
                "data": "01/09/2026", "valor": "R$ 1.220,55", "referencia": "L15",
                "documentos": [{"descricao": "Serviço de Acme", "cnpj": "12.ABC.123/0001-09", "cpf": 12345678909}]}
    safe = document_privacy.provider_context(original)
    for item in ("MARIA", "SOUZA", "123.456", "888-1", "example.test", "Acme", "12.ABC", "12345678909"):
        assert item not in str(safe)
    assert "Pagamento" in safe["historico"]
    assert "PIX" in safe["historico"]
    for key in ("data", "valor", "referencia"):
        assert safe[key] == original[key]
    assert "MARIA" in original["historico"]
    assert document_privacy.mask_identifiers("Pagamento Maria CPF 123 456 789 09") == "Pagamento Maria CPF [CPF]"


def test_two_authenticated_accounts_cannot_share_temporary_reports_or_jobs(monkeypatch):
    monkeypatch.setenv("RAZYNC_LOGIN_REQUIRED", "1")
    monkeypatch.setenv("RAZYNC_LOGIN_EMAILS", "one@example.test,two@example.test")
    monkeypatch.setenv("RAZYNC_AUTH_URL", "https://example.supabase.co")
    monkeypatch.setenv("RAZYNC_AUTH_PUBLIC_KEY", "test")
    monkeypatch.setattr(site_access, "verify_password", lambda *_: True)
    monkeypatch.setattr(site_access, "_sessions", site_access.OrderedDict())
    monkeypatch.setattr(site_access, "_attempts", site_access.OrderedDict())
    app = FastAPI()
    for router in (site_access.router, result_artifacts.router, organizer_jobs.router):
        app.include_router(router)
    app.add_middleware(site_access.SiteAccessMiddleware)

    @app.get("/report")
    def generate():
        return {"token": result_artifacts.store(b"synthetic export", "relatorio.xlsx")}

    workbook = Workbook()
    workbook.active.append(["DATA", "VALOR", "HISTÓRICO"])
    workbook.active.append(["01/09/2026", 15, "Pagamento fictício"])
    stream = BytesIO()
    workbook.save(stream)
    data = stream.getvalue()

    @app.get("/job")
    def queue():
        return organizer_jobs.submit(lambda: (data, "relatorio.xlsx"), len(data), 1)

    client = TestClient(app)
    def sign_in(name):
        return {"X-Razync-Session": client.post("/api/v1/acesso/entrar", json={
            "email": f"{name}@example.test", "password": "test"
        }).json()["session"]}

    one, two = sign_in("one"), sign_in("two")
    token = client.get("/report", headers=one).json()["token"]
    url = "/api/v1/resultados/" + token
    assert client.get(url).status_code == 401
    assert client.get(url, headers=two).status_code == 404
    assert client.get(url, headers=one).content == b"synthetic export"
    job = client.get("/job", headers=one).json()["job_token"]
    path = "/api/v1/organizador/" + job
    organizer_jobs._jobs[job]["future"].result(timeout=5)
    assert client.get(path, headers=one).json()["state"] == "ready"
    assert client.get(path, headers=two).status_code == 404
    assert client.get(path + "/resultado", headers=two).status_code == 404
    assert client.delete(path, headers=two).status_code == 404
    report_token = client.get(path + "/resultado", headers=one).json()["report_token"]
    report = "/api/v1/resultados/" + report_token
    assert client.get(report, headers=two).status_code == 404
    assert client.get(report, headers=one).content == data

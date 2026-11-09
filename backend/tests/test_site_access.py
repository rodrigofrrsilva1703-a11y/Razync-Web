import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import site_access


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RAZYNC_LOGIN_REQUIRED", "1")
    monkeypatch.setenv("RAZYNC_LOGIN_EMAILS", "owner@example.test")
    monkeypatch.setattr(site_access, "_sessions", site_access.OrderedDict())
    monkeypatch.setattr(site_access, "_attempts", site_access.OrderedDict())
    monkeypatch.setattr(site_access, "verify_password", lambda email, password: password == "test-password")
    app = FastAPI()
    app.include_router(site_access.router)
    app.add_middleware(site_access.SiteAccessMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/v1/tasks")
    def tasks(request: Request):
        return {"identity": request.state.site_email, "admin_header": request.headers.get("authorization")}

    @app.post("/api/v1/base-inteligente/969/aprender")
    def learn():
        pytest.fail("A chamada anônima chegou ao manipulador.")

    return TestClient(app)


def sign_in(client):
    r = client.post("/api/v1/acesso/entrar", json={"email": "OWNER@example.test", "password": "test-password"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    return {"X-Razync-Session": r.json()["session"]}


def test_private_mode_blocks_anonymous_reads_uploads_and_docs(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/acesso/config").json() == {"required": True}
    for method, path in [("GET", "/api/v1/tasks"), ("POST", "/api/v1/base-inteligente/969/aprender"), ("GET", "/docs")]:
        r = client.request(method, path, headers={"Authorization": "Bearer old-admin-key"})
        assert r.status_code == 401
        assert r.headers["x-razync-login-required"] == "1"


def test_session_preserves_separate_admin_header_and_logout_revokes_it(client):
    headers = sign_in(client)
    r = client.get("/api/v1/tasks", headers={**headers, "Authorization": "Bearer admin-test"})
    assert r.json() == {"identity": "owner@example.test", "admin_header": "Bearer admin-test"}
    assert r.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/acesso/sair", headers=headers).status_code == 200
    assert client.get("/api/v1/tasks", headers=headers).status_code == 401


def test_removed_email_loses_access_even_with_existing_session(client, monkeypatch):
    headers = sign_in(client)
    monkeypatch.setenv("RAZYNC_LOGIN_EMAILS", "")
    assert client.get("/api/v1/tasks", headers=headers).status_code == 401


def test_wrong_email_and_password_do_not_create_session_or_echo_credentials(client):
    for email, password in [("outside@example.test", "test-password"), ("owner@example.test", "wrong-password")]:
        r = client.post("/api/v1/acesso/entrar", json={"email": email, "password": password})
        assert r.status_code == 401
        assert password not in r.text and "session" not in r.json()
    r = client.post("/api/v1/acesso/entrar", json={"email": [], "password": "must-not-echo"})
    assert r.status_code == 400
    assert "must-not-echo" not in r.text

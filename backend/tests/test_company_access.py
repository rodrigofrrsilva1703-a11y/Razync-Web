import secrets
import sys
from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import company_access, site_access


def test_company_reassignment_updates_access_without_limiting_admins(monkeypatch, tmp_path):
    users = ("rodrigo@example.test", "admin@example.test", "regular@example.test", "other@example.test")
    monkeypatch.setenv("RAZYNC_LOGIN_EMAILS", ",".join(users))
    monkeypatch.setenv("RAZYNC_ADMIN_EMAILS", ",".join(users[:2]))
    monkeypatch.setenv("RAZYNC_DEFAULT_COMPANY_OWNER", users[0])
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    monkeypatch.setenv("RAZYNC_LOGIN_REQUIRED", "1")
    monkeypatch.setitem(sys.modules, "app.classification_service", SimpleNamespace(DB_PATH=tmp_path / "base.sqlite"))
    monkeypatch.setitem(sys.modules, "app.company_service", SimpleNamespace(catalog=lambda: [
        {"codigo": 3, "nome": "Empresa A"}, {"codigo": 8, "nome": "Empresa B"},
    ]))
    app = FastAPI(dependencies=[Depends(company_access.require_company_access)])
    app.add_middleware(site_access.SiteAccessMiddleware)
    app.include_router(company_access.router)

    @app.get("/api/v1/companies/{company_code}")
    def company(company_code: int):
        return {"codigo": company_code}

    @app.get("/api/v1/base-inteligente/{company_code}/status")
    def base_status(company_code: int):
        return {"learned": {3: 42, 8: 0}[company_code]}

    client = TestClient(app)

    def headers(email):
        token = secrets.token_urlsafe(32)
        site_access.save_session(token, email)
        return {"X-Razync-Session": token}

    other = headers(users[3])
    admin = headers(users[1])
    regular = headers(users[2])
    company_path = "/api/v1/companies/3"
    endpoint = "/api/v1/company-access/assignments"

    inbox = "/api/v1/company-access/notifications"
    base = "/api/v1/base-inteligente/3/status"
    assert client.get(inbox).status_code == 401
    assert client.get(base, headers=regular).status_code == 403
    assert client.get(company_path).status_code == 401
    assert client.get(company_path, headers=regular).status_code == 403
    assert client.get(endpoint, headers=regular).status_code == 403
    assert client.get(endpoint, headers=admin).json()["companies"][0]["email"] == users[0]
    assert client.put(endpoint + "/3", headers=regular, json={"email": users[2]}).status_code == 403
    assert client.put(endpoint + "/3", headers=admin, json={"email": "outside@example.test"}).status_code == 422
    assert client.put(endpoint + "/3", headers=admin, json={"email": users[2]}).status_code == 200
    assert client.get(company_path, headers=regular).status_code == 200
    assert client.get("/api/v1/companies/8", headers=regular).status_code == 403
    assert client.get(company_path, headers=admin).status_code == 200

    assert client.get(base, headers=regular).json() == {"learned": 42}
    notice = client.get(inbox, headers=regular).json()
    assert notice["unread"] == 1
    assert [row["company"] for row in notice["items"]] == [3]
    latest = notice["items"][0]["id"]
    assert client.get(inbox, headers=admin).json() == {"items": [], "unread": 0, "recipients": sorted(users[2:])}
    assert client.post(inbox + "/read", headers=other, json={"through": latest}).status_code == 200
    assert client.get(inbox, headers=regular).json()["unread"] == 1
    assert client.put(endpoint + "/3", headers=admin, json={"email": users[2]}).json()["changed"] is False
    assert client.get(inbox, headers=regular).json()["unread"] == 1
    assert client.post(inbox + "/read", headers=regular, json={"through": latest}).status_code == 200
    assert client.get(inbox, headers=regular).json()["unread"] == 0
    assert client.put(endpoint + "/3", headers=admin, json={"email": users[3]}).json()["changed"] is True
    assert client.get(base, headers=regular).status_code == 403
    assert client.get(inbox, headers=regular).json() == {"items": [], "unread": 0}
    assert client.get(base, headers=other).json() == {"learned": 42}
    assert client.get(inbox, headers=other).json()["unread"] == 1

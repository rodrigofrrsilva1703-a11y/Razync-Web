from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import company_access, monthly_tasks, site_access


def test_only_admins_send_direct_and_task_notices_to_collaborators(monkeypatch, tmp_path):
    admin = "admin@example.test"
    owner = "owner@example.test"
    other = "other@example.test"
    monkeypatch.setenv("RAZYNC_ADMIN_EMAILS", admin)
    monkeypatch.setenv("RAZYNC_LOGIN_EMAILS", ",".join((admin, owner, other)))
    monkeypatch.setenv("RAZYNC_DEFAULT_COMPANY_OWNER", owner)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    monkeypatch.setattr(monthly_tasks, "catalog", lambda: [{"codigo": 745, "nome": "Empresa teste"}])
    app = FastAPI()
    app.include_router(monthly_tasks.router)
    app.include_router(company_access.router)

    @app.middleware("http")
    async def test_identity(request: Request, call_next):
        token = site_access.current_owner.set(request.headers["test-user"])
        try:
            return await call_next(request)
        finally:
            site_access.current_owner.reset(token)

    client = TestClient(app)
    task = "/api/v1/monthly-tasks/2026-10/745"
    thread = task + "/messages"
    inbox = "/api/v1/company-access/notifications"

    def headers(email):
        return {"test-user": email}

    assert client.get(thread, headers=headers(other)).status_code == 403
    assert client.post(thread, headers=headers(owner), json={"body": "Pedido"}).status_code == 403
    assert client.post(inbox + "/send", headers=headers(owner), json={"recipient": other, "body": "Mensagem"}).status_code == 403
    assert client.get(inbox, headers=headers(admin)).json()["recipients"] == [other, owner]
    assert "recipients" not in client.get(inbox, headers=headers(owner)).json()
    assert client.post(inbox + "/send", headers=headers(admin), json={"recipient": admin, "body": "Mensagem"}).status_code == 422
    assert client.post(inbox + "/send", headers=headers(admin), json={"recipient": owner, "body": "Aviso geral"}).status_code == 201
    assert client.post(thread, headers=headers(admin), json={"body": "Revise a conciliação"}).status_code == 201
    notices = client.get(inbox, headers=headers(owner)).json()["items"]
    assert [(item["kind"], item["body"]) for item in notices] == [
        ("review", "Revise a conciliação"), ("direct", "Aviso geral"),
    ]
    assert notices[0]["period"] == "2026-10"
    assert notices[1]["period"] is None
    assert client.get(inbox, headers=headers(other)).json() == {"items": [], "unread": 0}
    assert client.get(thread, headers=headers(owner)).json()["can_request"] is False
    assert client.post(inbox + "/read", headers=headers(owner), json={
        "through": notices[1]["id"], "single": True,
    }).status_code == 200
    assert client.get(inbox, headers=headers(owner)).json()["unread"] == 1

    with company_access._db() as db:
        db.execute("INSERT INTO company_owners VALUES(?,?)", (745, other))
    assert [item["kind"] for item in client.get(inbox, headers=headers(owner)).json()["items"]] == ["direct"]
    assert client.get(thread, headers=headers(owner)).status_code == 403
    assert client.get(thread, headers=headers(other)).json()["messages"] == []

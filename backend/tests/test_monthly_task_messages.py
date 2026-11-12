from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import company_access, monthly_tasks, site_access


def test_task_requests_replies_and_resolution_follow_the_current_portfolio(monkeypatch, tmp_path):
    admin = "admin@example.test"
    owner = "owner@example.test"
    other = "other@example.test"
    monkeypatch.setenv("RAZYNC_ADMIN_EMAILS", admin)
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

    assert client.post(thread, headers=headers(other), json={"body": "Pedido"}).status_code == 403
    assert client.get(thread, headers=headers(other)).status_code == 403
    help_request = client.post(thread, headers=headers(owner), json={"body": "Conferir documentos"})
    assert help_request.status_code == 201
    review = client.post(thread, headers=headers(admin), json={"body": "Revise a conciliação"})
    assert review.status_code == 201
    reply = client.post(thread, headers=headers(admin), json={
        "body": "Pode usar o extrato atualizado", "reply_to": help_request.json()["id"],
    })
    assert reply.status_code == 201
    assert client.post(thread.replace("2026-10", "2026-09"), headers=headers(admin), json={
        "body": "Resposta fora da competência", "reply_to": help_request.json()["id"],
    }).status_code == 422
    assert client.get(inbox, headers=headers(admin)).json()["items"][0]["kind"] == "help"
    owner_notices = client.get(inbox, headers=headers(owner)).json()["items"]
    assert [item["kind"] for item in owner_notices] == ["reply", "review"]
    assert owner_notices[0]["period"] == "2026-10"
    assert client.post(inbox + "/read", headers=headers(owner), json={
        "through": owner_notices[0]["id"], "single": True,
    }).status_code == 200
    assert client.get(inbox, headers=headers(owner)).json()["unread"] == 1

    checklist = {"steps": ["pending"] * 6, "issue": "Revisar", "action": "", "issue_status": "open", "revision": 0}
    assert client.put(task, headers=headers(owner), json=checklist).status_code == 200
    assert client.put(task, headers=headers(admin), json={
        **checklist, "issue_status": "resolved", "revision": 1,
    }).status_code == 200
    assert client.get(inbox, headers=headers(owner)).json()["items"][0]["kind"] == "resolved"
    assert [msg["kind"] for msg in client.get(thread, headers=headers(owner)).json()["messages"]] == [
        "help", "review", "reply", "resolved",
    ]

    with company_access._db() as db:
        db.execute("INSERT INTO company_owners VALUES(?,?)", (745, other))
    assert client.get(inbox, headers=headers(owner)).json() == {"items": [], "unread": 0}
    assert client.get(thread, headers=headers(owner)).status_code == 403
    assert client.get(thread, headers=headers(other)).json()["messages"] == []

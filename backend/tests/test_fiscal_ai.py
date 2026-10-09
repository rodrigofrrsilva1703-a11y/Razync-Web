import json
import urllib.error
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import fiscal_ai
from app.main import app


def report():
    return {"empresa":"CONFIDENTIAL", "lancamentos":[{"historico":"JOAO CPF 12345678900", "valor":9123.45}],
        "contas":[{"conta":"22643", "tipo":"ENTRADAS", "descricao":"EMPRESA PRIVADA",
        "fiscal":9123.45,"contabil":0,"diferenca":-9123.45,"extras":2,"situacao":"REVISAR"}]}


def test_external_payload_has_no_identifiers_free_text_or_values():
    groups, mapping = fiscal_ai.sanitized(report())
    assert groups == [{"grupo":"G1", "situacao":"REVISAR", "natureza":"debito", "diferenca":"falta", "adicionais":True}]
    assert mapping == {"G1":{"conta":"22643","tipo":"ENTRADAS"}}
    for secret in ("22643", "JOAO", "12345678900", "9123", "EMPRESA", "CONFIDENTIAL"):
        assert secret not in json.dumps(groups)


def gateway(monkeypatch, answer):
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    monkeypatch.setattr(fiscal_ai, "last_request", 0)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps({"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":json.dumps(answer)}]}}]}).encode()
    def request(req, timeout):
        assert "test-secret" not in req.full_url
        assert timeout == 45
        payload = req.data.decode()
        assert "9123" not in payload and "22643" not in payload and "JOAO" not in payload
        return Response()
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", request)


def test_valid_response_maps_to_local_account_without_changing_numbers(monkeypatch):
    gateway(monkeypatch, {"analises":[{"grupo":"G1","explicacao":"Há falta de valor compatível.","verificar":"Verifique a integração no período."}]})
    source = report()
    result = fiscal_ai.explain(source)
    assert result["analises"][0]["conta"] == "22643"
    assert source["contas"][0]["fiscal"] == 9123.45
    with pytest.raises(HTTPException) as error:
        fiscal_ai.explain(source)
    assert error.value.status_code == 429


def test_invalid_group_is_rejected(monkeypatch):
    gateway(monkeypatch, {"analises":[{"grupo":"G999","explicacao":"Erro","verificar":"Teste"}]})
    with pytest.raises(HTTPException) as error:
        fiscal_ai.explain(report())
    assert error.value.status_code == 502


def test_missing_key_and_admin_protection(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = TestClient(app)
    assert client.get("/api/v1/conferencia-fiscal/242/ia/status").json() == {"configurado":False}
    monkeypatch.setenv("RAZYNC_ACCESS_TOKEN", "admin-test")
    files = {"acumuladores":("fiscal.xlsx",b"fake"),"razao":("razao.xlsx",b"fake")}
    assert client.post("/api/v1/conferencia-fiscal/242/ia",files=files).status_code == 401
    assert client.post("/api/v1/conferencia-fiscal/242/ia",files=files,headers={"Authorization":"Bearer admin-test"}).status_code == 503


def test_matching_groups_do_not_trigger_external_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    source = report(); source["contas"][0]["situacao"] = "CONFERE"
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", lambda *_: pytest.fail("Must not call Google"))
    assert fiscal_ai.explain(source)["analises"] == []

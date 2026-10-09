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
        assert "9123" in payload and "22643" in payload and "JOAO" not in payload
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


def test_missing_key_does_not_require_admin(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = TestClient(app)
    assert client.get("/api/v1/conferencia-fiscal/242/ia/status").json() == {"configurado":False}
    files = {"acumuladores":("fiscal.xlsx",b"fake"),"razao":("razao.xlsx",b"fake")}
    assert client.post("/api/v1/conferencia-fiscal/242/ia",files=files).status_code == 503


def test_analysis_endpoint_accepts_no_admin_password(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    monkeypatch.setattr(fiscal_ai, "conferencia_fiscal_preview", lambda *args: report())
    monkeypatch.setattr(fiscal_ai, "explain", lambda report: {"analises":[],"aviso":"Teste"})
    files = {"acumuladores":("fiscal.xlsx",b"fake"),"razao":("razao.xlsx",b"fake")}
    response = TestClient(app).post("/api/v1/conferencia-fiscal/242/ia", files=files)
    assert response.status_code == 200
    assert response.json()["aviso"] == "Teste"


def test_matching_groups_do_not_trigger_external_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    source = report(); source["contas"][0]["situacao"] = "CONFERE"
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", lambda *_: pytest.fail("Must not call Google"))
    assert fiscal_ai.explain(source)["analises"] == []


@pytest.mark.parametrize("code,reason,expected", [
    (400, "API_KEY_INVALID", "recusou a chave"),
    (403, "API_KEY_SERVICE_BLOCKED", "restrições"),
    (403, "PERMISSION_DENIED", "negou acesso"),
    (404, "NOT_FOUND", "modelo configurado"),
    (429, "RESOURCE_EXHAUSTED", "cota"),
    (400, "INVALID_ARGUMENT", "JSON estruturadas"),
    (503, "UNAVAILABLE", "HTTP 503"),
])
def test_provider_errors_are_actionable_without_leaking_secrets(monkeypatch, code, reason, expected):
    import io
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    monkeypatch.setattr(fiscal_ai, "last_request", 0)
    def fail(*args, **kwargs):
        body = json.dumps({"error": {"message": "test-secret private provider text", "details": [{"reason": reason}]}}).encode()
        raise urllib.error.HTTPError("https://example.invalid", code, "failure", {}, io.BytesIO(body))
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", fail)
    with pytest.raises(HTTPException) as error:
        fiscal_ai.explain(report())
    assert expected in error.value.detail
    assert "test-secret" not in error.value.detail
    assert "private provider text" not in error.value.detail
    assert error.value.status_code == (429 if code == 429 else 502)


def test_unavailable_configured_model_retries_flash_lite(monkeypatch):
    import io
    answer = {"analises":[{"grupo":"G1","explicacao":"Revisar diferença.","verificar":"Verifique os lançamentos."}]}
    gateway(monkeypatch, answer)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    original = fiscal_ai.urllib.request.urlopen
    calls = []
    def request(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 404, "missing", {}, io.BytesIO(b"{}"))
        return original(req, timeout)
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", request)
    assert fiscal_ai.explain(report())["analises"][0]["conta"] == "22643"
    assert len(calls) == 2
    assert "gemini-3.1-flash-lite" in calls[1]


def test_detailed_context_includes_authorized_records_and_totals():
    source = report()
    source["lancamentos"] = [{"conta":"22643", "historico":"Fornecedor JOAO CPF 12345678900", "data":"03/08/2026", "debito":1000, "credito":0}]
    context, mapping, refs, coverage = fiscal_ai.detailed_context(source)
    assert context["grupos"][0]["resumo"]["diferenca"] == -9123.45
    assert refs["L1"]["historico"] == "Fornecedor JOAO CPF 12345678900"
    assert refs["L1"]["debito"] == 1000
    assert "1 lançamentos" in coverage
    assert "sem documentos fiscais individuais" in context["fonte_fiscal"]


def test_invented_evidence_is_rejected(monkeypatch):
    gateway(monkeypatch, {"analises":[{"grupo":"G1", "explicacao":"Teste", "verificar":"Conferir", "evidencias":["L999"]}]})
    with pytest.raises(HTTPException) as error:
        fiscal_ai.explain(report())
    assert error.value.status_code == 502


def test_evidence_returns_original_record_and_full_history(monkeypatch):
    gateway(monkeypatch, {"analises":[{"grupo":"G1", "explicacao":"Revisar L1", "verificar":"Conferir documento", "evidencias":["L1"]}]})
    source = report()
    source["lancamentos"] = [{"conta":"22643", "historico":"Histórico completo do fornecedor", "debito":1000, "credito":0}]
    result = fiscal_ai.explain(source)
    assert result["analises"][0]["evidencias"][0]["historico"] == "Histórico completo do fornecedor"
    assert result["analises"][0]["evidencias"][0]["debito"] == 1000


def test_coverage_explicit_when_context_is_limited():
    source = report()
    source["contas"] = [dict(source["contas"][0], conta=str(i)) for i in range(15)]
    source["lancamentos"] = [dict(conta="0", historico="Original", debito=1) for _ in range(1501)]
    context, mapping, refs, coverage = fiscal_ai.detailed_context(source)
    assert len(mapping) == 12
    assert len(refs) == 1500
    assert context["grupos"][0]["cobertura"] == {"enviados":1500, "existentes":1501}
    assert "12 de 15" in coverage


def test_moeda_do_gemini_sempre_em_formato_brasileiro():
    assert fiscal_ai.formatar_brl(1234567.8) == "R$ 1.234.567,80"
    assert fiscal_ai.formatar_brl(-4282.5) == "-R$ 4.282,50"
    assert fiscal_ai.formatar_brl(0) == "R$ 0,00"
    fonte = "Conta 22643: R$ 1234.56; R$ 1,234.56; R$ 1.234,56. Diferença R$ -91.52."
    corrigido = fiscal_ai.padronizar_moeda(fonte)
    assert corrigido == (
        "Conta 22643: R$ 1.234,56; R$ 1.234,56; R$ 1.234,56. "
        "Diferença -R$ 91,52."
    )


def test_gemini_recebe_formatos_brl_e_devolve_valores_oficiais(monkeypatch):
    source = report()
    captured = {}
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    monkeypatch.setattr(fiscal_ai, "last_request", 0)
    class Resposta:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps({"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":json.dumps({
                "analises":[{"grupo":"G1","explicacao":"Falta R$ 9123.45.",
                             "verificar":"Verifique R$ 9,123.45.", "evidencias":[]}],
            })}]}}]}).encode()
    def fake_urlopen(req, timeout):
        body = json.loads(req.data)
        captured["payload"] = body
        assert "R$ 9.123,45" in body["contents"][0]["parts"][0]["text"]
        return Resposta()
    monkeypatch.setattr(fiscal_ai.urllib.request, "urlopen", fake_urlopen)
    result = fiscal_ai.explain(source)
    item = result["analises"][0]
    assert item["valores"]["fiscal"] == 9123.45
    assert item["valores"]["diferenca"] == -9123.45
    assert item["explicacao"] == "Falta R$ 9.123,45."
    assert item["verificar"] == "Verifique R$ 9.123,45."

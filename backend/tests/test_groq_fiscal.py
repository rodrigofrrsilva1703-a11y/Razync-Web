"""Regressões do provedor Groq gratuito, com requisições inteiramente simuladas."""
import io
import json
import urllib.error

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import fiscal_ai, groq_fiscal
from app.main import app


@pytest.fixture(autouse=True)
def isolated_groq(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.delenv("GROQ_ZDR_CONFIRMED", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("RAZYNC_AI_PRIMARY", "groq")
    monkeypatch.setenv("RAZYNC_AI_LEGACY_GEMINI", "0")


def example_report():
    return {
        "empresa": "FICTICIA",
        "periodo_fiscal": {"inicio":"2026-08-01","fim":"2026-08-31"},
        "periodo_razao": {"inicio":"2026-08-01","fim":"2026-08-31"},
        "lancamentos": [{
            "conta": "508", "data": "2026-08-07",
            "historico": "Compra NF 100 CPF 123.456.789-01 usuario@teste.com",
            "contrapartida": "1000", "debito": 8000, "credito": 0,
            "classificacao":"debito", "natureza":"ENTRADAS",
        }],
        "contas": [{
            "conta": "508", "tipo": "ENTRADAS", "descricao": "Estoque",
            "acumuladores": "123", "detalhes_fiscais": [{"codigo":"123","descricao":"Compras"}],
            "fiscal": 10000.0, "contabil":8000.0,
            "total_conta":8000.0, "diferenca":-2000.0,
            "extras": 0, "sem_evidencia":0, "situacao":"REVISAR",
        }]
    }


def enabled(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setenv("GROQ_ZDR_CONFIRMED", "1")


def test_groq_nao_chama_api_sem_privacidade_e_plano_confirmados(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("GROQ_FREE_TIER_CONFIRMED", "1")
    called = []
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen",
                        lambda *_args, **_kw: called.append(1))
    assert not groq_fiscal.is_enabled()
    assert TestClient(app).get("/api/v1/conferencia-fiscal/ia/status").json()["configurado"] is False
    with pytest.raises(HTTPException) as exc:
        fiscal_ai.explain(example_report())
    assert exc.value.status_code == 503
    assert called == []


def test_groq_produz_parecer_realmente_validado_sem_alterar_valores(monkeypatch):
    enabled(monkeypatch)
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n):
            return json.dumps({"choices":[{
                "finish_reason":"stop",
                "message":{"content":json.dumps({"analises":[{
                    "grupo":"G1",
                    "explicacao":"Diferença na conta 508 evidenciada em L1; causa não confirmada.",
                    "verificar":"1. Conferir notas; 2. Revisar razão e acumulador 123.",
                    "evidencias":["L1"]
                }]})}
            }]}).encode()
    def mock(req, timeout):
        data = json.loads(req.data)
        requests.append(data)
        assert req.full_url == "https://api.groq.com/openai/v1/chat/completions"
        assert req.get_header("Authorization") == "Bearer synthetic-test-key"
        assert timeout == 35
        assert data["model"] == "openai/gpt-oss-120b"
        assert data["response_format"]["json_schema"]["strict"] is True
        assert data["response_format"]["json_schema"]["schema"]["properties"]["analises"]["items"]["additionalProperties"] is False
        assert data["reasoning_effort"] == "low"
        assert data["max_completion_tokens"] == 3000
        assert "R$ 10.000,00" in data["messages"][1]["content"]
        assert "123.456.789-01" not in data["messages"][1]["content"]
        assert "usuario@teste.com" not in data["messages"][1]["content"]
        return Response()
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", mock)
    result = fiscal_ai.explain(example_report())
    assert len(requests) == 1
    assert result["provedor"] == "groq"
    assert result["gratuito"] is True
    assert result["fallback_usado"] is False
    assert result["analises"][0]["valores"]["fiscal"] == 10000
    assert result["analises"][0]["valores"]["contabil"] == 8000
    assert result["analises"][0]["evidencias"][0]["referencia"] == "L1"
    status = TestClient(app).get("/api/v1/conferencia-fiscal/ia/status").json()
    assert status["provedor"] == "groq"
    assert status["configurado"] is True


def test_groq_rejeita_lancamento_inexistente_no_texto(monkeypatch):
    enabled(monkeypatch)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n):
            return json.dumps({"choices":[{
                "finish_reason":"stop",
                "message":{"content":json.dumps({"analises":[{
                    "grupo":"G1",
                    "explicacao":"O lançamento L999 explica a diferença.",
                    "verificar":"1. Conferir",
                    "evidencias":[]
                }]})}
            }]}).encode()
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(HTTPException) as exc:
        fiscal_ai.explain(example_report())
    assert exc.value.status_code == 502


def test_groq_limite_429_faz_fallback_para_gemini_sem_perder_valores(monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY","test-gemini")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED","1")
    def refused(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "rate", {},
            io.BytesIO(b'{"error":{"message":"private client document"}}'))
    monkeypatch.setattr(groq_fiscal.urllib.request,"urlopen", refused)
    monkeypatch.setattr(fiscal_ai, "_gemini_completion", lambda *args, **kwargs: (
        {"analises":[{"grupo":"G1", "explicacao":"Conferir diferença documental.",
                     "verificar":"1. Compare o Razão.", "evidencias":[]}]}, "gemini-3.1-flash-lite"))
    result=fiscal_ai.explain(example_report())
    assert result["provedor"] == "gemini"
    assert result["fallback_usado"] is True
    assert result["analises"][0]["valores"]["diferenca"] == -2000.0


def test_groq_sem_confirmacao_nao_substitui_openrouter(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY","synthetic-test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY","test-openrouter")
    monkeypatch.setenv("RAZYNC_AI_PRIMARY","groq")
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("Groq desabilitada não faz request"))
    monkeypatch.setattr(fiscal_ai, "_openrouter_completion", lambda *args: (
        {"analises":[{"grupo":"G1", "explicacao":"Conferir fiscal com contábil.",
                     "verificar":"Conferir lançamentos", "evidencias":[]}]}, "openrouter/free"))
    result=fiscal_ai.explain(example_report())
    assert result["provedor"] == "openrouter"



def test_groq_resposta_truncada_identificada_e_preserva_fallback(monkeypatch, caplog):
    enabled(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "1")

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, n):
            return json.dumps({"choices": [{
                "finish_reason": "length",
                "message": {"content": "{\"analises\": [dado-fiscal-SENSIVEL"}
            }]}).encode()

    def fake(req, timeout):
        body = json.loads(req.data)
        assert body["max_completion_tokens"] == 3000
        return Response()

    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", fake)
    monkeypatch.setattr(fiscal_ai, "_gemini_completion", lambda *args, **kwargs: (
        {"analises": [{"grupo": "G1", "explicacao": "Exemplo fictício.",
                       "verificar": "Conferir documentos.", "evidencias": []}]},
        "gemini-3.1-flash-lite"))
    result = fiscal_ai.explain(example_report())
    assert result["provedor"] == "gemini"
    assert result["fallback_usado"] is True
    assert "category=Groq output limited by tokens" in caplog.text
    assert "dado-fiscal-SENSIVEL" not in caplog.text
    assert result["analises"][0]["valores"]["diferenca"] == -2000.0


def test_groq_resposta_com_json_invalido_registra_apenas_categoria(monkeypatch, caplog):
    enabled(monkeypatch)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, n):
            return json.dumps({"choices": [{
                "finish_reason": "stop",
                "message": {"content": "PRIVATE-FISCAL-TEXT"}
            }]}).encode()
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen",
                        lambda *args, **kwargs: Response())
    with pytest.raises(HTTPException) as err:
        fiscal_ai.explain(example_report())
    assert err.value.status_code == 502
    assert "category=Groq returned invalid JSON" in caplog.text
    assert "PRIVATE-FISCAL-TEXT" not in caplog.text
    assert "PRIVATE-FISCAL-TEXT" not in str(err.value.detail)


@pytest.mark.parametrize("failure", ["quota", "length"])
def test_groq_reserva_preserva_grupos_concluidos(monkeypatch, failure):
    enabled(monkeypatch)
    context = {"grupos":[{"grupo":f"G{i}", "lancamentos":[], "resumo":{}, "cobertura":{}} for i in range(1,4)]}
    payload = {"contents":[{"parts":[{"text":json.dumps(context)}]}]}
    calls = []
    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n): return json.dumps(self.body).encode()
    def send(req, timeout):
        body = json.loads(req.data)
        groups = json.loads(body["messages"][1]["content"])["grupos"]
        calls.append((body["model"], [g["grupo"] for g in groups]))
        if len(calls) == 2:
            if failure == "quota":
                raise urllib.error.HTTPError(req.full_url,429,"quota",{},io.BytesIO(b"{}"))
            return Response({"choices":[{"finish_reason":"length", "message":{"content":"incomplete"}}]})
        answer = {"analises":[{"grupo":g["grupo"], "explicacao":"Conferir", "verificar":"Revisar", "evidencias":[]} for g in groups]}
        # Mesmo JSON válido quando o provedor usa envelope markdown.
        return Response({"choices":[{"finish_reason":"stop", "message":{"content":"```json\n" + json.dumps(answer) + "\n```"}}]})
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", send)
    answer, used = groq_fiscal.complete(payload, "test", "openai/gpt-oss-120b")
    assert calls == [("openai/gpt-oss-120b", ["G1", "G2"]), ("openai/gpt-oss-120b", ["G3"]), ("openai/gpt-oss-20b", ["G3"])]
    assert [x["grupo"] for x in answer["analises"]] == ["G1", "G2", "G3"]
    assert used == "openai/gpt-oss-120b + openai/gpt-oss-20b"


def test_groq_deadline_nao_inicia_chamada_fora_do_prazo(monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setattr(groq_fiscal.time, "monotonic", lambda:100)
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Não pode iniciar"))
    payload={"contents":[{"parts":[{"text":json.dumps({"grupos":[{"grupo":"G1"}]})}]}]}
    with pytest.raises(HTTPException) as error:
        groq_fiscal.complete(payload, "test", "openai/gpt-oss-120b", _deadline=99)
    assert error.value.status_code == 504


@pytest.mark.parametrize("wrong_reference", ["L999", "L2"])
def test_groq_schema_restringe_referencias_e_rejeita_conta_errada(monkeypatch, wrong_reference):
    enabled(monkeypatch)
    context = {"grupos": [
        {"grupo": "G1", "lancamentos": [{"referencia": "L1"}]},
        {"grupo": "G2", "lancamentos": [{"referencia": "L2"}]},
    ]}
    payload = {"contents": [{"parts": [{"text": json.dumps(context)}]}]}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n):
            answer = {"analises": [
                {"grupo": "G1", "explicacao": "Conferir", "verificar": "Revisar", "evidencias": [wrong_reference]},
                {"grupo": "G2", "explicacao": "Conferir", "verificar": "Revisar", "evidencias": ["L2"]},
            ]}
            return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}]}).encode()
    def send(req, timeout):
        body = json.loads(req.data)
        props = body["response_format"]["json_schema"]["schema"]["properties"]["analises"]["items"]["properties"]
        assert props["grupo"]["enum"] == ["G1", "G2"]
        assert props["evidencias"]["items"]["enum"] == ["L1", "L2"]
        assert props["evidencias"]["maxItems"] == 3
        compact = json.loads(body["messages"][1]["content"])
        assert compact["referencias_permitidas_por_grupo"] == {"G1": ["L1"], "G2": ["L2"]}
        return Response()
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", send)
    with pytest.raises(ValueError, match="invented evidence"):
        groq_fiscal.complete(payload, "test", "openai/gpt-oss-120b")


def test_groq_schema_amostra_e_lote_sem_lancamentos(monkeypatch):
    enabled(monkeypatch)
    context = {"grupos": [
        {"grupo": "G1", "lancamentos": [{"referencia": f"L{i}"} for i in range(1, 13)]},
        {"grupo": "G2", "lancamentos": []},
        {"grupo": "G3", "lancamentos": []},
    ]}
    payload = {"contents": [{"parts": [{"text": json.dumps(context)}]}]}
    calls = []
    class Response:
        def __init__(self, groups): self.groups = groups
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n):
            answer = {"analises": [{"grupo": g["grupo"], "explicacao": "Conferir", "verificar": "Revisar", "evidencias": []} for g in self.groups]}
            return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}]}).encode()
    def send(req, timeout):
        body = json.loads(req.data)
        props = body["response_format"]["json_schema"]["schema"]["properties"]["analises"]["items"]["properties"]
        calls.append(props)
        return Response(json.loads(body["messages"][1]["content"])["grupos"])
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", send)
    result, _ = groq_fiscal.complete(payload, "test", "openai/gpt-oss-120b")
    assert len(result["analises"]) == 3
    assert set(calls[0]["evidencias"]["items"]["enum"]) == {f"L{i}" for i in [1,2,3,4,5,8,9,10,11,12]}
    assert calls[1]["grupo"]["enum"] == ["G3"]
    assert calls[1]["evidencias"]["maxItems"] == 0
    assert "enum" not in calls[1]["evidencias"]["items"]


@pytest.mark.parametrize("failure", ["quota", "length"])
def test_groq_reserva_bloqueada_continua_com_gemini(monkeypatch, failure, caplog):
    enabled(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "1")
    monkeypatch.setattr(fiscal_ai, "gemini_cooldown_until", 0)
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n):
            return json.dumps({"choices": [{"finish_reason": "length", "message": {"content": "incomplete"}}]}).encode()
    def send(req, timeout):
        model = json.loads(req.data)["model"]
        calls.append(model)
        if model == "openai/gpt-oss-120b":
            if failure == "length":
                return Response()
            raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, io.BytesIO(b"{}"))
        raise urllib.error.HTTPError(req.full_url, 403, "blocked", {}, io.BytesIO(
            b'{"error":{"code":"model_permission_blocked_org","message":"PRIVATE-RESPONSE"}}'))
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", send)
    monkeypatch.setattr(fiscal_ai, "_gemini_completion", lambda *args, **kwargs: (
        {"analises": [{"grupo": "G1", "explicacao": "Revisar documentos.", "verificar": "Conferir conta.", "evidencias": ["L1"]}]},
        "gemini-3.1-flash-lite"))
    result = fiscal_ai.explain(example_report())
    assert calls == list(groq_fiscal.FREE_MODELS)
    assert result["provedor"] == "gemini"
    assert result["fallback_usado"] is True
    assert result["gratuito"] is True
    assert result["analises"][0]["valores"]["diferenca"] == -2000
    assert "fiscal_groq_reserve_blocked" in caplog.text
    assert "PRIVATE-RESPONSE" not in caplog.text


def test_groq_permissao_principal_nao_e_ocultada_pelo_gemini(monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "1")
    def send(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "blocked", {}, io.BytesIO(
            b'{"error":{"code":"model_permission_blocked_org"}}'))
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", send)
    monkeypatch.setattr(fiscal_ai, "_gemini_completion", lambda *args, **kwargs: pytest.fail("Permissão principal deve ser exibida"))
    with pytest.raises(HTTPException) as error:
        fiscal_ai.explain(example_report())
    assert error.value.status_code == 403
    assert "openai/gpt-oss-120b" in error.value.detail



def test_indicadores_contam_sinais_sem_concluir_duplicidade_ou_alterar_dados():
    import copy
    row = {"data": "2026-08-07", "historico": "Compra NF 100", "contrapartida": "508", "debito": 80, "credito": 0, "classificacao": "FISCAL"}
    rows = [dict(row), dict(row), dict(row, data="2026-08-08"),
            dict(row, historico="Estorno compra", debito=-80),
            dict(row, historico=""), dict(row, historico="", debito="inválido"),
            dict(row, historico="Devolução", credito="NaN")]
    original = copy.deepcopy(rows)
    result = groq_fiscal._record_indicators(rows)
    assert rows == original
    assert result["registros_examinados_localmente"] == 7
    assert result["historicos_vazios"] == 2
    assert result["historicos_mencionando_estorno_cancelamento_devolucao"] == 2
    assert result["registros_com_valor_negativo"] == 1
    assert result["conjuntos_com_mesma_data_historico_contrapartida_e_valores"] == 1
    assert result["classificacoes_do_leitor"] == {"FISCAL": 7}
    assert "não comprovam" in result["ressalva"]


def test_amostra_prioriza_sinais_no_meio_do_periodo_sem_perder_indicadores_locais():
    rows = [{"referencia": f"L{i}", "data": "2026-08-07", "historico": f"Compra {i}", "contrapartida": "508", "debito": 80, "credito": 0} for i in range(1, 13)]
    rows[5]["historico"] = rows[6]["historico"] = "Estorno intermediário"
    group = groq_fiscal._compact_group({"grupo": "G1", "lancamentos": rows, "cobertura": {"existentes": 100}})
    assert group["amostra_enviada"] == 10
    assert group["amostra_nao_exaustiva"] is True
    assert group["indicadores_locais"]["registros_examinados_localmente"] == 12
    assert group["indicadores_locais"]["historicos_mencionando_estorno_cancelamento_devolucao"] == 2
    assert group["indicadores_locais"]["conjuntos_com_mesma_data_historico_contrapartida_e_valores"] == 1
    assert {"L6", "L7"}.issubset({r["referencia"] for r in group["lancamentos"]})
    assert "Estorno intermediário" in json.dumps(group, ensure_ascii=False)



def test_qwen_reserva_gratuita_apos_cota_dos_dois_gpt_oss(monkeypatch):
    enabled(monkeypatch)
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n):
            return json.dumps({"choices":[{"finish_reason":"stop", "message":{"content":json.dumps({"analises":[{"grupo":"G1", "explicacao":"Conferir L1", "verificar":"Conferir documentos", "evidencias":["L1"]}]})}}]}).encode()
    def send(req, timeout):
        body = json.loads(req.data)
        calls.append(body["model"])
        if body["model"].startswith("openai/"):
            raise urllib.error.HTTPError(req.full_url, 429, "quota", {"Retry-After":"60"}, io.BytesIO(b"{}"))
        assert body["model"] == "qwen/qwen3.8-27b"
        assert body["reasoning_effort"] == "none"
        assert body["response_format"]["json_schema"]["strict"] is True
        return Response()
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", send)
    result = fiscal_ai.explain(example_report())
    assert calls == list(groq_fiscal.FREE_MODELS)
    assert result["provedor"] == "groq"
    assert result["modelo_usado"] == "qwen/qwen3.8-27b"
    assert result["analises"][0]["valores"]["fiscal"] == 10000
    assert result["analises"][0]["evidencias"][0]["referencia"] == "L1"
    calls.clear()
    result = fiscal_ai.explain(example_report())
    assert calls == ["qwen/qwen3.8-27b"]


def test_parecer_invalido_e_rejeitado_e_tentado_em_outro_modelo(monkeypatch):
    enabled(monkeypatch)
    calls = []
    class Response:
        def __init__(self, ref): self.ref = ref
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n):
            return json.dumps({"choices":[{"finish_reason":"stop", "message":{"content":json.dumps({"analises":[{"grupo":"G1", "explicacao":"Conferir", "verificar":"Conferir documentos", "evidencias":[self.ref]}]})}}]}).encode()
    def send(req, timeout):
        model = json.loads(req.data)["model"]
        calls.append(model)
        return Response("L999" if model.endswith("120b") else "L1")
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", send)
    result = fiscal_ai.explain(example_report())
    assert calls == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert result["analises"][0]["evidencias"][0]["referencia"] == "L1"


def test_todos_modelos_em_cooldown_nao_fazem_requisicoes(monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setattr(groq_fiscal.time, "monotonic", lambda:100)
    groq_fiscal._quota_cooldowns.update({model:160 for model in groq_fiscal.FREE_MODELS})
    monkeypatch.setattr(groq_fiscal.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Cota em espera"))
    with pytest.raises(HTTPException) as error:
        groq_fiscal.complete({}, "synthetic", "openai/gpt-oss-120b")
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "60"

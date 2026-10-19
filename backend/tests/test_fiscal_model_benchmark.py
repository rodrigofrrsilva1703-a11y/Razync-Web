import io
import json
from app import fiscal_model_benchmark as benchmark


def test_comparacao_envia_casos_fixos_com_custo_zero_e_sem_fallback(monkeypatch):
    captured = []
    raw = {"analises": [{"grupo": "G1", "explicacao": "Hipóteses: a causa está indeterminada. Limitações: falta o documento original.",
                        "verificar": "1. Obtenha o detalhamento do acumulador 1152.", "evidencias": []}]}
    def send(request, timeout):
        captured.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"model": benchmark.MODELS[0], "choices": [{"message": {"content": json.dumps(raw)}, "finish_reason": "stop"}]}).encode())
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", send)
    name, report = benchmark.cases()[2]
    result = benchmark.evaluate(benchmark.MODELS[0], name, report, "synthetic-test-key")
    assert result['contract_valid']
    assert captured[0]['provider']['max_price'] == {'prompt': 0, 'completion': 0}
    assert captured[0]['provider']['allow_fallbacks'] is False
    assert captured[0]['provider']['data_collection'] == 'deny'
    assert 'synthetic-test-key' not in json.dumps(result)


def test_comparacao_nao_confunde_json_valido_com_evidencia_valida(monkeypatch):
    raw = {"analises": [{"grupo": "G1", "explicacao": "Hipóteses: confira L999.", "verificar": "1. Confira L999.", "evidencias": ["L999"]}]}
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(raw)}}]}).encode()))
    name, report = benchmark.cases()[0]
    result = benchmark.evaluate(benchmark.MODELS[0], name, report, "synthetic-test-key")
    assert result['error'] == 'ValueError'
    assert not result.get('contract_valid')

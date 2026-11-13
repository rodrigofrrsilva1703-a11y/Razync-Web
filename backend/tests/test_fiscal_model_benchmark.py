import json
from app import fiscal_model_benchmark as benchmark


def test_comparacao_usa_mesmo_caminho_da_producao_sem_trocar_modelo(monkeypatch):
    captured = []
    raw = {"analises": [{"grupo": "G1", "explicacao": "Hipóteses: a causa está indeterminada. Limitações: falta o documento original.",
                        "verificar": "1. Obtenha o detalhamento do acumulador 1152.", "evidencias": []}]}
    def send(payload, models, key, **kwargs):
        captured.append((payload, models))
        return raw, models[0]
    monkeypatch.setattr(benchmark.fiscal_ai, "_openrouter_completion", send)
    name, report = benchmark.cases()[2]
    result = benchmark.evaluate(benchmark.MODELS[0], name, report, "synthetic-test-key")
    assert result['contract_valid']
    assert captured[0][1] == [benchmark.MODELS[0]]
    assert captured[0][0]['generationConfig']['responseSchema']['properties']['analises']
    assert json.loads(result['raw']) == raw
    assert 'synthetic-test-key' not in json.dumps(result)


def test_comparacao_nao_confunde_json_valido_com_evidencia_valida(monkeypatch):
    raw = {"analises": [{"grupo": "G1", "explicacao": "Hipóteses: confira L999.", "verificar": "1. Confira L999.", "evidencias": ["L999"]}]}
    monkeypatch.setattr(benchmark.fiscal_ai, "_openrouter_completion", lambda *a, **k: (raw, benchmark.MODELS[0]))
    name, report = benchmark.cases()[0]
    result = benchmark.evaluate(benchmark.MODELS[0], name, report, "synthetic-test-key")
    assert not result.get('contract_valid')
    assert result.get('error')

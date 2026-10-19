"""Comparação manual, limitada e gratuita; não é exposta pela API.

Executar: python -m app.fiscal_model_benchmark --run
Usa apenas os casos fictícios fixos abaixo. Nunca recebe relatórios de usuários.
A validação automática mede contrato/evidências, não substitui revisão das respostas.
"""
import argparse
import json
import os
import time
import sys
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "legacy"))

from app import fiscal_ai
from app.fiscal_ai_strategy import REVIEW_PROMPT

MODELS = ["dots-studio/dots-3-note-preview:free", "nvidia/nemotron-3.5-lightning:free",
          "google/gemma-4-31b-it:free"]


def cases():
    def make(name, fiscal, contabil, docs=None, rows=None):
        account = dict(conta="508", tipo="ENTRADAS", situacao="REVISAR", fiscal=fiscal,
                       contabil=contabil, total_conta=contabil, diferenca=contabil-fiscal,
                       extras=0, acumuladores="1152", descricao="Compras fictícias")
        report = {"contas": [account], "lancamentos": rows or []}
        if docs is not None:
            key = "508:ENTRADAS"
            report.update(documentos_pendentes={key: docs},
                resumo_documental={key: {"documentos_lidos": len(docs), "documentos_pendentes": len(docs),
                    "situacoes": {d["situacao"]: sum(x["situacao"] == d["situacao"] for x in docs) for d in docs}}},
                cobertura_documental={key: {"amostra": False}}, fonte_fiscal="Documentos fiscais fictícios")
        return name, report
    row = dict(conta="508", data="04/08/2026", historico="COMPRA FICTICIA NF 101",
               contrapartida="800", debito=250, credito=0, natureza="DÉBITO", classificacao="CONSIDERADO")
    return [
        make("valor_diferente", 200, 250,
            [dict(referencia="E-1", situacao="VALOR_DIFERENTE", nota="101", acumulador="1152",
                  valor_brl="R$ 200,00", valor_razao_candidato_brl="R$ 250,00", razao_id="L1")], [row]),
        make("outra_conta", 300, 0,
            [dict(referencia="E-1", situacao="CONTA_DIFERENTE", nota="202", acumulador="1152",
                  valor_brl="R$ 300,00", conta_razao_candidato="509", valor_razao_candidato_brl="R$ 300,00")]),
        make("sem_documentos", 500, 400, rows=[dict(row, historico="COMPRA FICTICIA SEM NUMERO DE NOTA", debito=400)]),
        make("totais_iguais_vinculo_ambiguo", 200, 200,
            [dict(referencia="E-1", situacao="AMBIGUO", nota="303", acumulador="1152",
                  valor_brl="R$ 200,00", detalhe="Dois candidatos; série e parceiro não disponíveis.")],
            [dict(row, historico="COMPRA FICTICIA NF 303", debito=100),
             dict(row, historico="COMPRA FICTICIA NF 303", debito=100)]),
    ]


def evaluate(model, name, report, key):
    start = time.monotonic()
    outcome = {"protocol": "production", "model": model, "case": name}
    validator = fiscal_ai._validar_resposta_ia
    def record(raw, *args, **kwargs):
        outcome["raw"] = json.dumps(raw, ensure_ascii=False)
        return validator(raw, *args, **kwargs)
    try:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": key}), \
             patch.object(fiscal_ai, "_openrouter_models", return_value=[model]), \
             patch.object(fiscal_ai, "_validar_resposta_ia", side_effect=record):
            result = fiscal_ai.explain(report, only_openrouter=True)
        verified = result["analises"][0]
        outcome.update(actual_model=result.get("modelo_usado"), contract_valid=True,
                       audit=verified["auditoria"], published_explanation=verified["explicacao"])
    except HTTPException as exc:
        outcome.update(error="provider_or_validation", status=exc.status_code, detail=exc.detail)
    except Exception as exc:
        outcome.update(error=type(exc).__name__)
    outcome["seconds"] = round(time.monotonic()-start, 2)
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.parse_args()
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        print('RZ_EVAL {"error":"missing_key"}', flush=True)
        return
    for model in MODELS:
        for name, report in cases():
            result = evaluate(model, name, report, key)
            print("RZ_EVAL " + json.dumps(result, ensure_ascii=False), flush=True)
            if result.get("status") in (429, 503):
                break
    print('RZ_EVAL_DONE', flush=True)


if __name__ == "__main__":
    main()

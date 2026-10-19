"""Comparação manual, limitada e gratuita; não é exposta pela API.

Executar: python -m app.fiscal_model_benchmark --run
Usa apenas os casos fictícios fixos abaixo. Nunca recebe relatórios de usuários.
A validação automática mede contrato/evidências, não substitui revisão das respostas.
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request

from app.fiscal_ai import detailed_context, _validar_resposta_ia
from app.fiscal_ai_strategy import REVIEW_PROMPT

MODELS = ["dots-studio/dots-3-note-preview:free", "liquid/lfm-2.5-2.6b:free",
          "minimax/minimax-m3.1-flash:free", "google/gemma-4-31b-it:free"]


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
    context, mapping, references, _ = detailed_context(report)
    allowed = {g["grupo"]: [r["referencia"] for r in g["lancamentos"]] for g in context["grupos"]}
    body = {"model": model, "messages": [
        {"role": "system", "content": REVIEW_PROMPT + " Referências permitidas: " + json.dumps(allowed)},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
        "temperature": 0.2, "max_tokens": 1600, "reasoning": {"enabled": False},
        "provider": {"allow_fallbacks": False, "data_collection": "deny", "max_price": {"prompt": 0, "completion": 0}}}
    start = time.monotonic()
    outcome = {"model": model, "case": name}
    try:
        request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key,
            "Content-Type": "application/json", "X-Title": "Razync Synthetic Evaluation"})
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.load(response)
        choice = answer["choices"][0]
        raw = choice["message"]["content"] or ""
        outcome.update(actual_model=answer.get("model"), finish=choice.get("finish_reason"), raw=raw)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split('\n', 1)[1].rsplit('```', 1)[0]
        parsed = json.loads(clean)
        verified = _validar_resposta_ia(parsed, report, mapping, references, provider="openrouter", model=model)
        outcome.update(contract_valid=True, audit=verified[0]["auditoria"],
                       published_explanation=verified[0]["explicacao"])
    except urllib.error.HTTPError as exc:
        outcome.update(error="http", status=exc.code)
    except (TimeoutError, urllib.error.URLError):
        outcome.update(error="timeout_or_network")
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
            print("RZ_EVAL " + json.dumps(evaluate(model, name, report, key), ensure_ascii=False), flush=True)
    print('RZ_EVAL_DONE', flush=True)


if __name__ == "__main__":
    main()

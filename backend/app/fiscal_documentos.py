"""Investigação documental opcional após Conferência Fiscal × Contábil.

Não altera a conferência existente nem conclui omissão/duplicidade por igualdade
de totais. Usa apenas relatórios escolhidos pelo usuário e a filial já filtrada.
"""
from __future__ import annotations

import io
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from app.fiscal_242 import conferencia_fiscal_preview
from razync.conferencia_fiscal import (
    _chave_empresa, _codigo_dominio, _data_dominio, _empresa_no_cabecalho,
    _excel, _numero, _periodo_relatorio, _rotulo, _texto,
)

TARGET_STATUSES = {"REVISAR", "AUSENTE NO CONTÁBIL", "CONFERE COM ALERTAS"}
TAX_LABELS = {"ICMS", "IPI", "SUBTRI", "SUBSTITUICAO TRIBUTARIA", "ST", "ISS", "PIS", "COFINS"}
NOTE_RE = re.compile(
    r"(?<!\w)(?:N\.?\s?F\.?|NOTA(?:\s+FISCAL)?|CTRC|CT\s*-?\s*E)(?:\s*(?:N[º°.]|NUMERO|NR))?\s*[:#º°.-]*\s*(\d{1,12})(?!\d)",
    re.IGNORECASE,
)
CNPJ_RE = re.compile(r"(?<!\d)(?:\d{2}[.]?\d{3}[.]?\d{3}[/]?\d{4}[-]?\d{2})(?!\d)")


def _centavos(value):
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _nota(value):
    value = _codigo_dominio(value)
    return value.lstrip("0") or ("0" if value else "")


def _periodo_data(value):
    date = _data_dominio(value)
    return pd.Timestamp(date).normalize() if pd.notna(date) else None


def _celula(values, index, largura=2):
    if index is None:
        return ""
    for i in range(index, min(index + largura, len(values))):
        if _texto(values[i]):
            return values[i]
    return ""


def _cnpj(values):
    for v in values:
        m = CNPJ_RE.search(_texto(v))
        if m:
            return re.sub(r"\D", "", m.group())
    return ""


def ler_acompanhamento(content: bytes, name: str, tipo: str, acumuladores: set[str]) -> dict:
    """Extrai documentos, ignorando totalizações e linhas auxiliares de tributos.

    Se o layout não expuser um acumulador reconhecível, o documento NÃO
    será associado a uma conta por aproximação numérica.
    """
    if not name.lower().endswith((".xls", ".xlsx")):
        raise ValueError("Os acompanhamentos devem estar em XLS ou XLSX.")
    if not content or len(content) > 25_000_000:
        raise ValueError("O acompanhamento está vazio ou excede 25 MB.")
    xls = _excel(content, name)  # Inclui recuperação BIFF do Domínio.
    period = None
    company = ""
    cnpj = ""
    filiais = set()
    documents = []
    ignored = 0
    unidentified = 0
    found_header = False
    for sheet in xls.sheet_names:
        table = pd.read_excel(xls, sheet_name=sheet, header=None, dtype=object)
        columns = None
        current_acc = ""
        partner = ""
        for row_index, series in table.iterrows():
            vals = series.tolist()
            labels = [_rotulo(value) for value in vals]
            combined = " ".join(label for label in labels if label)
            first = labels[0] if labels else ""
            possible = _empresa_no_cabecalho(vals, primeira_linha=row_index == 0)
            if possible:
                if company and _chave_empresa(company) != _chave_empresa(possible):
                    raise ValueError(f"O acompanhamento de {tipo.lower()} contém empresas diferentes.")
                company = possible
            if "CNPJ" in combined:
                cnpj = cnpj or _cnpj(vals)
            if first.startswith("PERIODO"):
                parsed = _periodo_relatorio(vals)
                if parsed:
                    if period and period != parsed:
                        raise ValueError(f"O acompanhamento de {tipo.lower()} contém períodos diferentes.")
                    period = parsed
            if "FILIAL" in first and len(vals) >= 2:
                code = _codigo_dominio(_celula(vals, 1, 4))
                if code:
                    filiais.add(code.lstrip("0") or "0")
            if "ACUMULADOR" in combined and "NOTA" not in labels:
                for value in vals:
                    code = _codigo_dominio(value)
                    if code in acumuladores:
                        current_acc = code
                        break
            # Cada página pode repetir o cabeçalho, com colunas deslocadas.
            if "NOTA" in labels and "CFOP" in labels and any(
                label.startswith("VALOR CONT") or label in {"VLR CONTABIL", "VL CONTABIL"}
                for label in labels
            ):
                found_header = True
                def locate(*terms):
                    for index, label in enumerate(labels):
                        if any(label == term or label.startswith(term + " ") for term in terms):
                            return index
                    return None
                columns = {
                    "nota": locate("NOTA"),
                    "data": locate("DATA", "EMISSAO", "DT EMISSAO"),
                    "cfop": locate("CFOP"),
                    "valor": locate("VALOR CONTABIL", "VALOR CONT", "VLR CONTABIL", "VL CONTABIL"),
                    # Nos XLS reais do Domínio, "Código" inicial é ID da linha,
                    # o segundo "Código" identifica o parceiro; "AC." é o acumulador.
                    "acc": locate("AC", "ACUMULADOR") if locate("AC", "ACUMULADOR") is not None
                           else locate("CODIGO", "COD"),
                    "serie": locate("SERIE"),
                    "parceiro": locate("FORNECEDOR" if tipo == "ENTRADAS" else "CLIENTE"),
                    "filial": locate("FILIAL"),
                }
                continue
            if any(label.startswith("TOTAL") for label in labels) or first in TAX_LABELS:
                ignored += 1
                continue
            # Linhas auxiliares ICMS/IPI/SUBTRI aparecem logo abaixo da nota,
            # por isso só aceitamos linhas com NF, data, CFOP e valor contábil.
            if columns is None:
                continue
            if any(label in TAX_LABELS for label in labels[:4]):
                ignored += 1
                continue
            note = _nota(_celula(vals, columns["nota"], 2))
            date = _periodo_data(_celula(vals, columns["data"], 2))
            cfop_raw = _codigo_dominio(_celula(vals, columns["cfop"], 2))
            cfop = cfop_raw if re.fullmatch(r"\d{4}", cfop_raw) else ""
            valor_raw = _celula(vals, columns["valor"], 2)
            value = _numero(valor_raw)
            if not note or date is None or not cfop or abs(value) < .005:
                # Cabeçalhos com fornecedor/cliente podem surgir entre as notas.
                if not note and not cfop:
                    possible_partner = next((_texto(v) for v in vals[:8]
                        if _texto(v) and len(_texto(v)) > 5
                        and not _rotulo(v).startswith(("TOTAL", "PERIODO", "PAGINA"))), "")
                    if possible_partner and not re.search(r"\b(ICMS|IPI|SUBTRI)\b", possible_partner.upper()):
                        partner = possible_partner[:100]
                continue
            acc = _codigo_dominio(_celula(vals, columns["acc"], 2))
            if acc and acc not in acumuladores:
                # Documento pertence a outro acumulador, não a uma falha de leitura.
                continue
            if not acc:
                acc = current_acc if current_acc in acumuladores else ""
            if not acc:
                unidentified += 1
                continue
            row_filial = _codigo_dominio(_celula(vals, columns["filial"], 2))
            if row_filial:
                filiais.add(row_filial.lstrip("0") or "0")
            document = {
                "id": f"{tipo[0]}-{len(documents)+1}",
                "tipo": tipo, "acumulador": acc,
                "nota": note, "serie": _texto(_celula(vals, columns["serie"], 2))[:20],
                "data": date.strftime("%d/%m/%Y"), "cfop": cfop,
                "valor": round(value, 2),
                "parceiro": _texto(_celula(vals, columns["parceiro"], 2))[:100] or partner,
                "filial": row_filial, "linha_origem": int(row_index) + 1,
            }
            documents.append(document)
    if not found_header:
        raise ValueError(f"Não foi encontrado o cabeçalho de documentos no Acompanhamento de {tipo.title()}.")
    # Nenhum documento com acumulador vinculado não significa documento inexistente:
    # pode ser formato de exportação diferente ou relatório sem o acumulador visado.
    # A comparação permanece inconclusiva e os movimentos do Razão não são
    # declarados sem documento por mera ausência de linhas reconhecidas.
    return {"documentos": documents, "periodo": period, "empresa": company,
            "cnpj": cnpj, "filiais": sorted(filiais), "ignoradas": ignored,
            "sem_acumulador": unidentified}


def _nota_historico(texto):
    m = NOTE_RE.search(str(texto or ""))
    return _nota(m.group(1)) if m else ""

def _nota_inferida_historico(texto):
    # Alguns Razões reais trazem apenas "149249 - NOME", sem a sigla NF.
    # Número inicial é indício, não confirmação de nota fiscal.
    m = re.match(r"^\s*(\d{3,9})\s*(?:-|\s)", str(texto or ""))
    return _nota(m.group(1)) if m else ""


def _cnpj_no_resumo(content, name):
    """Confere identidade da filial quando CNPJ está disponível em ambos os arquivos."""
    book = _excel(content, name)
    for sheet in book.sheet_names[:3]:
        header = pd.read_excel(book, sheet_name=sheet, header=None, nrows=12, dtype=object)
        for _, row in header.iterrows():
            values = row.tolist()
            if any("CNPJ" in _rotulo(v) for v in values):
                code = _cnpj(values)
                if code:
                    return code
    return ""


def _valida_relatorio(detalhe, preview, tipo):
    original = preview.get("empresa_nome", "")
    company = detalhe["empresa"]
    if original and company and _chave_empresa(original) != _chave_empresa(company):
        raise ValueError(f"O Acompanhamento de {tipo.title()} pertence a outra empresa.")
    fiscal = preview.get("periodo_fiscal", {})
    try:
        start = datetime.strptime(fiscal["inicio"], "%d/%m/%Y").date()
        end = datetime.strptime(fiscal["fim"], "%d/%m/%Y").date()
    except (TypeError, ValueError, KeyError):
        raise ValueError("Informe relatórios com período fiscal identificado antes de investigar documentos.")
    interval = detalhe["periodo"]
    if not interval:
        raise ValueError(f"Não foi possível confirmar o período do Acompanhamento de {tipo.title()}.")
    if interval[0].date() != start or interval[1].date() != end:
        raise ValueError(f"O período do Acompanhamento de {tipo.title()} é diferente do Resumo por Acumulador.")
    chosen = str(preview.get("filial_aplicada") or "")
    if detalhe["filiais"] and chosen and chosen not in detalhe["filiais"]:
        raise ValueError(f"O Acompanhamento de {tipo.title()} não contém a filial {chosen}.")
    return chosen


def investigar_documentos(acumuladores_bytes, acumuladores_nome, razao_bytes,
                          razao_nome, entradas=None, saidas=None, filial="", *,
                          completo=False, preview=None):
    """Recalcula a conferência inicial no servidor e investiga só contas alertadas."""
    if entradas is None and saidas is None:
        raise ValueError("Selecione pelo menos um Acompanhamento de Entradas ou Saídas.")
    if preview is None:
        preview = conferencia_fiscal_preview(acumuladores_bytes, acumuladores_nome,
                                             razao_bytes, razao_nome, filial_alvo=filial or None)
    targets = {(str(r["conta"]), r["tipo"]): r for r in preview["contas"]
               if r["situacao"] in TARGET_STATUSES}
    reports = {}
    warnings = []
    expected_cnpj = _cnpj_no_resumo(acumuladores_bytes, acumuladores_nome)
    for tipo, attachment in (("ENTRADAS", entradas), ("SAÍDAS", saidas)):
        if attachment is None:
            continue
        rows = [r for r in targets.values() if r["tipo"] == tipo]
        allowed = {str(a["codigo"]) for r in rows for a in r["detalhes_fiscais"]}
        if not allowed:
            warnings.append(f"Não existem contas de {tipo.lower()} com divergência ou alerta nesta conferência.")
            continue
        detail = ler_acompanhamento(attachment[0], attachment[1], tipo, allowed)
        if not detail["documentos"]:
            warnings.append(f"O relatório de {tipo.lower()} não possui documentos identificáveis "
                            "nos acumuladores divergentes. Não é possível concluir ausência fiscal.")
        filial_aplicada = _valida_relatorio(detail, preview, tipo)
        if expected_cnpj and detail["cnpj"] and expected_cnpj != detail["cnpj"]:
            raise ValueError(
                f"O CNPJ do Acompanhamento de {tipo.title()} não corresponde ao Resumo por Acumulador."
            )
        if not expected_cnpj or not detail["cnpj"]:
            warnings.append(f"Não foi possível confirmar o CNPJ entre Resumo e {tipo.title()}; "
                            "confira a filial e o documento de origem.")
        if not detail["filiais"]:
            warnings.append(f"O relatório de {tipo.lower()} não informa filial por documento; "
                            f"confirme se pertence à filial {filial_aplicada} antes de concluir ajustes.")
        if detail["sem_acumulador"]:
            warnings.append(f"{detail['sem_acumulador']} linha(s) de {tipo.lower()} sem acumulador "
                            "vinculado identificável foram excluídas do cruzamento automático.")
        reports[tipo] = detail
    if not reports:
        return {"filial": preview["filial_aplicada"], "empresa_nome": preview["empresa_nome"],
                "periodo": preview["periodo_fiscal"], "contas": [], "avisos": warnings,
                "resumo": {"contas": 0, "conciliados": 0, "pendentes": 0, "ambiguos": 0},
                "tipos_investigados": []}
    all_docs = [doc for report in reports.values() for doc in report["documentos"]]
    result = []
    for (account, tipo), row in targets.items():
        if tipo not in reports:
            continue
        codes = {str(a["codigo"]) for a in row["detalhes_fiscais"]}
        docs = [d.copy() for d in all_docs if d["tipo"] == tipo and d["acumulador"] in codes]
        ledger = []
        for i, mov in enumerate(preview["lancamentos"]):
            if str(mov["conta"]) != account:
                continue
            amount = float(mov["credito"] if tipo == "SAÍDAS" else mov["debito"])
            if abs(amount) < .005:
                continue
            nota_explicita = _nota_historico(mov.get("historico", ""))
            ledger.append({
                "id": f"R-{i+1}", "data": str(mov.get("data", "")),
                "valor": round(amount, 2),
                "nota": nota_explicita or _nota_inferida_historico(mov.get("historico", "")),
                "nota_explicita": bool(nota_explicita),
                "historico": str(mov.get("historico", "")),
                "contrapartida": mov.get("contrapartida", ""),
                "classificacao": mov.get("classificacao", ""),
            })
        strong_candidates = defaultdict(list)
        ledger_to_docs = defaultdict(list)
        near_candidates = defaultdict(list)
        # Índices reduzem o cruzamento de todos-contra-todos para poucas
        # candidatas por nota ou por valor/data, essencial com milhares de NFs.
        by_note = defaultdict(list)
        by_amount_day = defaultdict(list)
        for mov in ledger:
            mov_day = datetime.strptime(mov["data"], "%d/%m/%Y").date()
            mov["_day"] = mov_day
            mov["_cents"] = _centavos(mov["valor"])
            if mov["nota"]:
                by_note[mov["nota"]].append(mov)
            by_amount_day[(mov["_cents"], mov_day)].append(mov)
        for d in docs:
            dt = datetime.strptime(d["data"], "%d/%m/%Y").date()
            cents = _centavos(d["valor"])
            candidates = {mov["id"]: mov for mov in (
                by_note.get(d["nota"], []) + by_amount_day.get((cents, dt), [])
            )}.values()
            for mov in candidates:
                if abs((dt - mov["_day"]).days) > 45:
                    continue
                note_equal = bool(mov["nota"] and mov["nota"] == d["nota"])
                amount_equal = cents == mov["_cents"]
                if note_equal and amount_equal:
                    strong_candidates[d["id"]].append(mov["id"])
                    ledger_to_docs[mov["id"]].append(d["id"])
                elif note_equal or (amount_equal and dt == mov["_day"]):
                    near_candidates[d["id"]].append((mov["id"], note_equal, amount_equal))
        matched = set()
        ledger_by_id = {record["id"]: record for record in ledger}
        for d in docs:
            choices = strong_candidates[d["id"]]
            if len(choices) == 1 and len(ledger_to_docs[choices[0]]) == 1:
                movimento = ledger_by_id[choices[0]]
                explicita = movimento["nota_explicita"]
                mesma_data = d["data"] == movimento["data"]
                d["situacao"] = ("DATA_DIFERENTE" if not mesma_data else
                                 "CONCILIADO" if explicita else "PROVAVEL")
                d["razao_id"] = choices[0]
                d["criterio"] = (f"Documento e valor coincidem, mas a data do Razão é {movimento['data']}; confirme o período de escrituração."
                                  if not mesma_data else
                                  "Conta, documento explícito, valor e data iguais; correspondência única."
                                  if explicita else
                                  "Número inicial do histórico pode ser NF; nota, valor e data sugerem correspondência, mas exigem confirmação.")
                if explicita and mesma_data:
                    matched.add(choices[0])
            elif choices:
                d["situacao"] = "AMBIGUO"
                d["razao_id"] = ""
                d["criterio"] = "Há mais de uma correspondência possível para nota e valor."
            else:
                near = near_candidates[d["id"]]
                if len(near) == 1 and near[0][1] and not near[0][2] and ledger_by_id[near[0][0]]["nota_explicita"]:
                    d["situacao"] = "VALOR_DIFERENTE"
                    d["razao_id"] = near[0][0]
                    d["criterio"] = "Nota identificada na conta, mas valor contábil diferente."
                elif near:
                    d["situacao"] = "AMBIGUO"
                    d["razao_id"] = ""
                    d["criterio"] = "Existe indício por nota ou por data/valor, sem confirmação suficiente."
                else:
                    d["situacao"] = "SEM_LANCAMENTO_IDENTIFICADO"
                    d["razao_id"] = ""
                    d["criterio"] = "Nenhum lançamento identificado pelos critérios disponíveis."
        possible_ids = {ref for choices in strong_candidates.values() for ref in choices}
        possible_ids |= {ref for choices in near_candidates.values() for ref, *_ in choices}
        remaining = []
        for mov in ledger:
            if mov["id"] in matched:
                continue
            mov = {key: val for key, val in mov.items() if not key.startswith("_")}
            mov["situacao"] = ("CORRESPONDENCIA_EM_ANALISE" if mov["id"] in possible_ids
                               else "DOCUMENTOS_NAO_IDENTIFICAVEIS" if not docs
                               else "SEM_DOCUMENTO_IDENTIFICADO")
            remaining.append(mov)
        by_acc = []
        for acc in row["detalhes_fiscais"]:
            acc_docs = [d for d in docs if d["acumulador"] == str(acc["codigo"])]
            qty = Counter(d["situacao"] for d in acc_docs)
            by_acc.append({
                "codigo": str(acc["codigo"]), "descricao": acc.get("descricao", ""),
                "valor_resumo": acc["valor"], "valor_documentos": round(sum(d["valor"] for d in acc_docs), 2),
                "quantidade_documentos": len(acc_docs), "conciliados": qty["CONCILIADO"],
                "pendentes": sum(v for k, v in qty.items() if k not in {"CONCILIADO", "AMBIGUO"}),
                "ambiguos": qty["AMBIGUO"],
                "detalhamento_disponivel": bool(acc_docs),
            })
        counts = Counter(d["situacao"] for d in docs)
        result.append({
            "conta": account, "tipo": tipo, "situacao_inicial": row["situacao"],
            "fiscal": row["fiscal"], "contabil": row["contabil"], "diferenca": row["diferenca"],
            # A tela prioriza pendências. O contexto interno nunca passa por este corte.
            "acumuladores": by_acc, "documentos": docs if completo else
                sorted(docs, key=lambda d: d["situacao"] == "CONCILIADO")[:300],
            "documentos_total": len(docs), "razao_pendente": remaining if completo else remaining[:300],
            "razao_pendente_total": len(remaining),
            "resumo": {"conciliados": counts["CONCILIADO"],
                       "ambiguos": counts["AMBIGUO"],
                       "pendentes": len(docs) - counts["CONCILIADO"] - counts["AMBIGUO"] + len([
                           item for item in remaining if item["situacao"] == "SEM_DOCUMENTO_IDENTIFICADO"
                       ])},
        })
        if not completo and (len(docs) > 300 or len(remaining) > 300):
            warnings.append(f"Conta {account}: a tela mostra até 300 documentos e lançamentos pendentes; "
                            "as contagens consideram todos os registros.")
    return {
        "filial": preview["filial_aplicada"], "empresa_nome": preview["empresa_nome"],
        "periodo": preview["periodo_fiscal"], "tipos_investigados": sorted(reports),
        "contas": result, "avisos": warnings,
        "resumo": {
            "contas": len(result),
            "conciliados": sum(r["resumo"]["conciliados"] for r in result),
            "ambiguos": sum(r["resumo"]["ambiguos"] for r in result),
            "pendentes": sum(r["resumo"]["pendentes"] for r in result),
        },
    }



def preparar_relatorio_pendencias_para_ia(acumuladores_bytes, acumuladores_nome, razao_bytes,
                                        razao_nome, entradas=None, saidas=None, filial=""):
    """Monta somente pendências e lançamentos não conciliados para provedores gratuitos."""
    preview = conferencia_fiscal_preview(
        acumuladores_bytes, acumuladores_nome, razao_bytes, razao_nome,
        filial_alvo=filial or None,
    )
    investigation = investigar_documentos(
        acumuladores_bytes, acumuladores_nome, razao_bytes, razao_nome, entradas, saidas, filial,
        completo=True, preview=preview,
    )
    selected = {}
    docs_to_ai = {}
    ledger_to_ai = []
    coverage = {}
    for item in investigation["contas"]:
        account, tipo = item["conta"], item["tipo"]
        pending_docs = [d for d in item["documentos"] if d["situacao"] != "CONCILIADO"]
        other_ledger = item["razao_pendente"]
        if not pending_docs and not other_ledger:
            continue
        selected[(account, tipo)] = True
        key = account + ":" + tipo
        # Prioriza diferenças concretas antes de indícios ambíguos. A amostra
        # econômica é explícita e é escolhida entre TODAS as pendências locais.
        priority = {"VALOR_DIFERENTE": 0, "DATA_DIFERENTE": 1,
                    "SEM_LANCAMENTO_IDENTIFICADO": 2, "PROVAVEL": 3, "AMBIGUO": 4}
        pending_docs.sort(key=lambda d: priority.get(d["situacao"], 5))
        chosen_docs = pending_docs[:30]
        related = {d["razao_id"] for d in chosen_docs if d.get("razao_id")}
        other_ledger = sorted(other_ledger, key=lambda m: (m["id"] not in related,
                              m["situacao"] != "SEM_DOCUMENTO_IDENTIFICADO"))
        chosen_ledger = other_ledger[:30]
        coverage[key] = {"documentos_enviados": len(chosen_docs),
                         "documentos_pendentes": len(pending_docs),
                         "lancamentos_enviados": len(chosen_ledger),
                         "lancamentos_pendentes": len(other_ledger),
                         "amostra": len(chosen_docs) < len(pending_docs) or len(chosen_ledger) < len(other_ledger)}
        docs_to_ai[key] = [
            {"referencia": d["id"], "razao_id": d.get("razao_id", "").replace("R-", "L", 1),
             "acumulador": d["acumulador"], "nota": d["nota"],
             "serie": d["serie"], "data": d["data"], "cfop": d["cfop"],
             "valor_brl": f"R$ {d['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
             "situacao": d["situacao"], "criterio": d["criterio"]}
            for d in chosen_docs
        ]
        for mov in chosen_ledger:
            ledger_to_ai.append({
                "_referencia_ia": mov["id"].replace("R-", "L", 1),
                "conta": account, "data": mov["data"],
                "historico": mov["historico"], "contrapartida": mov["contrapartida"],
                "debito": mov["valor"] if tipo != "SAÍDAS" else 0,
                "credito": mov["valor"] if tipo == "SAÍDAS" else 0,
                "natureza": "CRÉDITO" if tipo == "SAÍDAS" else "DÉBITO",
                "classificacao": mov["situacao"],
            })
    preview["contas"] = [r for r in preview["contas"] if (r["conta"], r["tipo"]) in selected]
    preview["lancamentos"] = ledger_to_ai
    preview["documentos_pendentes"] = docs_to_ai
    preview["cobertura_documental"] = coverage
    preview["avisos"] = list(preview.get("avisos", [])) + investigation["avisos"]
    preview["fonte_fiscal"] = ("Acompanhamento de Entradas/Saídas: somente documentos "
                               "com correspondência ambígua ou pendente, por acumulador.")
    preview["escopo_razao"] = "Somente lançamentos contábeis não conciliados na investigação documental."
    return preview

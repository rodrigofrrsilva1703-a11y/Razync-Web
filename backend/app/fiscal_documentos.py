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


def _parceiro_chave(texto):
    return re.sub(r"[^A-Z0-9]", "", _rotulo(texto))


def _parceiro_historico(texto):
    # Somente o parceiro exposto depois do separador, sem aproximação de nomes.
    parts = re.split(r"\s+-\s+", str(texto or ""), maxsplit=1)
    return _parceiro_chave(parts[1]) if len(parts) == 2 else ""


def _serie_historico(texto):
    match = re.search(r"\bS[ÉE]RIE\s*[:.-]?\s*([A-Z0-9]{1,12})\b", str(texto or ""), re.I)
    return _nota(match.group(1)) if match else ""


def _composicao_diferenca(row, docs, ledger, comparisons):
    """Particiona os valores sem duplicar candidatos compartilhados.

    A identidade fecha em centavos mesmo com vínculos ambíguos. Seu fechamento
    explica a aritmética, sem transformar indícios em conciliações confirmadas.
    """
    account = str(row["conta"])
    refs = {m["id"] for c in comparisons for m in c["lancamentos"] if str(m.get("conta", account)) == account}
    fiscal_linked = sum(_centavos(c["valor_fiscal"]) for c in comparisons
                        if any(str(m.get("conta", account)) == account for m in c["lancamentos"]))
    ledger_linked = sum(_centavos(m["valor"]) for m in ledger if m["id"] in refs)
    fiscal_read = sum(_centavos(d["valor"]) for d in docs)
    ledger_total = sum(_centavos(m["valor"]) for m in ledger)
    entries = [
        ("vinculados", "Diferenças nos vínculos encontrados ou em análise", ledger_linked - fiscal_linked),
        ("razao_sem_vinculo", "Movimentos do Razão sem vínculo", ledger_total - ledger_linked),
        ("fiscal_sem_vinculo", "Documentos fiscais sem vínculo nesta conta", -(fiscal_read - fiscal_linked)),
        ("cobertura", "Diferença entre os documentos lidos e o resumo fiscal", fiscal_read - _centavos(row["fiscal"])),
        ("fora_inicial", "Movimentos separados na conferência inicial", -(ledger_total - _centavos(row["contabil"]))),
    ]
    total = sum(value for _, _, value in entries)
    return {"itens": [{"codigo": key, "descricao": title, "valor": value / 100} for key, title, value in entries],
            "total": total / 100, "confere_com_inicial": total == _centavos(row["diferenca"]),
            "documentos_lidos": fiscal_read / 100, "razao_completo_conta": ledger_total / 100,
            "vinculos_incertos": any(c["situacao"] in {"AMBIGUO", "PROVAVEL", "ESTORNO_EM_ANALISE", "CONTA_DIFERENTE"} for c in comparisons)}


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
                                             razao_bytes, razao_nome, filial_alvo=filial or None, incluir_razao_completo=True)
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
    # Índice da filial já validada para indicar possíveis contas diferentes.
    other_accounts = defaultdict(list)
    for i, mov in enumerate(preview.get("_razao_completo", preview["lancamentos"])):
        note = _nota_historico(mov.get("historico")) or _nota_inferida_historico(mov.get("historico"))
        if not note:
            continue
        for tipo, side in (("ENTRADAS", "debito"), ("SAÍDAS", "credito")):
            amount = _centavos(mov.get(side))
            if amount:
                other_accounts[(tipo, note, str(mov.get("data", "")), amount)].append({
                    "id": mov.get("id", f"R-{i+1}"), "conta": str(mov["conta"]),
                    "serie": _serie_historico(mov.get("historico")),
                    "data": str(mov.get("data", "")), "valor": amount / 100,
                    "historico": str(mov.get("historico", "")),
                    "contrapartida": mov.get("contrapartida", ""),
                })
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
                "serie": _serie_historico(mov.get("historico", "")),
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
            # Dois indícios bastam para reconhecer ambiguidade; não percorra
            # milhares de pagamentos de mesmo valor para cada documento.
            if not mov["nota"]:
                bucket = by_amount_day[(mov["_cents"], mov_day)]
                if len(bucket) < 2:
                    bucket.append(mov)
        for d in docs:
            dt = datetime.strptime(d["data"], "%d/%m/%Y").date()
            cents = _centavos(d["valor"])
            candidates = by_note.get(d["nota"]) or by_amount_day.get((cents, dt), [])
            reducing = [m for m in by_note.get(d["nota"], []) if m["_cents"] < 0 and m["nota_explicita"]
                        and abs((dt - m["_day"]).days) <= 45
                        and (not m["serie"] or not d["serie"] or m["serie"] == _nota(d["serie"]))
                        and (not _parceiro_historico(m["historico"]) or not d.get("parceiro") or
                             _parceiro_historico(m["historico"]) == _parceiro_chave(d["parceiro"]))]
            if reducing:
                d["_tem_estorno"] = True
            for mov in candidates:
                if abs((dt - mov["_day"]).days) > 45:
                    continue
                if mov["serie"] and d["serie"] and mov["serie"] != _nota(d["serie"]):
                    continue
                partner = _parceiro_historico(mov["historico"])
                if partner and d.get("parceiro") and partner != _parceiro_chave(d["parceiro"]):
                    continue
                note_equal = bool(mov["nota"] and mov["nota"] == d["nota"])
                if mov["nota_explicita"] and not note_equal:
                    continue  # Outra NF explícita não vira candidata só pelo valor.
                amount_equal = cents == mov["_cents"]
                if note_equal and amount_equal and not d.get("_tem_estorno"):
                    strong_candidates[d["id"]].append(mov["id"])
                    ledger_to_docs[mov["id"]].append(d["id"])
                elif note_equal or (amount_equal and dt == mov["_day"]):
                    near_candidates[d["id"]].append((mov["id"], note_equal, amount_equal))
        ledger_by_id = {record["id"]: record for record in ledger}
        # Repetições de número em competências diferentes: prefira a data exata
        # antes de validar a exclusividade nas duas direções.
        ledger_to_docs.clear()
        for d in docs:
            exact_day = [ref for ref in strong_candidates[d["id"]] if ledger_by_id[ref]["data"] == d["data"]]
            if exact_day:
                strong_candidates[d["id"]] = exact_day
            for ref in strong_candidates[d["id"]]:
                ledger_to_docs[ref].append(d["id"])
        matched = set()
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
                if len(near) == 1 and near[0][1] and not near[0][2] and ledger_by_id[near[0][0]]["nota_explicita"] and not ledger_to_docs[near[0][0]]:
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
        # Uma NF pode ser desdobrada em CFOPs e em frete/despesas acessórias.
        # Agrupe apenas a mesma nota, data e parceiro explicitamente presente.
        # Linhas idênticas repetidas continuam ambíguas (não provar duplicidade).
        doc_groups = defaultdict(list)
        for d in docs:
            if d["situacao"] != "CONCILIADO" and d.get("parceiro") and not d.get("_tem_estorno"):
                doc_groups[(d["nota"], d["data"], _parceiro_chave(d["parceiro"]), d["serie"])].append(d)
        parcel_index = defaultdict(list)
        for mov in ledger:
            partner = _parceiro_historico(mov["historico"])
            if mov["id"] not in matched and mov["nota"] and partner:
                parcel_index[(mov["nota"], mov["data"], partner)].append(mov)
        identity_counts = Counter(key[:3] for key in doc_groups)
        for key, parts in doc_groups.items():
            movements = [m for m in parcel_index.get(key[:3], [])
                         if not m["serie"] or not key[3] or m["serie"] == _nota(key[3])]
            if not movements or identity_counts[key[:3]] != 1:
                continue
            if len({m["serie"] for m in movements if m["serie"]}) > 1:
                continue
            signatures = [(d["acumulador"], d["cfop"], _centavos(d["valor"])) for d in parts]
            if len(set(signatures)) != len(signatures):
                continue
            mov_signatures = [(m["historico"], m["_cents"], m["contrapartida"]) for m in movements]
            if len(set(mov_signatures)) != len(mov_signatures):
                continue  # Parcelas indistinguíveis não comprovam um vínculo único.
            # Não substitua vínculo único individual por outro agrupamento.
            if len(parts) == len(movements) == 1 and parts[0].get("razao_id"):
                continue
            fiscal_cents = sum(_centavos(d["valor"]) for d in parts)
            ledger_cents = sum(m["_cents"] for m in movements)
            explicit = all(m["nota_explicita"] for m in movements)
            status = ("CONCILIADO" if explicit else "PROVAVEL") if fiscal_cents == ledger_cents else "VALOR_DIFERENTE" if explicit else "PROVAVEL"
            ident = parts[0]["id"]
            for d in parts:
                d.update(situacao=status, razao_id=movements[0]["id"],
                         razao_ids=[m["id"] for m in movements], documento_grupo_id=ident,
                         valor_fiscal_grupo=fiscal_cents / 100,
                         valor_razao_candidato=ledger_cents / 100,
                         data_razao_candidato=key[1],
                         diferenca_candidato=(ledger_cents - fiscal_cents) / 100,
                         criterio=f"Mesma nota, data e parceiro: {len(parts)} linha(s) fiscal(is) × {len(movements)} lançamento(s) no Razão. " +
                                  ("Soma das parcelas confere." if fiscal_cents == ledger_cents else "Soma das parcelas apresenta diferença de valor.") +
                                  (" Número sem indicação explícita de NF: confirme o documento." if not explicit else ""))
            if status == "CONCILIADO":
                matched.update(m["id"] for m in movements)
        for document in docs:
            if document.pop("_tem_estorno", False):
                refs = list(dict.fromkeys(ref for ref, *_ in near_candidates[document["id"]]))
                if refs:
                    document.update(situacao="ESTORNO_EM_ANALISE", razao_id=refs[0], razao_ids=refs,
                                    documento_grupo_id=document["id"], valor_fiscal_grupo=document["valor"],
                                    valor_razao_candidato=sum(ledger_by_id[ref]["_cents"] for ref in refs) / 100,
                                    data_razao_candidato=ledger_by_id[refs[0]]["data"],
                                    criterio="Há valores negativos vinculados à mesma nota na conta. Compare o lançamento original e os redutores antes de confirmar a conciliação.")
            if document.get("documento_grupo_id"):
                continue
            candidate = ledger_by_id.get(document.get("razao_id"))
            if candidate and document["situacao"] != "CONCILIADO":
                document["valor_razao_candidato"] = candidate["valor"]
                document["data_razao_candidato"] = candidate["data"]
                document["diferenca_candidato"] = (_centavos(candidate["valor"]) - _centavos(document["valor"])) / 100
        reversals = defaultdict(list)
        for d in docs:
            if d["situacao"] == "ESTORNO_EM_ANALISE":
                reversals[(d["nota"], d["data"], _parceiro_chave(d.get("parceiro")), d["serie"])].append(d)
        for parts in reversals.values():
            refs = list(dict.fromkeys(ref for d in parts for ref in d.get("razao_ids", [])))
            total_fiscal = sum(_centavos(d["valor"]) for d in parts) / 100
            total_ledger = sum(ledger_by_id[ref]["_cents"] for ref in refs) / 100
            for d in parts:
                d.update(documento_grupo_id=parts[0]["id"], razao_ids=refs, razao_id=refs[0],
                         valor_fiscal_grupo=total_fiscal, valor_razao_candidato=total_ledger,
                         diferenca_candidato=round(total_ledger - total_fiscal, 2))
        comparisons = []
        grouped = defaultdict(list)
        for d in docs:
            grouped[d.get("documento_grupo_id", d["id"])].append(d)
        assigned = set()
        for parts in grouped.values():
            d = parts[0]
            refs = d.get("razao_ids") or ([d["razao_id"]] if d.get("razao_id") else [])
            candidates = [ledger_by_id[ref] for ref in refs if ref in ledger_by_id]
            if not candidates and d["situacao"] == "SEM_LANCAMENTO_IDENTIFICADO":
                alternatives = [m for m in other_accounts.get((tipo, d["nota"], d["data"], _centavos(d["valor"])), [])
                                if m["conta"] != account and _parceiro_historico(m["historico"]) == _parceiro_chave(d.get("parceiro", ""))
                                and d.get("parceiro") and (not m.get("serie") or not d["serie"] or m["serie"] == _nota(d["serie"]))]
                if len(alternatives) == 1:
                    candidates = alternatives
                    d.update(situacao="CONTA_DIFERENTE", criterio="Nota, data, valor e parceiro coincidem em outra conta; confirme o vínculo e o mapeamento do acumulador.")
            if not candidates and d["situacao"] == "AMBIGUO":
                refs = list(dict.fromkeys(strong_candidates[d["id"]] + [ref for ref, *_ in near_candidates[d["id"]]]))
                candidates = [ledger_by_id[ref] for ref in refs]
            assigned.update(m["id"] for m in candidates if str(m.get("conta", account)) == account)
            fiscal_value = sum(_centavos(part["valor"]) for part in parts) / 100
            total = sum(_centavos(m["valor"]) for m in candidates) / 100 if candidates and d["situacao"] != "AMBIGUO" else None
            comparisons.append({
                "id": d["id"], "nota": d["nota"], "serie": d["serie"], "data": d["data"],
                "parceiro": d.get("parceiro", ""), "situacao": d["situacao"], "criterio": d["criterio"],
                "valor_fiscal": fiscal_value, "valor_razao": total,
                "diferenca": round(total - fiscal_value, 2) if total is not None else None,
                "linhas_fiscais": [{k: part[k] for k in ("id", "acumulador", "cfop", "valor", "linha_origem")} for part in parts],
                "lancamentos": [{k: v for k, v in m.items() if not k.startswith("_")} for m in candidates],
            })
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
            # A paginação é visual; nenhum registro é descartado no servidor.
            "descricao": row.get("descricao", ""),
            "comparacoes": comparisons,
            "composicao": _composicao_diferenca(row, docs, ledger, comparisons),
            "razao_sem_vinculo": [m for m in remaining if m["id"] not in assigned],
            "situacoes": dict(Counter(c["situacao"] for c in comparisons)),
            "acumuladores": by_acc, "documentos": sorted(docs, key=lambda d: d["situacao"] == "CONCILIADO"),
            "documentos_total": len(docs), "razao_pendente": remaining,
            "razao_pendente_total": len(remaining),
            "resumo": {"conciliados": counts["CONCILIADO"],
                       "ambiguos": counts["AMBIGUO"],
                       "pendentes": len(docs) - counts["CONCILIADO"] - counts["AMBIGUO"] + len([
                           item for item in remaining if item["situacao"] == "SEM_DOCUMENTO_IDENTIFICADO"
                       ])},
        })
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
                                        razao_nome, entradas=None, saidas=None, filial="", *,
                                        manter_outros_tipos=False):
    """Monta somente pendências e lançamentos não conciliados para provedores gratuitos."""
    preview = conferencia_fiscal_preview(
        acumuladores_bytes, acumuladores_nome, razao_bytes, razao_nome,
        filial_alvo=filial or None, incluir_razao_completo=True,
    )
    investigation = investigar_documentos(
        acumuladores_bytes, acumuladores_nome, razao_bytes, razao_nome, entradas, saidas, filial,
        completo=True, preview=preview,
    )
    selected = {}
    docs_to_ai = {}
    ledger_to_ai = []
    coverage = {}
    summaries = {}
    resolved = []
    investigated = set(investigation["tipos_investigados"])
    for item in investigation["contas"]:
        account, tipo = item["conta"], item["tipo"]
        pending_docs = [d for d in item["documentos"] if d["situacao"] != "CONCILIADO"]
        other_ledger = item["razao_pendente"]
        key = account + ":" + tipo
        summaries[key] = {
            "tipo": tipo, "documentos_lidos": item["documentos_total"],
            "conciliados": item["resumo"]["conciliados"], "documentos_pendentes": len(pending_docs),
            "movimentos_pendentes": len(other_ledger),
            "situacoes": dict(Counter(d["situacao"] for d in item["documentos"])),
            "composicao": item.get("composicao", {}),
        }
        if not pending_docs and not other_ledger:
            resolved.append({"conta": account, "tipo": tipo, "documentos": item["documentos_total"]})
            continue
        selected[(account, tipo)] = True
        key = account + ":" + tipo
        # Prioriza diferenças concretas antes de indícios ambíguos. A amostra
        # econômica é explícita e é escolhida entre TODAS as pendências locais.
        priority = {"VALOR_DIFERENTE": 0, "ESTORNO_EM_ANALISE": 1, "CONTA_DIFERENTE": 2, "DATA_DIFERENTE": 3,
                    "SEM_LANCAMENTO_IDENTIFICADO": 4, "PROVAVEL": 5, "AMBIGUO": 6}
        pending_docs.sort(key=lambda d: priority.get(d["situacao"], 5))
        chosen_docs = pending_docs[:30]
        related = {ref for d in chosen_docs for ref in (d.get("razao_ids") or ([d["razao_id"]] if d.get("razao_id") else []))}
        other_ledger = sorted(other_ledger, key=lambda m: (m["id"] not in related,
                              m["situacao"] != "SEM_DOCUMENTO_IDENTIFICADO"))
        chosen_ledger = other_ledger[:30]
        ledger_by_id = {mov["id"]: mov for mov in other_ledger}
        comparison_by_doc = {part["id"]: c for c in item.get("comparacoes", []) for part in c["linhas_fiscais"]}
        def comparison(document):
            def brl(value):
                return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            paired = comparison_by_doc.get(document["id"], {})
            if document["situacao"] == "CONTA_DIFERENTE" and paired.get("lancamentos"):
                found = paired["lancamentos"][0]
                return {"vinculo_confirmado": False, "conta_razao_candidato": found["conta"],
                        "data_razao_candidato": found["data"], "valor_razao_candidato_brl": brl(found["valor"]),
                        "diferenca_candidato_brl": brl(paired["diferenca"]),
                        "historico_candidato": found["historico"][:180]}
            candidate = ledger_by_id.get(document.get("razao_id"))
            if not candidate:
                return {"vinculo_confirmado": False}
            def brl(value):
                return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            # Cálculo em centavos. O candidato é indício, não integração comprovada.
            total = document.get("valor_razao_candidato", candidate["valor"])
            fiscal_total = document.get("valor_fiscal_grupo", document["valor"])
            difference = (_centavos(total) - _centavos(fiscal_total)) / 100
            return {"valor_razao_candidato_brl": brl(total),
                    "valor_fiscal_grupo_brl": brl(fiscal_total),
                    "diferenca_candidato_brl": brl(difference),
                    "data_razao_candidato": candidate["data"], "vinculo_confirmado": False}
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
             "situacao": d["situacao"], "criterio": d["criterio"], **comparison(d)}
            for d in chosen_docs
        ]
        for mov in chosen_ledger:
            ledger_to_ai.append({
                "_referencia_ia": mov["id"].replace("R-", "L", 1), "_tipo_ia": tipo,
                "conta": account, "data": mov["data"],
                "historico": mov["historico"], "contrapartida": mov["contrapartida"],
                "debito": mov["valor"] if tipo != "SAÍDAS" else 0,
                "credito": mov["valor"] if tipo == "SAÍDAS" else 0,
                "natureza": "CRÉDITO" if tipo == "SAÍDAS" else "DÉBITO",
                "classificacao": mov["situacao"],
            })
    if manter_outros_tipos:
        # Entradas não substituem a análise de Saídas, e vice-versa.
        for row in preview["contas"]:
            if row["tipo"] not in investigated:
                selected[(row["conta"], row["tipo"])] = True
        fallback_sides = defaultdict(set)
        for row in preview["contas"]:
            if row["tipo"] not in investigated:
                fallback_sides[row["conta"]].add((row["tipo"], "credito" if row["tipo"] == "SAÍDAS" else "debito"))
        for i, mov in enumerate(preview["lancamentos"], 1):
            for tipo, side in sorted(fallback_sides.get(mov["conta"], ())):
                if abs(float(mov.get(side, 0))) >= .005:
                    ledger_to_ai.append(dict(mov, _referencia_ia=f"L{i}", _tipo_ia=tipo))
    preview.pop("_razao_completo", None)  # Não enviar o Razão completo aos provedores de IA.
    preview["contas"] = [r for r in preview["contas"] if (r["conta"], r["tipo"]) in selected]
    preview["lancamentos"] = ledger_to_ai
    preview["documentos_pendentes"] = docs_to_ai
    preview["cobertura_documental"] = coverage
    preview["resumo_documental"] = summaries
    preview["apoio_documental"] = {"tipos": sorted(investigated),
        "documentos_lidos": sum(i["documentos_total"] for i in investigation["contas"]),
        "conciliados": investigation["resumo"]["conciliados"], "contas_resolvidas": resolved}
    preview["avisos"] = list(preview.get("avisos", [])) + investigation["avisos"]
    preview["fonte_fiscal"] = ("Resumo e Razão; Entradas/Saídas complementam os tipos investigados com totais locais e pendências selecionadas."
        if manter_outros_tipos else "Acompanhamento de Entradas/Saídas: somente documentos com correspondência ambígua ou pendente, por acumulador.")
    preview["escopo_razao"] = ("Nas contas com apoio documental: até 30 movimentos pendentes por conta/tipo. "
        "Nas demais: contexto original do Razão. Os totais documentais locais não são uma leitura integral pela IA."
        if manter_outros_tipos else "Somente lançamentos contábeis não conciliados na investigação documental.")
    return preview

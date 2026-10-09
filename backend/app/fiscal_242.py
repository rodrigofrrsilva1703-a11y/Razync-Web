"""Apresentação da conferência Fiscal x Contábil da empresa 242 no Razync Web.

Reutiliza o motor Domínio já migrado. A classificação dos históricos é preliminar:
uma igualdade aritmética não comprova por si só integração contábil correta.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

from razync.conferencia_fiscal import processar_conferencia


def _normalizar(texto) -> str:
    value = unicodedata.normalize("NFKD", str(texto or ""))
    return re.sub(r"\s+", " ", "".join(
        ch for ch in value if not unicodedata.combining(ch)
    ).upper()).strip()


def _csv_para_excel(conteudo: bytes, nome: str) -> tuple[bytes, str]:
    if Path(nome).suffix.lower() != ".csv":
        return conteudo, nome
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    inicio = texto[:8192]
    try:
        separador = csv.Sniffer().sniff(inicio, delimiters=";,\t").delimiter
    except csv.Error:
        separador = ";" if inicio.count(";") >= inicio.count(",") else ","
    linhas = list(csv.reader(io.StringIO(texto), delimiter=separador))
    if linhas and linhas[0] and linhas[0][0].lower().startswith("sep="):
        linhas = linhas[1:]
    if not linhas:
        raise ValueError("O Razão CSV está vazio.")

    # O Domínio exporta o Razão com blocos Conta + lançamentos.
    # Também aceita CSV em formato de tabela: Conta, Data, Histórico,
    # Débito, Crédito, Filial.
    cabecalho_indice = None
    colunas = {}
    for indice, linha in enumerate(linhas[:80]):
        nomes = [_normalizar(valor) for valor in linha]
        if "CONTA" in nomes and "DATA" in nomes and (
            "DEBITO" in nomes or "CREDITO" in nomes
        ):
            cabecalho_indice = indice
            colunas = {nome: pos for pos, nome in enumerate(nomes)}
            break

    if cabecalho_indice is not None:
        def ler(linha, *nomes):
            for nome in nomes:
                i = colunas.get(nome)
                if i is not None and i < len(linha):
                    return linha[i]
            return ""

        por_conta = defaultdict(list)
        nomes_contas = {}
        for linha in linhas[cabecalho_indice + 1:]:
            conta = re.sub(r"\D", "", str(ler(linha, "CONTA", "CONTA CONTABIL")))
            data = str(ler(linha, "DATA")).strip()
            if not conta or pd.isna(pd.to_datetime(data, dayfirst=True, errors="coerce")):
                continue
            nomes_contas[conta] = ler(
                linha, "DESCRICAO CONTA", "NOME DA CONTA", "DESCRICAO"
            ) or nomes_contas.get(conta, "")
            por_conta[conta].append([
                data,
                ler(linha, "LOTE"),
                ler(linha, "HISTORICO", "HISTORICO DO LANCAMENTO"),
                ler(linha, "CTA C PART", "CONTRAPARTIDA", "CONTA CONTRAPARTIDA"),
                ler(linha, "DEBITO"),
                ler(linha, "CREDITO"),
                ler(linha, "FILIAL", "CODIGO FILIAL", "COD FILIAL"),
            ])
        if not por_conta:
            raise ValueError("O CSV não possui lançamentos válidos de conta e data.")
        blocos = []
        for conta, movimentos in por_conta.items():
            blocos.append(["Conta", conta, "", "", "", nomes_contas.get(conta, "")])
            blocos.append(["Data", "Lote", "Histórico", "Cta C/Part", "Débito", "Crédito", "Filial"])
            blocos.extend(movimentos)
        linhas = blocos

    tamanho = max(len(linha) for linha in linhas)
    quadro = pd.DataFrame([linha + [""] * (tamanho - len(linha)) for linha in linhas])
    saida = io.BytesIO()
    quadro.to_excel(saida, index=False, header=False)
    return saida.getvalue(), "razao_convertido.xlsx"


def _periodo(dados: dict) -> dict:
    resposta = {}
    for campo in ("inicio", "fim"):
        data = pd.to_datetime(dados.get(campo), errors="coerce")
        resposta[campo] = data.strftime("%d/%m/%Y") if pd.notna(data) else ""
    return resposta


def conferencia_fiscal_preview(
    acumuladores_bytes: bytes, acumuladores_nome: str,
    razao_bytes: bytes, razao_nome: str,
    codigo_empresa: int | None = None, filial_alvo: str | None = None,
) -> dict:
    if not acumuladores_nome.lower().endswith((".xls", ".xlsx")):
        raise ValueError("Envie o Resumo por Acumulador em XLS ou XLSX.")
    if not razao_nome.lower().endswith((".xls", ".xlsx", ".csv")):
        raise ValueError("Envie o Razão em XLS, XLSX ou CSV.")
    if not acumuladores_bytes or not razao_bytes:
        raise ValueError("Envie os dois relatórios.")
    if len(acumuladores_bytes) > 25_000_000 or len(razao_bytes) > 25_000_000:
        raise ValueError("Cada arquivo deve ter no máximo 25 MB.")

    razao_bytes, razao_nome = _csv_para_excel(razao_bytes, razao_nome)
    resultado = processar_conferencia(
        acumuladores_bytes, acumuladores_nome,
        razao_bytes, razao_nome, filial_alvo=filial_alvo,
    )
    resumo = resultado.get("resumo", pd.DataFrame())
    detalhes = resultado.get("detalhes", pd.DataFrame())
    acumuladores = resultado.get("acumuladores", pd.DataFrame())
    if resumo.empty:
        raise ValueError("Nenhuma conta vinculada a acumuladores foi encontrada.")

    linhas = []
    for _, item in resumo.iterrows():
        conta, tipo = str(item["CONTA"]), str(item["TIPO"])
        vinculados = acumuladores.loc[
            acumuladores["CONTA"].astype(str).eq(conta)
            & acumuladores["TIPO"].astype(str).eq(tipo)
        ]
        descricoes = [
            texto for texto in dict.fromkeys(vinculados["DESCRIÇÃO"].fillna("").astype(str))
            if texto.strip()
        ]
        linhas.append({
            "conta": conta,
            "descricao": " | ".join(descricoes[:2]),
            "tipo": tipo,
            "acumuladores": str(item["ACUMULADORES"]),
            "detalhes_fiscais": [{"codigo": str(a["ACUMULADOR"]),
                "descricao": str(a["DESCRIÇÃO"]), "valor": round(float(a["VALOR_FISCAL"]), 2)}
                for _, a in vinculados.iterrows()],
            "fiscal": round(float(item["VALOR FISCAL"]), 2),
            "contabil": round(float(item["CONTÁBIL COMPATÍVEL"]), 2),
            "total_conta": round(float(item["TOTAL DA CONTA"]), 2),
            "diferenca": round(float(item["DIFERENÇA FISCAL"]), 2),
            "extras": int(item["LANÇAMENTOS EXTRAS"]),
            "sem_evidencia": int(item.get("FECHAMENTOS SEM EVIDÊNCIA", 0)),
            "situacao": str(item["SITUAÇÃO"]),
        })

    prioridade = {
        "REVISAR": 0, "AUSENTE NO CONTÁBIL": 1,
        "CONFERE COM ALERTAS": 2, "CONFERE": 3,
    }
    linhas.sort(key=lambda x: (prioridade.get(x["situacao"], 9), x["conta"], x["tipo"]))

    movimentos = []
    for _, mov in detalhes.iterrows():
        data = pd.to_datetime(mov.get("DATA"), errors="coerce")
        movimentos.append({
            "conta": str(mov.get("CONTA", "")),
            "data": data.strftime("%d/%m/%Y") if pd.notna(data) else "",
            "historico": str(mov.get("HISTÓRICO", "")),
            "contrapartida": str(mov.get("CONTRAPARTIDA", "")),
            "debito": round(float(mov.get("DÉBITO", 0) or 0), 2),
            "credito": round(float(mov.get("CRÉDITO", 0) or 0), 2),
            "natureza": str(mov.get("NATUREZA", "")),
            "classificacao": str(mov.get("CLASSIFICAÇÃO", "")),
        })

    situacoes = [item["situacao"] for item in linhas]
    resumo_contagens = {
        "total": len(linhas),
        "conferem": situacoes.count("CONFERE"),
        "com_alertas": situacoes.count("CONFERE COM ALERTAS"),
        "revisar": situacoes.count("REVISAR") + situacoes.count("AUSENTE NO CONTÁBIL"),
    }

    sem_conta = resultado.get("sem_conta", [])
    avisos = [
        "Conferência preliminar: igualdade de valores e classificação por histórico não "
        "substituem a validação dos documentos e contrapartidas.",
    ]
    if sem_conta:
        avisos.append(
            f"{len(sem_conta)} acumulador(es) sem conta vinculada foram excluídos "
            "da comparação e estão disponíveis para revisão abaixo."
        )
    if any(linha["sem_evidencia"] for linha in linhas):
        avisos.append(
            "Contas que fecharam apenas pelo valor, sem histórico fiscal comprovado, "
            "estão marcadas como 'Com alertas'."
        )
    fiscal = _periodo(resultado.get("periodo_fiscal", {}))
    razao = _periodo(resultado.get("periodo_razao", {}))
    if fiscal["inicio"] and razao["inicio"] and fiscal != razao:
        avisos.append("Os períodos informados nos dois relatórios não coincidem. Confira a competência.")

    return {
        "empresa": codigo_empresa,
        "filial_aplicada": str(resultado.get("filial_aplicada", "")),
        "filiais_encontradas": resultado.get("filiais_encontradas", []),
        "periodo_fiscal": fiscal,
        "periodo_razao": razao,
        "resumo": resumo_contagens,
        "contas": linhas,
        "sem_conta": sem_conta,
        "lancamentos": movimentos,
        "avisos": avisos,
    }

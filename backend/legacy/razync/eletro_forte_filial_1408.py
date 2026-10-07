"""Montagem bancária específica da Eletro Forte Filial 1408."""
from __future__ import annotations

from collections import defaultdict
import re
import unicodedata

import pandas as pd

from razync.eletro_forte import COLUNAS_MODELO, processar_recebidos


CONTA_ITAU_1408 = "512"


def _texto_normalizado(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return texto.encode("ascii", "ignore").decode().upper()


def _eh_recebimento_cartao(valor: str) -> bool:
    texto = _texto_normalizado(valor)
    return "RECEBIMENTO REDE" in texto or any(
        bandeira in texto for bandeira in ("REDE VISA", "REDE MAST", "REDE ELO")
    )


def _remover_cpf_cnpj(valor: str) -> str:
    texto = str(valor or "")
    texto = re.sub(
        r"(?<!\d)(?:\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|"
        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)",
        "",
        texto,
    )
    texto = re.sub(r"\b(?:CNPJ|CPF)(?:/CPF)?\s*[:\-]?\s*", "", texto, flags=re.I)
    return re.sub(r"\s{2,}", " ", texto).strip(" -|")


def _chave(data, valor) -> tuple[pd.Timestamp, int]:
    return pd.Timestamp(data).normalize(), int(round(float(valor) * 100))


def _centavos(valor) -> int:
    return int(round(float(valor) * 100))


def _grupos_francesinhas(francesinhas: pd.DataFrame):
    """Separa a francesinha por data e arquivo para não misturar boletos do mesmo dia."""
    if francesinhas is None or francesinhas.empty:
        return []
    dados = francesinhas.copy()
    dados["DATA"] = pd.to_datetime(dados["DATA"], dayfirst=True, errors="coerce")
    dados["VALOR"] = pd.to_numeric(dados["VALOR"], errors="coerce")
    dados = dados.dropna(subset=["DATA", "VALOR"])
    if dados.empty:
        return []

    if "ARQUIVO" not in dados.columns:
        dados["ARQUIVO"] = ""
    grupos = []
    for (data, arquivo), grupo in dados.groupby(
        [dados["DATA"].dt.normalize(), dados["ARQUIVO"].fillna("").astype(str)],
        sort=True,
        dropna=False,
    ):
        parte = grupo.copy().reset_index(drop=True)
        grupos.append({
            "data": pd.Timestamp(data).normalize(),
            "arquivo": str(arquivo or ""),
            "total_centavos": sum(_centavos(v) for v in parte["VALOR"]),
            "dados": parte,
        })
    return grupos


def _selecionar_grupos_para_total(grupos, total_centavos):
    """Encontra um grupo ou uma combinação única de arquivos que feche o boleto."""
    disponiveis = list(grupos)
    exatos = sorted(
        [g for g in disponiveis if g["total_centavos"] == total_centavos],
        key=lambda g: (g.get("arquivo", ""), g["total_centavos"]),
    )
    if exatos:
        return [exatos[0]]

    # Normalmente há poucos PDFs por data. Busca combinações sem reutilizar grupos.
    if len(disponiveis) > 18:
        return None

    solucoes = []
    ordenados = sorted(disponiveis, key=lambda g: g["total_centavos"], reverse=True)

    def buscar(indice, faltante, escolhidos):
        if len(solucoes) > 1:
            return
        if faltante == 0:
            solucoes.append(list(escolhidos))
            return
        if faltante < 0 or indice >= len(ordenados):
            return
        restante_max = sum(max(0, g["total_centavos"]) for g in ordenados[indice:])
        if restante_max < faltante:
            return
        grupo = ordenados[indice]
        if 0 < grupo["total_centavos"] <= faltante:
            escolhidos.append(grupo)
            buscar(indice + 1, faltante - grupo["total_centavos"], escolhidos)
            escolhidos.pop()
        buscar(indice + 1, faltante, escolhidos)

    buscar(0, total_centavos, [])
    return solucoes[0] if solucoes else None


def montar_modelo_1408(
    lancamentos_extrato,
    conteudo_recebidos: bytes | None = None,
    ano_referencia: int | None = None,
    francesinhas: pd.DataFrame | None = None,
):
    """Usa o extrato como base e substitui BOLETO RECEBIDO pelo detalhamento das francesinhas."""
    modelo = pd.DataFrame(lancamentos_extrato).copy()
    if modelo.empty or not {"DATA", "VALOR"}.issubset(modelo.columns):
        raise ValueError("Nenhum movimento válido foi encontrado no extrato Itaú.")

    modelo["DATA"] = pd.to_datetime(modelo["DATA"], dayfirst=True, errors="coerce")
    modelo["VALOR"] = pd.to_numeric(modelo["VALOR"], errors="coerce")
    modelo = modelo.dropna(subset=["DATA", "VALOR"]).reset_index(drop=True)
    if modelo.empty:
        raise ValueError("O extrato Itaú não contém datas e valores válidos.")
    modelo["DESCRIÇÃO"] = "BANCO ITAÚ"
    modelo["DÉBITO"] = modelo["VALOR"].map(lambda v: CONTA_ITAU_1408 if v > 0 else "")
    modelo["CRÉDITO"] = modelo["VALOR"].map(lambda v: CONTA_ITAU_1408 if v < 0 else "")
    if "HISTÓRICO" not in modelo:
        modelo["HISTÓRICO"] = "MOVIMENTO ITAÚ"

    # Francesinhas têm prioridade sobre a planilha de Recebidos. Assim o histórico
    # BOLETO RECEBIDO não é apagado antes de o agregado ser localizado.
    grupos = _grupos_francesinhas(francesinhas)
    grupos_por_data = defaultdict(list)
    for grupo in grupos:
        grupos_por_data[grupo["data"]].append(grupo)

    usados = set()
    linhas_francesinhas = []
    indices_remover = []
    avisos_francesinhas = []
    grupos_francesinhas = 0
    boletos_encontrados = 0
    boletos_sem_correspondencia = 0

    boletos = modelo.loc[
        (modelo["VALOR"] > 0)
        & modelo["HISTÓRICO"].astype(str).str.contains(
            r"\bBOLETO\s+RECEBIDO\b", case=False, na=False, regex=True
        )
    ]

    for indice, linha in boletos.iterrows():
        boletos_encontrados += 1
        data = pd.Timestamp(linha["DATA"]).normalize()
        total_centavos = _centavos(linha["VALOR"])
        candidatos = [
            grupo for grupo in grupos_por_data.get(data, [])
            if id(grupo) not in usados
        ]
        selecionados = _selecionar_grupos_para_total(candidatos, total_centavos)
        if not selecionados:
            boletos_sem_correspondencia += 1
            total_francesinhas = sum(g["total_centavos"] for g in candidatos) / 100
            avisos_francesinhas.append(
                f"Boleto recebido de {data.strftime('%d/%m/%Y')} no valor de "
                f"R$ {float(linha['VALOR']):.2f} não foi desmembrado. "
                f"Francesinhas disponíveis na data: R$ {total_francesinhas:.2f}."
            )
            continue

        indices_remover.append(indice)
        for grupo in selecionados:
            usados.add(id(grupo))
            parte = grupo["dados"][COLUNAS_MODELO].copy()
            parte["DESCRIÇÃO"] = "BANCO ITAÚ"
            parte["DÉBITO"] = CONTA_ITAU_1408
            parte["CRÉDITO"] = ""
            linhas_francesinhas.append(parte)
        grupos_francesinhas += 1

    # Avisar francesinhas válidas que não encontraram um BOLETO RECEBIDO no extrato.
    grupos_nao_usados = [grupo for grupo in grupos if id(grupo) not in usados]
    for grupo in grupos_nao_usados:
        avisos_francesinhas.append(
            f"Francesinha {grupo['arquivo'] or 'sem nome'} de "
            f"{grupo['data'].strftime('%d/%m/%Y')} (R$ {grupo['total_centavos'] / 100:.2f}) "
            "não encontrou BOLETO RECEBIDO correspondente no extrato."
        )

    if indices_remover:
        modelo = modelo.drop(index=indices_remover).reset_index(drop=True)

    # A planilha de Recebidos detalha somente os movimentos que permaneceram no extrato.
    detalhes = defaultdict(list)
    if conteudo_recebidos:
        ano = int(ano_referencia or modelo["DATA"].dt.year.mode().iloc[0])
        grupos_recebidos = processar_recebidos(
            conteudo_recebidos, ano, CONTA_ITAU_1408
        )
        recebido = grupos_recebidos.get(CONTA_ITAU_1408, pd.DataFrame())
        for indice, linha in recebido.iterrows():
            detalhes[_chave(linha["DATA"], linha["VALOR"])].append((indice, linha))

    usados_recebidos = set()
    historicos_substituidos = 0
    for indice, linha in modelo.loc[modelo["VALOR"] > 0].iterrows():
        if _eh_recebimento_cartao(linha.get("HISTÓRICO", "")):
            continue
        candidatos = detalhes.get(_chave(linha["DATA"], linha["VALOR"]), [])
        candidato = next(
            (item for item in candidatos if item[0] not in usados_recebidos),
            None,
        )
        if candidato:
            usados_recebidos.add(candidato[0])
            modelo.at[indice, "HISTÓRICO"] = candidato[1]["HISTÓRICO"]
            historicos_substituidos += 1

    if linhas_francesinhas:
        modelo = pd.concat(
            [modelo[COLUNAS_MODELO], *linhas_francesinhas],
            ignore_index=True,
        )

    historico = modelo["HISTÓRICO"].fillna("").astype(str).map(_remover_cpf_cnpj)
    modelo["HISTÓRICO"] = [
        texto if texto.lower().startswith(("pago: ", "recebido: "))
        else ("Recebido: " if valor > 0 else "Pago: ") + texto
        for texto, valor in zip(historico, modelo["VALOR"])
    ]
    modelo = (
        modelo[COLUNAS_MODELO]
        .sort_values(["DATA"], kind="stable")
        .reset_index(drop=True)
    )
    resumo = {
        "movimentos_extrato": len(lancamentos_extrato),
        "historicos_substituidos": historicos_substituidos,
        "boletos_recebidos": boletos_encontrados,
        "boletos_desmembrados": grupos_francesinhas,
        "boletos_sem_correspondencia": boletos_sem_correspondencia,
        "grupos_francesinhas": grupos_francesinhas,
        "francesinhas_nao_usadas": len(grupos_nao_usados),
        "avisos_francesinhas": avisos_francesinhas,
        "linhas_finais": len(modelo),
    }
    return modelo, resumo


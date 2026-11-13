"""Leitor do PDF Aplicativo Santander Empresas, com Valor e Saldo.

Preserva históricos quebrados entre linhas e páginas e confere cada variação
de saldo na ordem decrescente exibida pelo aplicativo, em centavos.
"""
from __future__ import annotations

import io
import re
from decimal import Decimal

from pypdf import PdfReader

_DATE = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s+(.*)$")
_BR = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
_AMOUNTS = re.compile(rf"(?<!\d)(?P<valor>{_BR})\s+(?P<saldo>{_BR})(?!\d)")
_SKIP = re.compile(
    r"^(?:Aplicativo Santander Empresas|Per[ií]odos?:|Saldo dispon[ií]vel para uso:|"
    r"Data\s+Hist[oó]rico\s+Documento|Ag[eê]ncia:|Conta:|"
    r"Central de Atendimento|SAC\s*[-–]|Ouvidoria|"
    r"\d+\s*/\s*\d+\s*$)", re.I
)
_END = re.compile(r"^(?:Saldo de ContaMax|Saldo Dispon[ií]vel\s*$|Posi[cç][aã]o em:|"
                  r"Entenda a composi[cç][aã]o)", re.I)
_HEADER = re.compile(r"APLICATIVO\s+SANTANDER\s+EMPRESAS", re.I)


def parece_extrato_santander_aplicativo(texto: str) -> bool:
    return bool(_HEADER.search(texto or "") and
                re.search(r"Valor\s*\(R\$\)\s+Saldo\s*\(R\$\)", texto or "", re.I))


def _centavos(valor: str) -> int:
    numero = Decimal(valor.replace(".", "").replace(",", "."))
    return int(numero * 100)


def processar_extrato_santander_aplicativo_texto(
    texto: str, banco: str = "BANCO SANTANDER"
) -> list[dict]:
    """Retorna todas as movimentações, sem linhas de saldo ou de limites."""
    if not parece_extrato_santander_aplicativo(texto):
        raise ValueError("PDF não corresponde ao layout Aplicativo Santander Empresas.")
    registros = []
    atual = None
    terminada = False

    def fechar():
        if atual is None:
            return
        bruto = " ".join(atual["partes"])
        grupo = _AMOUNTS.search(bruto)
        if not grupo:
            raise ValueError("Extrato Santander incompleto: movimentação sem Valor e Saldo reconhecíveis.")
        saldo = _centavos(grupo.group("saldo"))
        valor = _centavos(grupo.group("valor"))
        if not valor:
            raise ValueError("Extrato Santander contém movimentação com valor zerado; revise a origem.")
        historico = re.sub(r"\s+", " ", (bruto[:grupo.start()] + " " + bruto[grupo.end():])).strip()
        if not historico:
            raise ValueError("Extrato Santander com histórico vazio; confira a exportação.")
        registros.append({
            "DESCRIÇÃO": banco, "DATA": atual["data"], "VALOR": valor / 100,
            "DÉBITO": "", "CRÉDITO": "", "HISTÓRICO": historico,
            "_SALDO_CENTAVOS": saldo, "_VALOR_CENTAVOS": valor,
        })

    for line in (texto or "").splitlines():
        linha = re.sub(r"\s+", " ", line).strip()
        if not linha:
            continue
        if _END.match(linha):
            fechar()
            atual = None
            terminada = True
        if terminada:
            continue
        if _SKIP.match(linha) or ("Agência:" in linha and "Conta:" in linha):
            continue
        registro = _DATE.match(linha)
        if registro:
            fechar()
            atual = {"data": registro.group(1), "partes": [registro.group(2)]}
        elif atual is not None:
            atual["partes"].append(linha)
    if not terminada:
        fechar()
    if not registros:
        raise ValueError("Nenhum lançamento foi encontrado no PDF Santander Empresas.")
    # Extrato em ordem decrescente: saldo do movimento mais recente menos
    # saldo do movimento anterior deve ser exatamente o valor do mais recente.
    for newer, older in zip(registros, registros[1:]):
        if newer["_SALDO_CENTAVOS"] - older["_SALDO_CENTAVOS"] != newer["_VALOR_CENTAVOS"]:
            raise ValueError(
                "Extrato Santander: sequência de saldos não confere. "
                "Verifique linhas não lidas ou páginas faltantes."
            )
    for record in registros:
        record.pop("_SALDO_CENTAVOS")
        record.pop("_VALOR_CENTAVOS")
    return registros


def processar_extrato_santander_aplicativo_pdf(content: bytes) -> list[dict]:
    if not content or len(content) > 25_000_000:
        raise ValueError("O PDF Santander está vazio ou excede 25 MB.")
    try:
        pdf = PdfReader(io.BytesIO(content), strict=False)
        if len(pdf.pages) > 100:
            raise ValueError("O PDF Santander possui mais de 100 páginas; envie um extrato por período.")
        texto = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Não foi possível ler o PDF Santander. Exporte novamente o PDF original.") from exc
    return processar_extrato_santander_aplicativo_texto(texto)

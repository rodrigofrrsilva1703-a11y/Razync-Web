"""Leitura de Razão contábil exportado pelo Domínio para a Base Inteligente."""

from __future__ import annotations

import io
import os
import re
import struct
import unicodedata

import pandas as pd


def _normalizar(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", "", texto)


def _conta(valor) -> str:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return ""
    texto = str(valor or "").strip()
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]
    return re.sub(r"\s+", "", texto)


def _numero(valor) -> float:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto or texto.casefold() == "nan":
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0



def _reparar_endereco_aba_ole(file_bytes: bytes):
    """Repara apenas BOUNDSHEET incorreto em XLS OLE, sem alterar as células.

    Alguns relatórios Domínio apontam BOUNDSHEET para um registro BLANK
    (0x0201), mesmo tendo BOF válido da planilha mais adiante no stream.
    Retorna uma cópia em memória do OLE original, ou None se ambíguo.
    """
    if not file_bytes.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) or len(file_bytes) < 512:
        return None
    try:
        def u16(offset):
            return struct.unpack_from("<H", file_bytes, offset)[0]

        def u32(offset):
            return struct.unpack_from("<I", file_bytes, offset)[0]

        tamanho_setor = 1 << u16(30)
        total_fat = u32(44)
        # Somente OLE com FAT inteiramente enumerada no cabeçalho.
        if tamanho_setor != 512 or u32(68) != 0xFFFFFFFE or u32(72) != 0:
            return None
        setores_fat = [
            u32(76 + 4 * n) for n in range(109)
            if u32(76 + 4 * n) not in (0xFFFFFFFF, 0xFFFFFFFE)
        ]
        if total_fat != len(setores_fat):
            return None
        fat = []
        for setor in setores_fat:
            inicio = (setor + 1) * tamanho_setor
            if inicio + tamanho_setor > len(file_bytes):
                return None
            fat.extend(struct.unpack_from("<128I", file_bytes, inicio))

        def cadeia(primeiro):
            ids, vistos = [], set()
            atual = primeiro
            while atual not in (0xFFFFFFFE, 0xFFFFFFFF):
                if (atual in vistos or atual >= len(fat)
                        or (atual + 1) * tamanho_setor >= len(file_bytes)
                        or len(ids) > 65536):
                    return None
                vistos.add(atual)
                ids.append(atual)
                atual = fat[atual]
            return ids

        def bytes_da_cadeia(ids):
            return b"".join(file_bytes[(s + 1) * tamanho_setor:
                                       (s + 2) * tamanho_setor] for s in ids)

        diretorio_ids = cadeia(u32(48))
        if not diretorio_ids:
            return None
        diretorio = bytes_da_cadeia(diretorio_ids)
        for posicao in range(0, len(diretorio), 128):
            entrada = diretorio[posicao:posicao + 128]
            if len(entrada) != 128:
                continue
            comprimento = struct.unpack_from("<H", entrada, 64)[0]
            if not 2 <= comprimento <= 64:
                continue
            nome = entrada[:comprimento - 2].decode("utf-16le")
            if nome not in ("Workbook", "Book"):
                continue
            inicio = struct.unpack_from("<I", entrada, 116)[0]
            comprimento_fluxo = struct.unpack_from("<Q", entrada, 120)[0]
            if not 4096 <= comprimento_fluxo <= 32 * 1024 * 1024:
                return None
            ids = cadeia(inicio)
            if not ids or len(ids) * tamanho_setor < comprimento_fluxo:
                return None
            fluxo = bytes_da_cadeia(ids)[:comprimento_fluxo]
            cabecalhos, cursor, fim_globais = [], 0, None
            while cursor + 4 <= len(fluxo):
                codigo, comprimento_registro = struct.unpack_from("<HH", fluxo, cursor)
                if cursor + 4 + comprimento_registro > len(fluxo):
                    return None
                if codigo == 0x0085 and comprimento_registro >= 6:
                    cabecalhos.append(cursor)
                cursor += 4 + comprimento_registro
                if codigo == 0x000A:
                    fim_globais = cursor
                    break
            if not cabecalhos or fim_globais is None:
                return None
            inicios = []
            for offset in range(fim_globais, len(fluxo) - 8):
                if fluxo[offset:offset + 2] not in (
                    b"\x09\x08", b"\x09\x04", b"\x09\x02", b"\x09\x00"
                ):
                    continue
                tamanho = struct.unpack_from("<H", fluxo, offset + 2)[0]
                if tamanho < 4 or offset + 4 + tamanho > len(fluxo):
                    continue
                versao, tipo = struct.unpack_from("<HH", fluxo, offset + 4)
                if (versao in (0x0200, 0x0300, 0x0400, 0x0500, 0x0600)
                        and tipo in (0x0010, 0x0020, 0x0040)):
                    inicios.append(offset)
            if len(inicios) != len(cabecalhos):
                return None
            reparado = bytearray(file_bytes)
            alteracoes = 0
            for cabecalho, destino in zip(cabecalhos, inicios):
                anterior = struct.unpack_from("<I", fluxo, cabecalho + 4)[0]
                if anterior == destino:
                    continue
                if anterior in inicios:
                    return None
                endereco_fluxo = cabecalho + 4
                deslocamento = endereco_fluxo % tamanho_setor
                if deslocamento > tamanho_setor - 4:
                    return None
                endereco_ole = (ids[endereco_fluxo // tamanho_setor] + 1) * tamanho_setor + deslocamento
                struct.pack_into("<I", reparado, endereco_ole, destino)
                alteracoes += 1
            return bytes(reparado) if alteracoes else None
    except (IndexError, ValueError, UnicodeError, struct.error):
        return None
    return None

def _recuperar_xls_biff_irregular(file_bytes: bytes, *, workbook: bool = False):
    try:
        from xlrd.compdoc import CompDoc

        documento = CompDoc(file_bytes, ignore_workbook_corruption=True)
        fluxo_original = (
            documento.get_named_stream("Workbook")
            or documento.get_named_stream("Book")
        )
        if not fluxo_original:
            return None
        fluxo = bytearray(fluxo_original)
        registros_abas = []
        posicao = 0
        fim_globais = None
        while posicao + 4 <= len(fluxo):
            codigo, tamanho = struct.unpack_from("<HH", fluxo, posicao)
            fim = posicao + 4 + tamanho
            if fim > len(fluxo):
                break
            if codigo == 0x0085 and tamanho >= 4:
                registros_abas.append(posicao)
            posicao = fim
            if codigo == 0x000A:
                fim_globais = posicao
                break
        if not registros_abas or fim_globais is None:
            return None

        # Recuperação conservadora: alguns relatórios têm o BOUNDSHEET
        # apontando para BLANK (0x0201) em vez do BOF da aba. O BOF BIFF8
        # verdadeiro é 0x0809; versões antigas usam 0x0409/0x0209/0x0009.
        # Validamos tamanho, versão e tipo de substream antes de corrigir.
        inicios = []
        vistos = set()
        for marcador in (b"\x09\x08", b"\x09\x04", b"\x09\x02", b"\x09\x00"):
            cursor = fim_globais
            while True:
                indice = fluxo.find(marcador, cursor)
                if indice < 0:
                    break
                cursor = indice + 2
                if indice in vistos or indice + 8 > len(fluxo):
                    continue
                tamanho = struct.unpack_from("<H", fluxo, indice + 2)[0]
                if tamanho < 4 or indice + 4 + tamanho > len(fluxo):
                    continue
                versao, tipo = struct.unpack_from("<HH", fluxo, indice + 4)
                if versao not in (0x0200, 0x0300, 0x0400, 0x0500, 0x0600):
                    continue
                if tipo not in (0x0010, 0x0020, 0x0040):
                    continue
                vistos.add(indice)
                inicios.append(indice)
        inicios.sort()
        if len(inicios) != len(registros_abas):
            # Arquivos ambíguos não são reescritos nem importados parcialmente.
            return None
        for registro, inicio in zip(registros_abas, inicios):
            struct.pack_into("<I", fluxo, registro + 4, inicio)
        xls = pd.ExcelFile(io.BytesIO(bytes(fluxo)), engine="xlrd")
        if workbook:
            return xls
        with xls:
            return pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=None, dtype=object)
    except Exception:
        return None


def _ler_bruto(file_bytes: bytes, filename: str):
    extensao = os.path.splitext(filename)[1].casefold()
    try:
        # Algumas exportações são XLSX (ZIP) com extensão .xls.
        # Priorizar a assinatura real do arquivo, nunca apenas o nome.
        if file_bytes.startswith(b"PK\x03\x04"):
            return pd.read_excel(io.BytesIO(file_bytes), header=None,
                                 dtype=object, engine="openpyxl")
        if extensao == ".xlsx":
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            return pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=None, dtype=object)
        if extensao == ".xls":
            try:
                return pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=object, engine="xlrd")
            except Exception:
                reparado = _reparar_endereco_aba_ole(file_bytes)
                if reparado is not None:
                    try:
                        return pd.read_excel(io.BytesIO(reparado), header=None,
                                             dtype=object, engine="xlrd")
                    except Exception:
                        pass
                try:
                    tabelas = pd.read_html(io.BytesIO(file_bytes), header=None)
                    if tabelas:
                        return tabelas[0]
                except Exception:
                    pass
                return _recuperar_xls_biff_irregular(file_bytes)
    except Exception:
        return None
    return None


def ler_razao_dominio_base(file_bytes: bytes, filename: str, contas_bancarias: dict):
    """Retorna lançamentos bancários do Razão com a contrapartida contábil."""
    bruto = _ler_bruto(file_bytes, filename)
    if bruto is None or bruto.empty:
        return []

    linha_cabecalho = None
    mapa = {}
    for indice, linha in bruto.iterrows():
        teste = {_normalizar(valor): coluna for coluna, valor in linha.items() if pd.notna(valor)}
        separado = "historico" in teste and "ctacpart" in teste
        if "data" in teste and (separado or "contrapartidahistorico" in teste):
            linha_cabecalho = indice
            mapa = teste
            break
    if linha_cabecalho is None:
        return []

    col_data = mapa["data"]
    col_contrapartida = mapa.get("ctacpart")
    col_historico = mapa["historico"] if col_contrapartida is not None else mapa["contrapartidahistorico"]
    col_debito = mapa.get("debito")
    col_credito = mapa.get("credito")
    if col_debito is None or col_credito is None:
        return []

    bancos_por_conta = {
        _conta(numero): banco for banco, numero in contas_bancarias.items()
    }
    banco_atual = ""
    conta_banco_atual = ""
    registros = []
    for _, linha in bruto.iloc[linha_cabecalho + 1 :].iterrows():
        primeiro = _normalizar(linha.iloc[0] if len(linha) else "")
        if primeiro == "conta":
            numero_conta = _conta(linha.iloc[1] if len(linha) > 1 else "")
            banco_atual = bancos_por_conta.get(numero_conta, "")
            conta_banco_atual = numero_conta if banco_atual else ""
            continue
        if not banco_atual:
            continue

        data = pd.to_datetime(linha.get(col_data), dayfirst=True, errors="coerce")
        historico_bruto = linha.get(col_historico)
        contrapartida = _conta(linha.get(col_contrapartida))
        if col_contrapartida is None and not pd.isna(historico_bruto):
            conta_e_descricao, _, historico_bruto = str(historico_bruto).partition("\n")
            match = re.fullmatch(r"\s*(\d+)\s*-\s*.+", conta_e_descricao.strip())
            contrapartida = match[1] if match else ""
        historico = (
            "" if pd.isna(historico_bruto)
            else re.sub(r"\s+", " ", str(historico_bruto)).strip()
        )
        debito = abs(_numero(linha.get(col_debito)))
        credito = abs(_numero(linha.get(col_credito)))
        if pd.isna(data) or not historico or not contrapartida:
            continue
        if debito > 0 and credito == 0:
            conta_debito, conta_credito, valor = conta_banco_atual, contrapartida, debito
        elif credito > 0 and debito == 0:
            conta_debito, conta_credito, valor = contrapartida, conta_banco_atual, -credito
        else:
            continue
        registros.append({
            "banco": banco_atual,
            "data": pd.Timestamp(data).normalize(),
            "historico": historico,
            "contrapartida": contrapartida,
            "debito": conta_debito,
            "credito": conta_credito,
            "valor": round(valor, 2),
        })
    return registros

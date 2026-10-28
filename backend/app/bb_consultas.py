"""BB Consultas: movimentação C/D, saldo separado e continuação entre páginas."""
from __future__ import annotations

import io
import re
from datetime import datetime
from decimal import Decimal

from pypdf import PdfReader

_MONEY = r"(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
_DATE = r"\d{2}/\d{2}/\d{4}"
_ROW = re.compile(
    rf"^(?P<data>{_DATE})\s+(?:{_DATE}\s+)?\d{{4}}\s+\d{{5}}\s+\d{{3}}\s+"
    rf"(?P<historico>.+?)\s*(?P<documento>[\d.\-/]+)\s+"
    rf"(?P<valor>{_MONEY})\s*(?P<natureza>[CD])"
    rf"(?:\s*(?P<saldo>{_MONEY})\s*(?P<saldo_natureza>[CD]))?\s*$", re.I,
)
# Algumas versões do BB Consultas deixam o documento vazio.
# Nesses casos as colunas de data, códigos, valor e natureza continuam obrigatórias.
_ROW_NO_DOCUMENT = re.compile(
    rf"^(?P<data>{_DATE})\s+(?:{_DATE}\s+)?"
    rf"\d{{1,5}}\s+\d{{1,6}}\s+\d{{1,3}}\s+"
    rf"(?P<historico>.+?)\s+(?P<valor>{_MONEY})\s*(?P<natureza>[CD])"
    rf"(?:\s*(?P<saldo>{_MONEY})\s*(?P<saldo_natureza>[CD]))?\s*$",
    re.I,
)
_START = re.compile(rf"^{_DATE}\s")
_END = re.compile(rf"(?P<valor>{_MONEY})\s*(?P<natureza>[CD])\s*$", re.I)
_TITLE = re.compile(r"Consultas\s*[-–]\s*Extrato de conta corrente", re.I)


def parece_extrato_bb_consultas(content: bytes) -> bool:
    if not content.startswith(b'%PDF'):
        return False
    try:
        first = PdfReader(io.BytesIO(content), strict=False).pages[0].extract_text() or ''
        return bool(_TITLE.search(first))
    except Exception:
        return False


def _cents(value, nature):
    cents = int(Decimal(value.replace('.', '').replace(',', '.')) * 100)
    return cents if nature.upper() == 'C' else -cents


def ler_extrato_bb_consultas(content: bytes) -> list[dict]:
    if not content.startswith(b'%PDF') or len(content) > 25 * 1024 * 1024:
        raise ValueError('Banco do Brasil: envie um PDF válido de até 25 MB.')
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if not 1 <= len(reader.pages) <= 50:
            raise ValueError('Banco do Brasil: envie o extrato completo com até 50 páginas.')
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Não foi possível abrir o PDF do Banco do Brasil.') from exc
    if not _TITLE.search(text) or not re.search(r'Dt\.\s*balancete\s*Dt\.\s*movimento', text, re.I):
        raise ValueError('Banco do Brasil: layout Consultas não reconhecido.')
    records = []
    opening = closing = running = None
    current = None
    in_table = False
    for original in text.splitlines():
        line = re.sub(r'\s+', ' ', original).strip()
        if not line:
            continue
        if line == 'Lançamentos':
            in_table = True
            continue
        if not in_table:
            continue
        if _START.match(line):
            current = None
            if re.search(r'\bSaldo Anterior\b', line, re.I):
                match = _END.search(line)
                if match is None or opening is not None or records:
                    raise ValueError('Banco do Brasil: saldo anterior ausente, repetido ou fora de ordem.')
                opening = running = _cents(match['valor'], match['natureza'])
                continue
            if re.search(r'\b999\s+S\s*A\s*L\s*D\s*O\b', line, re.I):
                match = _END.search(line)
                if match is None:
                    raise ValueError('Banco do Brasil: saldo final não reconhecido.')
                closing = _cents(match['valor'], match['natureza'])
                break
            match = _ROW.fullmatch(line) or _ROW_NO_DOCUMENT.fullmatch(line)
            if match is None:
                raise ValueError('Banco do Brasil: movimento de ' + line[:10] + ' não reconhecido. Confira o layout e a integridade deste PDF.')
            if running is None:
                raise ValueError('Banco do Brasil: saldo anterior não encontrado.')
            cents = _cents(match['valor'], match['natureza'])
            running += cents
            if match['saldo'] is not None and running != _cents(match['saldo'], match['saldo_natureza']):
                raise ValueError('Banco do Brasil: saldo da linha não confere com as movimentações lidas.')
            current = {'DESCRIÇÃO':'BANCO DO BRASIL',
                       'DATA':datetime.strptime(match['data'], '%d/%m/%Y'),
                       'VALOR':cents / 100, 'DÉBITO':'', 'CRÉDITO':'',
                       'HISTÓRICO':(f"{match['historico']} (Doc. {match['documento']})" if match.groupdict().get('documento') else match['historico'])}
            records.append(current)
        elif current is not None:
            if (_TITLE.search(line) or line.startswith(('Dt. balancete', 'Cliente -', 'Agência ',
                'Conta corrente', 'Período do extrato', 'Transação efetuada',
                'Serviço de Atendimento', 'Ouvidoria', 'Para deficientes'))
                or re.match(r'^G\d+$', line)):
                continue
            current['HISTÓRICO'] += ' ' + line
    if not records:
        raise ValueError('Banco do Brasil: nenhum lançamento localizado.')
    if opening is None or closing is None:
        raise ValueError('Banco do Brasil: saldos inicial ou final ausentes; envie todas as páginas do extrato.')
    if running != closing:
        raise ValueError('Banco do Brasil: saldo final não confere com os lançamentos lidos; confira se o extrato está completo.')
    return records

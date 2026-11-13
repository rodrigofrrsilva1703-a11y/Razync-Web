"""Caixa Histórico: image OCR, movement date, signs and running balances."""
import pytest
import razync.valean_625 as caixa

TEXT = '''Extrato Histórico da Conta
Período Unidade Nome da Unidade
01/08/2026 - 31/08/2026 7682 PLAT EMP SAO BERNARDO, SP
SALDO ANTERIOR 2.865,27 D
03/08/2026 04/08 02:16 000000000 DEBITO DE IOF 41,88 D 2.907,15 D
03/08/2026 04/08 02:16 000000000 DEB JUROS DE MORA 91,98 D 2.999,13 D
03/08/2026 04/08 02:16 000000000 COBRANCA DE JUROS 1.782,48 D 4.781,61D
10/08/2026 10/0805:34 000202607 MENSALIDADE CESTA SERVICO 75,00 D 4.856,61 D
10/08/2026 10/0812:05 000101205 PIX RECEBIDO DADOS CONTA 3.000,00 C 1.856,61 D
12.345.678/0001-90 EMPRESA DEMONSTRACAO
E0000000020260810150548226915681
11/08/2026 11/0802:46 000000000 DEBITO PRESTA SIEMP 6.892,28 D 8.748,89 D
11/08/2026 11/08 10:30 000111030 PIX RECEBIDO DADOS CONTA 6.950,00 C 1.798,89 D
12.345.678/0001-90 EMPRESA DEMONSTRACAO
E0000000020260811133015351611625
INFORMACGOES DO LIMITE ROTATIVO
JUROS PROV 381,79 D
LIMITE DISPONIBILIZADO 20.000,00 C
Consulta realizada em 01/09/2026 as 17:26:20 por OPERADOR unidade 3859 Pagina 1 de 2
Consulta realizada em 01/09/2026 as 17:26:20 por OPERADOR unidade 3859 Pagina 2 de 2'''


def test_caixa_image_historico_is_read_completely(monkeypatch):
    monkeypatch.setattr(caixa, '_texto_pdf', lambda _: '')
    monkeypatch.setattr(caixa, '_texto_ocr_caixa', lambda _: TEXT.replace('Histórico', 'Histérico'))
    result = caixa.processar_caixa_625(b'image')
    assert result['VALOR'].tolist() == [-41.88, -91.98, -1782.48, -75, 3000, -6892.28, 6950]
    assert result['DATA'].dt.strftime('%d/%m/%Y').tolist()[:3] == ['03/08/2026'] * 3
    assert round(result['VALOR'].sum(), 2) == 1066.38
    histories = ' '.join(result['HISTÓRICO'])
    assert 'EMPRESA DEMONSTRACAO' in histories
    assert not any(word in histories for word in ['12.345.678', 'E00000000', 'LIMITE', 'Consulta', '381,79'])
    assert result.iloc[0]['CRÉDITO'] == '504' and result.iloc[4]['DÉBITO'] == '504'


@pytest.mark.parametrize('old,new', [('41,88 D', '41,83 D'), ('3.000,00 C', '3.000,00 D'),
                                     ('2.907,15 D', '2.907,15 C'), ('SALDO ANTERIOR 2.865,27 D', 'SEM SALDO ANTERIOR')])
def test_ocr_errors_cannot_silently_generate_accounting_entries(old, new):
    with pytest.raises(ValueError, match='saldo'):
        caixa._processar_caixa_historico(TEXT.replace(old, new))


def test_unreadable_transaction_is_reported_instead_of_dropped():
    with pytest.raises(ValueError, match='linha de movimento'):
        caixa._processar_caixa_historico(TEXT.replace('6.950,00 C', '6.95O,00 C'))


def test_equal_movements_are_preserved_if_balances_confirm_both():
    text = '''Extrato Histórico da Conta
SALDO ANTERIOR 100,00 C
03/08/2026 03/0802:16 000000001 TARIFA 10,00 D 90,00 C
03/08/2026 03/0802:16 000000001 TARIFA 10,00 D 80,00 C'''
    assert caixa._processar_caixa_historico(text)['VALOR'].tolist() == [-10, -10]


def test_same_reader_is_used_by_global_pdf_converter(monkeypatch):
    from types import SimpleNamespace
    from app import global_tools
    monkeypatch.setattr(global_tools, 'PdfReader', lambda _: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: '')]))
    monkeypatch.setattr(caixa, '_texto_pdf', lambda _: '')
    monkeypatch.setattr(caixa, '_texto_ocr_caixa', lambda _: TEXT)
    result = global_tools.processar_arquivo(b'image', 'Caixa Economica Federal.pdf')
    assert len(result) == 7
    assert round(result.VALOR.sum(), 2) == 1066.38
    assert set(result['DÉBITO']) == {''} and set(result['CRÉDITO']) == {''}

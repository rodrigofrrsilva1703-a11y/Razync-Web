"""Layout BB Consultas com saldo na mesma linha, sem dados de clientes."""
import io
from decimal import Decimal

import fitz
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.bb_consultas import ler_extrato_bb_consultas, parece_extrato_bb_consultas
from app.main import app
from app.migration_services import statement


def pdf(*, invalid_balance=False, omit_closing=False, bad_row=False):
    pages = [[
        'Consultas - Extrato de conta corrente',
        'Conta corrente 123456-7 EMPRESA TESTE',
        'Lançamentos',
        'Dt. balancete Dt. movimento Ag. origem Lote Histórico Documento Valor R$ Saldo',
        '27/02/2026 0000 00000 000 Saldo Anterior 0,00 C',
        '03/03/2026 0000 14173 900 Resgate Depósito Judicial 89.111.111 150,00 C',
        '03/03/2026 0000 13105 144 Pix - Enviado 30.301 50,00 D',
        '03/03 10:01 FAVORECIDO A',
        '03/03/2026 0000 13105 144 Pix - Enviado 30.302 50,00 D',
    ],[
        '03/03 10:02 FAVORECIDO B',
        '03/03/2026 0000 00000 351 BB Rende Fácil 9.903 50,00 D0,00 C',
        'Rende Facil',
        '04/03/2026 0000 13113 435 Tarifa Pacote de Serviços30.401 40,00 D',
        '04/03/2026 0000 00000 798 BB Rende Fácil 9.903 40,00 C '+('1,00 C' if invalid_balance else '0,00 C'),
    ]]
    if bad_row:pages[1].append('04/03/2026 0000 13105 144 Pix - Enviado 30.402 VALOR ILEGIVEL')
    if not omit_closing:pages[1].append('31/03/2026 0000 00000 999 S A L D O 0,00 C')
    pages[1].extend(['*** A CONTA NAO FOI MOVIMENTADA ***','Transação efetuada com sucesso'])
    doc=fitz.open()
    for lines in pages:doc.new_page().insert_text((25,25),'\n'.join(lines),fontsize=8)
    content=doc.tobytes();doc.close();return content


def test_movimentos_nao_sao_trocados_pelo_saldo_e_complemento_atravessa_pagina():
    rows=ler_extrato_bb_consultas(pdf())
    assert len(rows)==6
    assert [row['VALOR'] for row in rows]==[150,-50,-50,-50,-40,40]
    assert 'FAVORECIDO B' in rows[2]['HISTÓRICO']
    assert '30.302' in rows[2]['HISTÓRICO']
    assert all('SALDO' not in row['HISTÓRICO'] and 'NAO FOI' not in row['HISTÓRICO'] for row in rows)
    assert sum(Decimal(str(row['VALOR'])) for row in rows)==0


@pytest.mark.parametrize('kwargs',[{'invalid_balance':True},{'omit_closing':True},{'bad_row':True}])
def test_extrato_incompleto_ou_divergente_nao_retorna_resultado_parcial(kwargs):
    with pytest.raises(ValueError):ler_extrato_bb_consultas(pdf(**kwargs))


@pytest.mark.parametrize('company',[1529])
def test_layout_e_reconhecido_antes_do_leitor_especifico_de_outro_formato(company):
    frame=statement(company,'banco_brasil',pdf(),'extrato.pdf')
    assert len(frame)==6
    assert frame.VALOR.tolist()==[150,-50,-50,-50,-40,40]


def test_preview_da_conferencia_recebe_todos_os_movimentos_sem_eliminar_repetidos():
    rows=ler_extrato_bb_consultas(pdf())
    stream=io.BytesIO()
    pd.DataFrame(rows).to_excel(stream,index=False,sheet_name='Banco do Brasil')
    response=TestClient(app).post('/api/v1/conferencia-extrato/1529/preview',
        data={'bank':'banco_brasil','options_json':'{}'},
        files=[('model_file',('modelo.xlsx',stream.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')),
               ('statement_files',('extrato.pdf',pdf(),'application/pdf'))])
    assert response.status_code==200,response.text
    summary=response.json()['summary']
    assert summary['extrato']==6
    assert summary['planilha']==6
    assert summary['ok'] is True

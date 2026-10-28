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


@pytest.mark.parametrize('multi',[False,True])
def test_preview_da_conferencia_recebe_todos_os_movimentos_sem_eliminar_repetidos(multi):
    rows=ler_extrato_bb_consultas(pdf())
    stream=io.BytesIO()
    pd.DataFrame(rows).to_excel(stream,index=False,sheet_name='Banco do Brasil')
    endpoint='/api/v1/conferencia-extrato/1529/'+('multi/preview' if multi else 'preview')
    data={'banks_json':'["banco_brasil"]','file_banks_json':'["banco_brasil"]','options_json':'{}'} if multi else {'bank':'banco_brasil','options_json':'{}'}
    response=TestClient(app).post(endpoint,
        data=data,
        files=[('model_file',('modelo.xlsx',stream.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')),
               ('files' if multi else 'statement_files',('extrato.pdf',pdf(),'application/pdf'))])
    assert response.status_code==200,response.text
    parsed=response.json()
    movements=parsed['statement_movements']
    assert len(movements)==6
    assert [row['VALOR'] for row in movements if 'BB Rende Fácil' in row['HISTÓRICO']]==[-50,40]
    assert all(row['BANCO'] for row in movements)
    summary=parsed['summary']['by_bank']['banco_brasil'] if multi else parsed['summary']
    assert summary['extrato']==6
    assert summary['planilha']==6
    assert summary['ok'] is True


def test_organizador_bb_usa_leitor_do_banco_e_exporta_movimentos_com_saldo_na_mesma_linha(monkeypatch):
    import razync.nibo as nibo
    from app.migration_services import workflow

    def unexpected_nibo(_):
        raise AssertionError('Extrato BB Consultas não pode passar pelo OCR Nibo')
    monkeypatch.setattr(nibo, 'processar_extrato_nibo_pdf', unexpected_nibo)
    content, _ = workflow(1529, {'banco_brasil': [('extrato.pdf', pdf())]}, {})
    from app.migration_routes import workbook_preview
    sheets = workbook_preview(content)
    assert sum(sheet['count'] for sheet in sheets) == 6
    records = [dict(zip(sheet['columns'], row)) for sheet in sheets for row in sheet['rows']]
    rende = [row for row in records if 'BB Rende Fácil' in row['HISTÓRICO']]
    assert [row['VALOR'] for row in rende] == [-50, 40]
    assert all(not row['DÉBITO'] and not row['CRÉDITO'] for row in records)


def test_organizador_bb_invalido_nao_cai_no_ocr_nibo(monkeypatch):
    import razync.nibo as nibo
    from app.migration_services import workflow
    monkeypatch.setattr(nibo, 'processar_extrato_nibo_pdf', lambda _: pytest.fail('Não deve ignorar erro de saldo'))
    with pytest.raises(ValueError):
        workflow(1529, {'banco_brasil': [('extrato.pdf', pdf(invalid_balance=True))]}, {})


@pytest.mark.parametrize('bank', ['itau', 'banco_brasil'])
def test_organizador_preserva_pdf_nibo_no_banco_correspondente(monkeypatch, bank):
    import razync.nibo as nibo
    from app.migration_services import workflow
    from app.migration_routes import workbook_preview
    doc = fitz.open()
    doc.new_page().insert_text((25,25),'Contas e Extratos Nibo')
    content = doc.tobytes()
    doc.close()
    calls = []
    def original_nibo(data):
        calls.append(data)
        return pd.DataFrame([{'DESCRIÇÃO':'NIBO','DATA':pd.Timestamp('2026-03-03'),'VALOR':123.45,'DÉBITO':'','CRÉDITO':'','HISTÓRICO':'MOVIMENTO NIBO'}])
    monkeypatch.setattr(nibo, 'processar_extrato_nibo_pdf', original_nibo)
    result, _ = workflow(1529, {bank: [('nibo.pdf', content)]}, {})
    assert calls == [content]
    sheets = workbook_preview(result)
    assert sum(sheet['count'] for sheet in sheets) == 1
    assert sum(sheet['entradas'] for sheet in sheets) == 123.45


def test_api_organizador_exporta_bb_consultas_e_aplica_filtro_de_periodo():
    response = TestClient(app).post('/api/v1/workflow/1529/preview',
        data={'roles_json':'["banco_brasil"]', 'options_json':'{"data_inicial":"2026-03-04","data_final":"2026-03-04"}'},
        files=[('files', ('extrato.pdf', pdf(), 'application/pdf'))])
    assert response.status_code == 200, response.text
    sheets = response.json()['sheets']
    assert sum(sheet['count'] for sheet in sheets) == 2
    records = [dict(zip(sheet['columns'], row)) for sheet in sheets for row in sheet['rows']]
    assert all(row['DATA'] == '04/03/2026' for row in records)
    assert [row['VALOR'] for row in records] == [-40, 40]


def test_1529_abas_por_banco_reunem_varios_arquivos_e_filtram_periodo(monkeypatch):
    import razync.nibo as nibo
    from app.migration_services import workflow
    from app.migration_routes import workbook_preview
    def nibo_frame(data):
        return pd.DataFrame([{'DESCRIÇÃO':'NIBO','DATA':pd.Timestamp(date),'VALOR':value,'DÉBITO':'','CRÉDITO':'','HISTÓRICO':'Recebido: NIBO TESTE'}
            for date,value in ({b'itau-a':[('2026-03-04',20),('2026-02-01',10)], b'itau-b':[('2026-03-03',30)]}[data])])
    monkeypatch.setattr(nibo,'processar_extrato_nibo_pdf',nibo_frame)
    content,_=workflow(1529,{'itau':[('a.pdf',b'itau-a'),('b.pdf',b'itau-b')],
        'banco_brasil':[('bb.pdf',pdf())]}, {'data_inicial':'2026-03-01','data_final':'2026-03-31'})
    sheets=workbook_preview(content)
    assert [sheet['name'] for sheet in sheets]==['Itaú','Banco do Brasil']
    itau,bb=sheets
    assert itau['count']==2 and bb['count']==6
    itau_rows=[dict(zip(itau['columns'],row)) for row in itau['rows']]
    bb_rows=[dict(zip(bb['columns'],row)) for row in bb['rows']]
    assert [row['VALOR'] for row in itau_rows]==[30,20]
    assert [row['DATA'] for row in itau_rows]==['03/03/2026','04/03/2026']
    assert all(row['DESCRIÇÃO']=='BANCO ITAÚ' for row in itau_rows)
    assert all(row['DESCRIÇÃO']=='BANCO DO BRASIL' for row in bb_rows)
    assert [row['VALOR'] for row in bb_rows if 'BB Rende Fácil' in row['HISTÓRICO']]==[-50,40]


def test_bb_consultas_aceita_lancamento_sem_documento_e_conciliacao_fecha():
    """Documento é opcional no PDF; data, códigos, valor e saldo continuam obrigatórios."""
    doc = fitz.open()
    pg = doc.new_page(width=1040, height=450)
    rows = [
        "Consultas - Extrato de conta corrente",
        "Cliente - Conta atual",
        "Lançamentos",
        "Dt. balancete Dt. movimento Ag. origem Lote Histórico Documento Valor R$ Saldo",
        "30/09/2026 0000 00000 000 Saldo Anterior 500,00 C",
        "02/10/2026 0000 13105 144 Pix - Recebido sem documento 1.000,00 C",
        "02/10/2026 0000 13105 144 Pix - Enviado 123.456 400,00 D",
        "03/10/2026 0000 13113 435 Tarifa avulsa 10,00 D 1.090,00 C",
        "31/10/2026 0000 00000 999 S A L D O 1.090,00 C",
    ]
    for i, row in enumerate(rows):
        pg.insert_text((24, 30 + i * 22), row, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    result = ler_extrato_bb_consultas(pdf_bytes)
    assert len(result) == 3
    assert [x["VALOR"] for x in result] == [1000.0, -400.0, -10.0]
    assert "sem documento" in result[0]["HISTÓRICO"]
    assert "(Doc." not in result[0]["HISTÓRICO"]
    assert "(Doc. 123.456)" in result[1]["HISTÓRICO"]
    assert result[2]["HISTÓRICO"] == "Tarifa avulsa"


def test_bb_consultas_nao_inventa_valores_quando_linha_nao_tem_cd():
    doc = fitz.open()
    pg = doc.new_page(width=1000, height=350)
    rows = [
        "Consultas - Extrato de conta corrente",
        "Lançamentos",
        "Dt. balancete Dt. movimento Ag. origem Lote Histórico Documento Valor R$ Saldo",
        "01/09/2026 0000 00000 000 Saldo Anterior 0,00 C",
        "01/09/2026 0000 13105 144 Pix - Recebido 1.000,00",
        "30/09/2026 0000 00000 999 S A L D O 1.000,00 C",
    ]
    for i, row in enumerate(rows):
        pg.insert_text((24, 30 + i * 22), row, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    with pytest.raises(ValueError, match="não reconhecido"):
        ler_extrato_bb_consultas(pdf_bytes)

"""Regressões Itaú mensal CLJM 933 sem guardar documentos de clientes no Git."""
from unittest.mock import patch

import fitz
import pandas as pd
import pytest

from app import company_933 as module
from app import migration_services as services


def create_statement(*, wrong_total=False):
    pdf=fitz.open()
    pages=[pdf.new_page(width=595,height=842),pdf.new_page(width=595,height=842)]
    for i,page in enumerate(pages,1):
        page.insert_text((28,42),f"extrato mensal ag 6255 cc 19059-4 ago 2026 {i:03}|002",fontsize=8)
        if i==1:
            page.insert_text((28,65),"CLJM CONSULTORIA E PARTICIPACO",fontsize=9)
            page.insert_text((330,100),"entradas (créditos)",fontsize=9)
            page.insert_text((330,118),"total 107.102,39",fontsize=9)
            page.insert_text((330,139),"saídas (débitos)",fontsize=9)
            page.insert_text((330,158),f"total {'106.470,37' if wrong_total else '106.470,38'}",fontsize=9)
            page.insert_text((36,206),"Conta Corrente | Movimentação",fontsize=9)
        page.insert_text((150,230 if i==1 else 84),"data",fontsize=9)
        page.insert_text((208,230 if i==1 else 84),"descrição",fontsize=9)

    def row(page,y,day,desc,credit=None,debit=None,balance=None):
        if day:page.insert_text((150,y),day,fontsize=9)
        page.insert_text((208,y),desc,fontsize=9)
        if credit is not None:page.insert_text((364,y),credit,fontsize=9)
        if debit is not None:page.insert_text((430,y),debit,fontsize=9)
        if balance is not None:page.insert_text((520,y),balance,fontsize=9)

    p=pages[0]
    row(p,250,"23/07","Saldo anterior",balance="290,38")
    row(p,270,"03/08","SALDO APLIC AUT MAIS",balance="289,38")
    row(p,290,"04/08","Tar Plano Adapt 1 07/26",debit="169,00-")
    row(p,305,None,"Res Aplic Aut Mais",credit="168,98")
    row(p,320,None,"Rend Pago Aplic Aut Mais",credit="0,02")
    row(p,340,"05/08","BOLETO PAGO JAGUAR SERVI",debit="810,50-")
    row(p,355,None,"Resgate CDB",credit="3.000,16")
    row(p,370,None,"Apl Aplic Aut Mais",debit="2.189,66-")
    row(p,390,"07/08","BOLETO PAGO CONDOMINIO E",debit="1.910,68-")
    row(p,405,None,"PIX TRANSF PJBANK 07/08",credit="4.102,07")

    p=pages[1]
    row(p,104,None,"Apl Aplic Aut Mais",debit="2.191,39-")
    row(p,126,None,"SALDO APLIC AUT MAIS",balance="4.501,45")
    row(p,150,"18/08","BOLETO PAGO SUL AMERICA",debit="8.415,95-")
    row(p,164,None,"Aplicação CDB DI",debit="95.000,00-")
    row(p,178,None,"TBI 4054.02021-1A C",credit="100.000,00")
    row(p,192,None,"Res Aplic Aut Mais",credit="3.415,82")
    row(p,206,None,"Rend Pago Aplic Aut Mais",credit="0,13")
    row(p,228,"24/08","Sispag PIX QR-CODE",debit="164,25-")
    row(p,242,None,"Res Aplic Aut Mais",credit="164,24")
    row(p,256,None,"Rend Pago Aplic Aut Mais",credit="0,01")
    row(p,278,None,"Saldo em C/C",balance="1,00")
    row(p,292,None,"Saldo final",balance="922,39")
    page_bytes=pdf.tobytes()
    pdf.close()
    return page_bytes


def test_933_reads_all_17_movements_with_page_continuation():
    frame=module.read_statement(create_statement())
    assert len(frame)==17
    assert frame["VALOR"].sum()==pytest.approx(0)
    assert frame.loc[8,"VALOR"]==-2191.39
    assert frame.loc[8,"DATA"]==pd.Timestamp("2026-08-07")
    assert frame["DÉBITO"].replace("",pd.NA).dropna().eq("508").all()
    assert frame["CRÉDITO"].replace("",pd.NA).dropna().eq("508").all()
    assert frame["DATA"].dt.month.eq(8).all()
    assert not frame["HISTÓRICO"].str.contains("SALDO APLIC|Saldo final").any()


def test_933_must_reject_wrong_bank_totals():
    with pytest.raises(ValueError,match="resumo divergente"):
        module.read_statement(create_statement(wrong_total=True))


def test_933_rejects_other_bank_account():
    data=create_statement()
    with fitz.open(stream=data,filetype="pdf") as source:
        doc=fitz.open()
        for page in source:
            target=doc.new_page(width=page.rect.width,height=page.rect.height)
            target.show_pdf_page(target.rect,source,page.number)
        # Replace the header by a tiny overlay with another account for one test.
        p=doc[0]
        p.draw_rect(fitz.Rect(25,28,400,45),fill=(1,1,1),color=(1,1,1))
        p.insert_text((28,42),"extrato mensal ag 6255 cc 19059-5 ago 2026 001|002",fontsize=8)
        changed=doc.tobytes()
        doc.close()
    with pytest.raises(ValueError,match="agência 6255"):
        module.read_statement(changed)


def test_933_routes_to_statement_and_workflow():
    frame=module.read_statement(create_statement())
    with patch.object(module,"read_statement",return_value=frame) as parser:
        result=services.statement(933,"itau",b"%PDF example","ago.pdf")
        parser.assert_called_once()
    assert len(result)==17
    with patch.object(module,"read_statement",return_value=frame),\
         patch("app.excel.gerar_modelo_abas",return_value=b"file") as writer:
        workbook,name=module.workflow_933({"extrato":[("ago.pdf",b"%PDF example")]},{})
        assert workbook==b"file"
        assert writer.call_args.args[0]["Itaú"].shape[0]==17
        assert "933" in name
    with patch.object(module,"workflow_933",return_value=(b"file","933.xlsx")) as workflow:
        assert services._workflow(933,{}, {})==(b"file","933.xlsx")
        workflow.assert_called_once()


def test_933_preserves_duplicates_and_rejects_duplicate_period():
    with patch.object(module,"read_statement",return_value=module.read_statement(create_statement())):
        with pytest.raises(ValueError,match="competência repetida"):
            module.workflow_933({"extrato":[("a.pdf",b"%PDF"),("b.pdf",b"%PDF")]},{})

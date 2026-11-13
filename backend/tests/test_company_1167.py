"""Empresa 1167: regressões sintéticas sem dados bancários de clientes."""
from unittest.mock import patch
import fitz
import pandas as pd
import pytest

from app import company_1167 as company
from app import migration_services as services


def pdf(*page_data):
    doc=fitz.open()
    for lines in page_data:
        doc.new_page(width=624,height=964)
        page=doc[-1]
        for x,y,label in lines:
            page.insert_text((x,y),label,fontsize=9,fontname="helv")
    content=doc.tobytes()
    doc.close()
    return content


def rows(bank,account):
    return pd.DataFrame([{
        "DESCRIÇÃO":bank,"DATA":pd.Timestamp("2026-07-03"),
        "VALOR":v,"DÉBITO":account if v>0 else "",
        "CRÉDITO":account if v<0 else "",
        "HISTÓRICO":("Recebido: " if v>0 else "Pago: ")+name,
    } for v,name in [(-25.0,"Despesa"),(25.0,"Estorno")]])


def test_four_bank_workflow_separates_accounts_and_preserves_reversals():
    accounts={"banco_brasil":"8","sicoob":"506","itau":"508","bradesco":"507"}
    from unittest.mock import patch
    fake={key:(lambda content,account=account,key=key: rows(key,account))
          for key,account in accounts.items()}
    roles={key:[("julho.pdf",b"%PDF fake")] for key in accounts}
    with patch.dict(company.READERS,fake), \
         patch("app.excel.gerar_modelo_abas",return_value=b"workbook") as exporter:
        result,filename=company.workflow_1167(roles,{})
    assert result==b"workbook" and "1167" in filename
    sheets=exporter.call_args.args[0]
    assert list(sheets)==["Banco do Brasil","Sicoob","Itaú","Bradesco"]
    for key,label in (("banco_brasil","Banco do Brasil"),
                      ("sicoob","Sicoob"),("itau","Itaú"),("bradesco","Bradesco")):
        df=sheets[label]
        assert df["VALOR"].tolist()==[-25.0,25.0]
        assert df["CRÉDITO"].tolist()==[accounts[key],""]
        assert df["DÉBITO"].tolist()==["",accounts[key]]


def test_bank_specific_statement_route_and_reject_unknown():
    for key,account in (("banco_brasil","8"),("sicoob","506"),
                        ("itau","508"),("bradesco","507")):
        with patch.dict(company.READERS,{key:lambda content,account=account: rows("BANCO",account)}):
            result=services.statement(1167,key,b"%PDF dummy","julho.pdf")
            assert result["VALOR"].tolist()==[-25.0,25.0]
    with pytest.raises(ValueError,match="banco não cadastrado"):
        services.statement(1167,"santander",b"%PDF dummy","julho.pdf")
    with patch.object(company,"workflow_1167",return_value=(b"ok","1167.xlsx")) as workflow:
        assert services._workflow(1167,{}, {})==(b"ok","1167.xlsx")
        workflow.assert_called_once()


def test_bradesco_507_preserves_date_across_page_break_and_ignores_august():
    first=[
        (40,181,"Extrato de:"),(86,181,"Ag:"),(102,181,"538"),
        (118,181,"|"),(123,181,"CC:"),(140,181,"0301794-0"),
        (182,181,"|"),(187,181,"Entre"),(210,181,"01/07/2026"),
        (254,181,"e"),(261,181,"31/07/2026"),
        (30,105,"IMPERIO GONG"),
        (41,232,"30/06/2026"),(101,232,"SALDO"),(151,232,"ANTERIOR"),
        (539,232,"100,00"),
        (41,247,"31/07/2026"),(101,242,"PIX"),(123,242,"ENVIADO"),
        (266,247,"1234567"),(450,247,"-10,00"),(539,247,"90,00"),
        (101,922,"TARIFA"),(137,922,"BANCARIA"),
    ]
    second=[
        (101,134,"TRANSF"),(140,134,"PGTO"),(165,134,"PIX"),
        (266,134,"1234568"),(450,134,"-1,65"),(539,134,"88,35"),
        (41,225,"Total"),(101,225,"88,35"),
        (41,285,"Últimos"),(101,285,"Lançamentos"),
        (41,320,"11/08/2026"),(101,320,"PIX"),(266,320,"1234569"),
        (355,320,"400,00"),(539,320,"488,35"),
    ]
    with patch.object(company,"_open",return_value=fitz.open(stream=pdf(first,second),filetype="pdf")):
        df=company.read_bradesco(b"%PDF sample")
    assert df["VALOR"].tolist()==[-10.0,-1.65]
    assert df["CRÉDITO"].tolist()==["507","507"]
    assert df["DATA"].dt.strftime("%d/%m/%Y").tolist()==["31/07/2026"]*2
    assert "TARIFA BANCARIA" in df.iloc[1]["HISTÓRICO"]


def test_bradesco_507_rejects_wrong_bank_account():
    wrong=[
        (40,181,"Extrato de:"),(86,181,"Ag:"),(102,181,"538"),
        (118,181,"|"),(123,181,"CC:"),(140,181,"0301794-1"),
        (182,181,"|"),(187,181,"Entre"),(210,181,"01/07/2026"),
        (254,181,"e"),(261,181,"31/07/2026"),
    ]
    with pytest.raises(ValueError,match="agência 538"):
        company.read_bradesco(pdf(wrong))


def test_other_bank_accounts_must_be_validated():
    with pytest.raises(ValueError,match="agência 8224-4"):
        company.read_banco_brasil(pdf([(55,125,"Agência 8224-4"),
                                       (55,137,"Conta corrente 363-9")]))
    with pytest.raises(ValueError,match="cooperativa 4340"):
        company.read_sicoob(pdf([(60,100,"4340-0 / SICOOB"),
                                 (60,120,"210.033-8 / IMPERIO GONG")]))
    with pytest.raises(ValueError,match="agência 7111"):
        company.read_itau(pdf([(100,85,"IMPERIO GONG COM VAREJISTA"),
                               (435,85,"Agência 7111 Conta 0099857-5")]))


def test_input_validation_rejects_non_pdf():
    for reader in company.READERS.values():
        with pytest.raises(ValueError,match="PDF"):
            reader(b"not a pdf")


def test_duplicate_month_rejected_per_bank():
    with patch.dict(company.READERS,{"itau":lambda data: rows("ITAÚ","508")}):
        with pytest.raises(ValueError,match="período repetido"):
            company.workflow_1167({"itau":[("a.pdf",b"%PDF"),("b.pdf",b"%PDF")]},{})

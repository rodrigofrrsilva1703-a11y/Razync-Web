"""Regressões do OCR Santander da Leravi sem armazenar documentos bancários."""
from datetime import date
import pytest
from app import company_113_santander as santander
from app import company_113

def word(text,x,y,confidence=90):
    return {"text":text,"x":x,"y":y,"confidence":confidence}

def summary():
    fields=[
        ("Resumo",40,30),("-",98,30),("setembro/2026",110,30),
        ("LERAVI",40,50),("INDUSTRIAL",80,50),("LTDA",145,50),
        ("1565",40,70),("13.000018-2",85,70),
        ("TOTAL",40,90),("DE",68,90),("CREDITOS",81,90),("281.607",150,90),("67",220,90),
        ("TOTAL",40,110),("DE",68,110),("DEBITOS",81,110),("281.607",150,110),("(-)",205,110),("67",220,110)
    ]
    return [word(a,x,y) for a,x,y in fields]

def test_resumo_mes_conta_e_valores_reais():
    assert santander._period_and_totals(summary())==(2026,9,28160767,28160767)
    wrong=[dict(w) for w in summary()]
    for w in wrong:
        if w["text"]=="13.000018-2":w["text"]="13.000019-2"
    with pytest.raises(ValueError,match="agência|conta"):
        santander._period_and_totals(wrong)

@pytest.mark.parametrize("raw,expected", [
    ("4,535,82-",453582),
    ("61.145,30-",6114530),
    ("7,27-",727),
    ("281.607,67",28160767),
])
def test_ocr_moeda_sem_arredondar(raw,expected):
    assert santander._cents(raw)==expected

def test_movimentos_e_saldos_separados_por_colunas():
    words=[
        word("01/09",34,680),
        word("TARIFA",66,680),word("AVULSA",100,680),word("7,27-",438,680),
        word("RESGATE",66,695),word("CONTAMAX",105,695),
        word("7,27",389,695),word("0,00",526,695),
    ]
    records=santander._parse_transactions([(words,words)],2026,9)
    assert records==[
        (date(2026,9,1),-727,"TARIFA AVULSA"),
        (date(2026,9,1),727,"RESGATE CONTAMAX"),
    ]

def test_empresa_113_usa_novo_leitor_sem_importar_pdf_ilegiveI():
    assert company_113.READERS["santander"] is company_113.read_santander
    with pytest.raises(ValueError,match="PDF"):
        company_113.read_santander(b"not pdf")

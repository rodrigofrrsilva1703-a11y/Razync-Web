"""Regressão: sem duplicação de nomes ao montar históricos bancários."""
from io import BytesIO

import pandas as pd

from app.history_names import join_history_description
from app.company_1058 import read_itau


def test_full_name_already_in_history():
    assert join_history_description(
        "PIX ENVIADO ACME COMERCIO LTDA", "ACME COMERCIO LTDA"
    ) == "PIX ENVIADO ACME COMERCIO LTDA"


def test_partial_company_name_is_not_repeated():
    assert join_history_description(
        "SISPAG TRANSF CC ITAU - FERNANDES", "FERNANDES SERVICOS LTDA"
    ) == "SISPAG TRANSF CC ITAU - FERNANDES"


def test_accent_and_punctuation_normalization():
    assert join_history_description(
        "TRANSFERÊNCIA JOSÉ SILVA", "JOSE SILVA LTDA"
    ) == "TRANSFERÊNCIA JOSÉ SILVA"


def test_new_name_still_appended_if_not_identified():
    assert join_history_description(
        "SISPAG TRANSF CC ITAU", "FERNANDES SERVICOS LTDA"
    ) == "SISPAG TRANSF CC ITAU - FERNANDES SERVICOS LTDA"


def test_common_words_do_not_infer_identity():
    assert join_history_description(
        "PIX ENVIADO EMPRESA COMERCIAL", "EMPRESA COMERCIAL ALVORADA LTDA"
    ) == "PIX ENVIADO EMPRESA COMERCIAL - EMPRESA COMERCIAL ALVORADA LTDA"


def test_empty_merchant_and_original_history_preserved():
    assert join_history_description("RENDIMENTOS REND PAGO APLIC AUT MAIS", "") == (
        "RENDIMENTOS REND PAGO APLIC AUT MAIS"
    )


def test_1058_auxiliary_does_not_repeat_partially_identified_company():
    data = [[None]*6 for _ in range(3)] + [
        [None,"DATA","TIPO","FAVORECIDO","VALOR","DESCRIÇÃO"],
        [None,pd.Timestamp("2026-08-03"),"Boletos de cobrança",
         "FERNANDES SERVICOS LTDA",123.45,"PAGAMENTO FERNANDES"],
        [None,pd.Timestamp("2026-08-04"),"Boletos de cobrança",
         "ALVORADA SERVICOS LTDA",90.00,"PAGAMENTO DE BOLETO"],
    ]
    excel=BytesIO()
    pd.DataFrame(data).to_excel(excel,index=False,header=False)
    result=read_itau(excel.getvalue())
    assert result["HISTÓRICO"].tolist() == [
        "Pago: PAGAMENTO FERNANDES",
        "Pago: PAGAMENTO DE BOLETO - ALVORADA SERVICOS LTDA",
    ]

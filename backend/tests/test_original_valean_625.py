from pathlib import Path

import pandas as pd

from razync.valean_625 import CONTAS_VALEAN_625, processar_extrato_625


ARQUIVOS = {
    "banco_brasil": "3-Banco do Brasil -vs.pdf",
    "caixa": "5- caixa economica federal-vs.pdf",
    "sicredi": "1-Sicredi  -vs.pdf",
}


def test_contas_da_empresa_625():
    assert CONTAS_VALEAN_625 == {
        "banco_brasil": "8", "caixa": "504", "sicredi": "3999"
    }


def test_registro_modelo_define_conta_conforme_sinal(monkeypatch):
    import razync.valean_625 as valean

    monkeypatch.setattr(valean, "_texto_pdf", lambda _: (
        "02/03/2026 AMORTIZACAO CONTRATO C43430907 -1.486,28 -34.000,00\n"
        "03/03/2026 RECEBIMENTO PIX PIX_CRED 15.000,00 -19.000,00"
    ))
    df = processar_extrato_625(b"pdf", "sicredi")
    assert list(df["VALOR"]) == [-1486.28, 15000.0]
    assert list(df["DÉBITO"]) == ["", "3999"]
    assert list(df["CRÉDITO"]) == ["3999", ""]
    assert df.iloc[0]["HISTÓRICO"].startswith("Pago: ")
    assert df.iloc[1]["HISTÓRICO"].startswith("Recebido: ")


def test_datas_sao_validas_no_modelo(monkeypatch):
    import razync.valean_625 as valean

    monkeypatch.setattr(valean, "_texto_pdf", lambda _: (
        "10/04/2027 PIX RECEBIDO PIX_CRED 1.000,00 1.000,00"
    ))
    df = processar_extrato_625(b"pdf", "sicredi")
    assert pd.Timestamp(df.iloc[0]["DATA"]) == pd.Timestamp("2027-04-10")



def test_sicredi_ocr_confere_sinal_pelo_saldo_e_rejeita_leitura_inconsistente(monkeypatch):
    import pytest
    from razync import valean_625 as sicredi

    texto = (
        "Sicredi\nAssociado: Empresa Teste\nCooperativa: 0000\n"
        "Dados referentes ao periodo 01/02/2026 a 28/02/2026.\n"
        "SALDO 5.000,00\n"
        "02/02/2026 PAGAMENTO PIX    PIX_DEB    1,200,00  3.800,00\n"
        "03/02/2026 TED RECEBIDA    001234    200,00  4.000,00\n"
    )
    monkeypatch.setattr(sicredi, "_texto_pdf", lambda _: "")
    monkeypatch.setattr(sicredi, "_texto_ocr_sicredi", lambda _, *, dpi: texto)
    resultado = sicredi.processar_sicredi_625(b"pdf", titular="Empresa Teste")
    assert resultado["VALOR"].tolist() == [-1200, 200]
    resolucoes = []

    def ler_em_resolucoes(_, *, dpi):
        resolucoes.append(dpi)
        return texto.replace("3.800,00", "3.700,00") if dpi == 400 else texto

    monkeypatch.setattr(sicredi, "_texto_ocr_sicredi", ler_em_resolucoes)
    assert sicredi.processar_sicredi_625(b"pdf")["VALOR"].tolist() == [-1200, 200]
    assert resolucoes == [400, 350]

    with pytest.raises(ValueError, match="titular"):
        sicredi.processar_sicredi_625(b"pdf", titular="Outra Empresa")
    monkeypatch.setattr(sicredi, "_texto_ocr_sicredi", lambda _, *, dpi: texto.replace("3.800,00", "3.700,00"))
    with pytest.raises(ValueError, match="não fecha"):
        sicredi.processar_sicredi_625(b"pdf")


def test_sicredi_sem_texto_compartilhado_entre_fluxos(monkeypatch):
    from io import BytesIO
    from pypdf import PdfWriter
    from app.global_tools import processar_arquivo
    from app.migration_services import statement
    from razync import valean_625 as sicredi

    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(output)
    pdf = output.getvalue()
    texto = (
        "Sicredi\nAssociado: Empresa Teste\nCooperativa: 0000\n"
        "Dados referentes ao periodo 01/02/2026 a 28/02/2026.\n"
        "SALDO 5.000,00\n"
        "02/02/2026 PAGAMENTO PIX    PIX_DEB    1.200,00  3.800,00\n"
    )
    monkeypatch.setattr(sicredi, "_texto_ocr_sicredi", lambda _, *, dpi: texto)
    global_frame = processar_arquivo(pdf, "extrato.pdf")
    assert global_frame["VALOR"].tolist() == [-1200]
    assert global_frame["CRÉDITO"].tolist() == [""]
    for empresa, conta in [(625, "3999"), (626, "1155"), (912, "515")]:
        frame = statement(empresa, "sicredi", pdf, "extrato.pdf")
        assert frame["CRÉDITO"].astype(str).tolist() == [conta]
    assert statement(626, "sicredi", pdf, "extrato.pdf").attrs["saldo_extrato"] == 3800

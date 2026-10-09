import pandas as pd

from razync import conferencia_fiscal
from razync.conferencia_fiscal import conferir_fiscal_contabil


def test_pagamento_extra_nao_impede_conferencia_fiscal():
    acumuladores = pd.DataFrame([{
        "CONTA": "2221", "TIPO": "ENTRADAS", "ACUMULADOR": "3000",
        "DESCRIÇÃO": "Consultoria", "VALOR_FISCAL": 1294.0,
    }])
    razao = pd.DataFrame([
        {"CONTA": "2221", "DATA": pd.Timestamp("2026-07-28"), "LOTE": "1", "HISTÓRICO": "SERVIÇOS DE TERCEIROS CF NF 1300", "CONTRAPARTIDA": "2693", "DÉBITO": 1294.0, "CRÉDITO": 0.0},
        {"CONTA": "2221", "DATA": pd.Timestamp("2026-07-31"), "LOTE": "2", "HISTÓRICO": "Pago: fornecedor NF 1300", "CONTRAPARTIDA": "508", "DÉBITO": 1294.0, "CRÉDITO": 0.0},
    ])
    resumo, detalhes = conferir_fiscal_contabil(acumuladores, razao)
    assert resumo.iloc[0]["SITUAÇÃO"] == "CONFERE COM ALERTAS"
    assert resumo.iloc[0]["CONTÁBIL COMPATÍVEL"] == 1294.0
    assert resumo.iloc[0]["TOTAL DA CONTA"] == 2588.0
    assert (detalhes["CLASSIFICAÇÃO"] == "ALERTA - NÃO FISCAL").sum() == 1


def test_relatorio_individual_nao_confunde_empresa_com_filial(monkeypatch):
    acumuladores = pd.DataFrame([{
        "CONTA": "2221", "TIPO": "ENTRADAS", "ACUMULADOR": "3000",
        "DESCRIÇÃO": "Serviços", "VALOR_FISCAL": 100.0,
    }])
    razao = pd.DataFrame([{
        "CONTA": "2221", "FILIAL": "1", "DATA": pd.Timestamp("2026-03-31"),
        "LOTE": "1", "HISTÓRICO": "SERVIÇOS CF NF 1",
        "CONTRAPARTIDA": "1", "DÉBITO": 100.0, "CRÉDITO": 0.0,
    }])
    leituras = iter([
        (acumuladores, {"inicio": pd.Timestamp("2026-03-01"), "fim": pd.Timestamp("2026-03-31")}),
        (razao, {"inicio": pd.Timestamp("2026-03-01"), "fim": pd.Timestamp("2026-03-31")}),
    ])
    monkeypatch.setattr(conferencia_fiscal, "ler_acumuladores", lambda *_: next(leituras))
    monkeypatch.setattr(conferencia_fiscal, "ler_razao", lambda *_: next(leituras))

    resultado = conferencia_fiscal.processar_conferencia(
        b"acumuladores", "acumuladores.xlsx", b"razao", "razao.xlsx",
        filial_alvo="1532",
    )

    assert resultado["filial_aplicada"] == "1"
    assert resultado["resumo"].iloc[0]["SITUAÇÃO"] == "CONFERE"


def test_razao_xls_dominio_com_datas_e_codigos_numericos(monkeypatch):
    """Layout real do Domínio: conta/filial como números e data em serial Excel."""
    import pandas as pd

    colunas = 14
    def linha(celulas):
        valores = [None] * colunas
        for pos, value in celulas.items():
            valores[pos] = value
        return valores

    linhas = [
        linha({0: "Empresa:", 2: "EMPRESA DE TESTE"}),
        linha({0: "Período:", 2: "01/08/2026 - 30/09/2026"}),
        linha({0: "Data", 1: "Lote", 2: "Histórico", 6: "Cta.C.Part.",
               7: "Filial", 8: "Débito", 9: "Crédito"}),
        linha({0: "Conta:", 1: 22643.0, 2: "1.1.4.01.001",
               5: "ESTOQUE DE TESTE"}),
        linha({0: 46237.0, 1: 281697789.0, 2: "COMPRA DE MERCADORIA CF NF",
               6: 22644.0, 7: 1408.0, 8: 123.45}),
        linha({0: 46237.0, 1: 281713311.0, 2: "COMPRA DE MERCADORIA CF NF",
               6: 22644.0, 7: 242.0, 8: 123.45}),
    ]
    monkeypatch.setattr(conferencia_fiscal, "_excel",
                        lambda conteudo, nome: type("Xls", (), {"sheet_names": ["Razão"]})())
    monkeypatch.setattr(conferencia_fiscal.pd, "read_excel",
                        lambda *args, **kwargs: pd.DataFrame(linhas))
    movimentos, _ = conferencia_fiscal.ler_razao(b"ole-biff", "Razão.xls")

    assert movimentos["CONTA"].tolist() == ["22643", "22643"]
    assert movimentos["FILIAL"].tolist() == ["1408", "242"]
    assert movimentos["DATA"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-08-03", "2026-08-03"
    ]

    acumuladores = pd.DataFrame([{
        "CONTA": "22643", "TIPO": "ENTRADAS", "ACUMULADOR": "1152",
        "DESCRIÇÃO": "Mercadorias", "VALOR_FISCAL": 123.45,
    }])
    monkeypatch.setattr(conferencia_fiscal, "ler_acumuladores",
                        lambda *_: (acumuladores, {}))
    monkeypatch.setattr(conferencia_fiscal, "ler_razao",
                        lambda *_: (movimentos, {}))
    resultado = conferencia_fiscal.processar_conferencia(
        b"acumuladores", "acumuladores.xls", b"razao", "Razão.xls", filial_alvo="242"
    )
    assert resultado["filial_aplicada"] == "242"
    assert resultado["resumo"].iloc[0]["SITUAÇÃO"] == "CONFERE"
    assert resultado["resumo"].iloc[0]["TOTAL DA CONTA"] == 123.45


def test_codigos_xls_preservam_numero_sem_decimal():
    assert conferencia_fiscal._codigo_dominio(22643.0) == "22643"
    assert conferencia_fiscal._codigo_dominio("22643.0") == "22643"
    assert conferencia_fiscal._codigo_dominio(242.0) == "242"
    assert conferencia_fiscal._codigo_dominio(1408.0) == "1408"
    assert conferencia_fiscal._codigo_dominio(None) == ""

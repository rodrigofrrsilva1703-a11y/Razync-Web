import pandas as pd

from razync import dominio_ledger


def test_razao_dominio_mapeia_contrapartida_pelo_lado_do_banco(monkeypatch):
    bruto = pd.DataFrame([
        ["Data", "Lote", "Histórico", None, "Cta.C.Part.", "Débito", "Crédito"],
        ["Conta:", "8", "1.1.1.02.001", None, None, None, None],
        [pd.Timestamp("2025-01-02"), "1", "Recebimento cliente", None, "1161", 500, None],
        [pd.Timestamp("2025-01-03"), "2", "Pagamento fornecedor", None, "364", None, 200],
        [pd.Timestamp("2025-01-04"), "3", "Sem contrapartida", None, None, None, 10],
        ["Conta:", "999", "Outra conta", None, None, None, None],
        [pd.Timestamp("2025-01-05"), "4", "Fora do banco", None, "100", 50, None],
    ])
    monkeypatch.setattr(dominio_ledger, "_ler_bruto", lambda *_: bruto)

    itens = dominio_ledger.ler_razao_dominio_base(
        b"xls", "Razão.xls", {"banco_brasil": "8", "sicredi": "1155"}
    )

    assert len(itens) == 2
    assert itens[0]["debito"] == "8"
    assert itens[0]["credito"] == "1161"
    assert itens[0]["valor"] == 500
    assert itens[1]["debito"] == "364"
    assert itens[1]["credito"] == "8"
    assert itens[1]["valor"] == -200


def test_razao_com_contrapartida_e_historico_na_mesma_celula(monkeypatch):
    bruto = pd.DataFrame([
        ["Data", "Lote", "Contrapartida/Histórico", "Débito", "Crédito"],
        ["Conta:", "507", "Bradesco", None, None],
        [pd.Timestamp("2026-07-02"), "1", "364 - Fornecedor\r\nPagamento da nota\n123", None, 50],
        [pd.Timestamp("2026-07-02"), "2", "\nPagamento sem conta", None, 60],
    ])
    monkeypatch.setattr(dominio_ledger, "_ler_bruto", lambda *_: bruto)
    itens = dominio_ledger.ler_razao_dominio_base(b"xls", "Razão.xls", {"bradesco": "507"})
    assert [(i["debito"], i["credito"], i["historico"]) for i in itens] == [
        ("364", "507", "Pagamento da nota 123")
    ]

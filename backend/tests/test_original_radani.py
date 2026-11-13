import pandas as pd

from razync.radani import analisar_desmembramentos


def _extrato(valor=-33000.0, hist='SISPAG SALARIOS', banco='BANCO ITAU'):
    return pd.DataFrame([{
        'DESCRIÇÃO': banco, 'DATA': pd.Timestamp('2026-06-15'), 'VALOR': valor,
        'DÉBITO': '', 'CRÉDITO': '', 'HISTÓRICO': hist,
    }])


def _comprovantes():
    return pd.DataFrame([
        {'DATA': pd.Timestamp('2026-06-15'), 'HISTÓRICO': 'FUNC A VALE', 'VALOR': -20000.0, 'ARQUIVO': 'C', 'TIPO': 'VALE', 'FONTE': 'Comprovante SISPAG'},
        {'DATA': pd.Timestamp('2026-06-15'), 'HISTÓRICO': 'FUNC B VALE', 'VALOR': -13000.0, 'ARQUIVO': 'C', 'TIPO': 'VALE', 'FONTE': 'Comprovante SISPAG'},
    ])


def test_itau_sispag_fecha_com_comprovantes_e_desmembra():
    res = analisar_desmembramentos(_extrato(), 'Itaú', comprovantes=_comprovantes())
    assert len(res.organizado) == 2
    assert round(res.organizado['VALOR'].sum(), 2) == -33000.0
    assert set(res.detalhamentos['FONTE']) == {'Comprovante SISPAG'}
    assert res.revisoes.empty


def test_itau_sispag_sem_comprovante_fica_original():
    res = analisar_desmembramentos(_extrato(), 'Itaú', comprovantes=pd.DataFrame())
    assert len(res.organizado) == 1
    assert res.organizado.iloc[0]['HISTÓRICO'] == 'SISPAG SALARIOS'
    assert res.detalhamentos.empty


def test_bradesco_nao_usa_comprovantes_de_salario():
    extrato = _extrato(banco='BANCO BRADESCO')
    res = analisar_desmembramentos(extrato, 'Bradesco', comprovantes=_comprovantes())
    assert len(res.organizado) == 1
    assert res.organizado.iloc[0]['HISTÓRICO'] == 'SISPAG SALARIOS'
    assert res.detalhamentos.empty
    assert res.revisoes.empty


def test_pix_itau_permanece_como_extrato():
    extrato = _extrato(-150.0, 'PIX ENVIADO JOSE CLAUDIO')
    res = analisar_desmembramentos(extrato, 'Itaú', comprovantes=_comprovantes())
    assert len(res.organizado) == 1
    assert res.organizado.iloc[0]['HISTÓRICO'].startswith('PIX ENVIADO')


def test_radani_bradesco_retorna_dataframe_para_concatenacao(monkeypatch):
    from app import migration_services
    from razync import bradesco_radani
    original = [{
        'DESCRIÇÃO': 'BANCO BRADESCO',
        'DATA': pd.Timestamp('2026-10-01'),
        'VALOR': -120.0,
        'DÉBITO': '',
        'CRÉDITO': '',
        'HISTÓRICO': 'PAGAMENTO',
    }]
    monkeypatch.setattr(bradesco_radani, 'processar_extrato_bradesco_radani',
                        lambda content: (original, {'ok': True}))
    frame = migration_services.statement(968, 'bradesco', b'pdf', 'extrato.pdf')
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == 1
    assert frame.iloc[0]['VALOR'] == -120.0
    assert len(pd.concat([frame, frame], ignore_index=True)) == 2

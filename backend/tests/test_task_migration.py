from app import tasks
from app.migration_services import workflow
from test_migration import xlsx
from razync.task_deadlines import obter_competencia_operacional

def test_original_ng_completion_rule_only_after_success():
    _,period=obter_competencia_operacional()
    import pytest
    with pytest.raises(ValueError):
        workflow(1396,{}, {})
    assert tasks._statuses(period.isoformat())=={}
    data=xlsx([['Conta','Data','Valor','Lacto','Historico','Doc'],['98002-6','01/10/2026',100,'PAGAR','Fornecedor','1']])
    workflow(1396,{'consolidada':[('modelo.xlsx',data)]},{'bancos':['Itaú']})
    assert tasks._statuses(period.isoformat())=={'266':{'concluida':True}}

def test_import_task_status_is_idempotent_and_preserves_newer_target():
    row={'codigo_empresa':'242','competencia':'2026-09-01','concluida':True,'atualizado_em':'2026-09-15T10:00:00+00:00'}
    assert tasks.import_company_statuses([row])==1
    assert tasks.import_company_statuses([row])==0
    assert tasks._statuses('2026-09-01')['242']['concluida']
    tasks.set_company_status('242','2026-09-01',False)
    assert tasks.import_company_statuses([row])==0
    assert not tasks._statuses('2026-09-01')['242']['concluida']

CAPABILITIES = {
    3: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [{"name": "mapa", "label": "Mapa bancário", "accept": ".xls,.xlsx", "multiple": False}],
        "banks": {"itau": "508", "daycoval": "2283"},
    },
    47: {"status": "api_ready", "workflow": "standard", "banks": {"banco_brasil": "8"}},
    88: {"status": "api_ready", "workflow": "standard", "banks": {"itau": "508"}},
    154: {"status": "api_ready", "workflow": "standard_multi_bank", "banks": {"bradesco": "9", "itau": "508"}},
    178: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [{"name": "mapa", "label": "Mapa bancário", "accept": ".xls,.xlsx", "multiple": False}],
        "banks": {"itau": "508", "daycoval": "505"},
    },
    242: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "despesas", "label": "Despesas", "accept": ".xls,.xlsx", "multiple": False, "optional": True},
            {"name": "fornecedores", "label": "Fornecedores", "accept": ".xls,.xlsx", "multiple": False, "optional": True},
            {"name": "recebidos", "label": "Recebidos", "accept": ".xls,.xlsx", "multiple": False, "optional": True},
            {"name": "francesinhas", "label": "Francesinhas ZIP", "accept": ".zip", "multiple": False, "optional": True},
        ],
        "banks": {"itau_508": "508", "itau_509": "509", "banco_brasil": "8"},
    },
    266: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [{"name": "consolidada", "label": "Planilha consolidada", "accept": ".xls,.xlsx", "multiple": False}],
        "banks": {"itau": "", "bradesco": "", "fibra": ""},
    },
    285: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "jaguar", "label": "Planilha Jaguar", "accept": ".xls,.xlsx", "multiple": False},
            {"name": "entradas", "label": "Entradas detalhadas", "accept": ".xls,.xlsx", "multiple": False},
        ],
        "banks": {"santander": "513"},
    },
    343: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [{"name": "mapa", "label": "Mapa bancário", "accept": ".xls,.xlsx", "multiple": False}],
        "banks": {"itau": "508", "daycoval": "506"},
    },
    625: {"status": "api_ready", "workflow": "standard_multi_bank", "banks": {"banco_brasil": "8", "caixa": "508", "sicredi": "3999"}},
    626: {"status": "api_ready", "workflow": "standard_multi_bank", "banks": {"banco_brasil": "", "sicredi": ""}},
    841: {"status": "api_ready", "workflow": "standard", "banks": {"inter": "506"}},
    912: {"status": "api_ready", "workflow": "standard", "banks": {"sicredi": "515"}},
    964: {"status": "api_ready", "workflow": "standard", "banks": {"bradesco": "9"}},
    968: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "itau", "label": "Extrato Itaú", "accept": ".pdf", "multiple": True, "optional": True},
            {"name": "bradesco", "label": "Extrato Bradesco", "accept": ".pdf", "multiple": True, "optional": True},
            {"name": "sispag", "label": "Comprovantes SISPAG", "accept": ".pdf", "multiple": True, "optional": True},
        ],
        "banks": {"itau": "508", "bradesco": "9"},
    },
    969: {"status": "api_ready", "workflow": "standard", "banks": {"itau": "508"}},
    1000: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "itau", "label": "SIG Itaú", "accept": ".xls,.xlsx", "multiple": True, "optional": True},
            {"name": "sicredi", "label": "SIG Sicredi", "accept": ".xls,.xlsx", "multiple": True, "optional": True},
        ],
        "banks": {"itau": "508", "sicredi": "505"},
    },
    1001: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "itau", "label": "SIG Itaú", "accept": ".xls,.xlsx", "multiple": True, "optional": True},
            {"name": "sicredi", "label": "SIG Sicredi", "accept": ".xls,.xlsx", "multiple": True, "optional": True},
        ],
        "banks": {"itau": "508", "sicredi": "505"},
    },
    1064: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "sicredi", "label": "Planilha SIG Sicredi", "accept": ".xls,.xlsx", "multiple": True},
        ],
        "banks": {"sicredi": "505"},
    },
    1096: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "santander", "label": "SIG Santander", "accept": ".xls,.xlsx", "multiple": True, "optional": True},
            {"name": "sicredi", "label": "SIG Sicredi", "accept": ".xls,.xlsx", "multiple": True, "optional": True},
        ],
        "banks": {"santander": "513", "sicredi": "510"},
    },
    1208: {"status": "api_ready", "workflow": "standard_multi_bank", "banks": {"itau": "508", "safra": "512", "bradesco": "9"}},
    1211: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "extrato", "label": "Extrato Itaú", "accept": ".pdf", "multiple": False},
            {"name": "boletos", "label": "Boletos liquidados", "accept": ".xls,.xlsx,.pdf", "multiple": False},
        ],
        "banks": {"itau": ""},
    },
    1396: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [{"name": "consolidada", "label": "Planilha consolidada", "accept": ".xls,.xlsx", "multiple": False}],
        "banks": {"itau": "", "bradesco": ""},
    },
    1402: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "planilha", "label": "Planilha de caixa", "accept": ".xls,.xlsx", "multiple": False},
            {"name": "extrato", "label": "Extrato BTG", "accept": ".pdf", "multiple": False},
        ],
        "banks": {"btg": "510"},
    },
    1408: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "extrato", "label": "Extrato Itaú", "accept": ".pdf", "multiple": True},
            {"name": "recebidos", "label": "Planilha de recebidos", "accept": ".xls,.xlsx", "multiple": False, "optional": True},
            {"name": "francesinhas", "label": "Francesinhas ZIP", "accept": ".zip", "multiple": False, "optional": True},
        ],
        "options": [{"name": "ano", "label": "Ano de referência", "type": "number"}],
        "banks": {"itau": "512"},
    },
    1529: {
        "status": "api_ready",
        "workflow": "advanced",
        "roles": [
            {"name": "itau", "label": "Nibo Itaú", "accept": ".pdf", "multiple": True, "optional": True},
            {"name": "banco_brasil", "label": "Nibo Banco do Brasil", "accept": ".pdf", "multiple": True, "optional": True},
        ],
        "banks": {"itau": "508", "banco_brasil": "8"},
    },
    1530: {"status": "api_ready", "workflow": "standard", "banks": {"itau": "508"}},
    1532: {"status": "api_ready", "workflow": "standard", "banks": {"itau": "508"}},
}

COMMON_TOOLS = ["modelo_dominio", "base_inteligente", "conferencia_extrato"]
CAPABILITIES[1248] = {'status':'api_ready','workflow':'advanced','banks':{'itau':'508'},
    'roles':[{'name':'extrato','label':'Extrato Itaú RGR','accept':'.pdf','multiple':False},
             {'name':'movimentos','label':'Entradas e Saídas RGR','accept':'.xls,.xlsx','multiple':False}]}

# Accounts confirmed in the original modules/pages; never infer unknown accounts.
CAPABILITIES[626]['banks'] = {'banco_brasil': '8', 'sicredi': '1155'}
CAPABILITIES[625]['banks']['caixa'] = '504'
CAPABILITIES[266]['banks'] = {'itau': '508', 'bradesco': '9', 'fibra': '506'}
CAPABILITIES[1396]['banks'] = {'itau': '515', 'bradesco': '514'}
CAPABILITIES[1211]['banks'] = {'itau': '508'}
for code in (242, 1408):
    existing = CAPABILITIES[code]['roles']
    for role in existing:
        role['optional'] = True
    for name, label in (('despesas', 'Relatório Despesa'), ('fornecedores', 'Relatório Fornecedor'), ('recebidos', 'Relatório Recebido')):
        if not any(role['name'] == name for role in existing):
            existing.append({'name': name, 'label': label, 'accept': '.xls,.xlsx', 'multiple': False, 'optional': True})
    options = [
        {'name': 'data_inicial', 'label': 'Data inicial (opcional)', 'type': 'date'},
        {'name': 'data_final', 'label': 'Data final (opcional)', 'type': 'date'},
    ]
    if code == 1408:
        options.insert(0, {'name': 'ano', 'label': 'Ano de referência', 'type': 'number'})
    CAPABILITIES[code]['options'] = options
for code in (3, 178, 343, 266, 1396, 1000, 1001, 1064):
    CAPABILITIES[code]['options'] = [
        {'name': 'data_inicial', 'label': 'Data inicial (opcional)', 'type': 'date'},
        {'name': 'data_final', 'label': 'Data final (opcional)', 'type': 'date'},
    ]
# GZ's original boleto parser consumes PDF, not Excel.
next(r for r in CAPABILITIES[1211]['roles'] if r['name'] == 'boletos')['accept'] = '.pdf'
next(r for r in CAPABILITIES[1402]['roles'] if r['name'] == 'extrato')['optional'] = True
for capability in CAPABILITIES.values():
    capability['validation_status'] = 'pending_real_files'
COMMON_TOOLS.extend(['revisao_inteligente'])

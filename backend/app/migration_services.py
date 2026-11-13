"""Web orchestration of the original business rules, without Streamlit UI."""
from __future__ import annotations

import io
import os
import re
import zipfile
from datetime import datetime

import pandas as pd
from app import engine
from app.advanced import append_dataframe_sheets
from app.excel import _template_bytes, gerar_modelo_abas
from app.registry import CAPABILITIES

COLUNAS = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
SLUGS = {1050: 'f2r_excelencia_1050', 1303: 'bmz_moto_1303', 1167: 'imperio_gong_1167', 1160: 'gung_wen_1160', 933: 'cljm_933', 799: 'urocabral_799', 1399: 'jetmaq_1399', 1187: 'okktech_1187', 1151: 'mri_service_1151', 1131: 'cotas_premiadas_1131', 1058: 'quarteto_1058', 1033: 'terratest_1033', 1024: 'teles_veras_1024', 818: 'youz_818', 803: 'felix_gitti_803', 745: 'dourado_745', 521: 'bormais_521', 1522: 'priscila_camargo_1522', 1248: 'rgr_1248', 3: 'autokraft_industrial', 178: 'autokraft_projetos', 343: 'isa',
         242: 'eletro_forte', 1408: 'eletro_forte_filial_1408',
         266: 'nova_geracao_matriz', 1396: 'nova_geracao_filial',
         285: 'lcarlos', 968: 'radani', 1000: 'accede_automacao',
         1001: 'accede_equipamentos', 1096: 'up_pack', 1211: 'gz_1211',
         1402: 'vgv_1402', 734: 'empresa_734', 1529: 'dias_pereira', 47: 'crj_47',
         154: 'rm_postais_154', 625: 'valean_625', 626: 'valean_626',
         841: 'lucrativite_841', 912: 'vital_safety_912', 964: 'willians_964',
         88: 'hw_88', 969: 'engekraft_969', 1208: 'kairos_1208',
         1064: 'tech_control_1064', 1530: 'dias_pereira_1530', 1532: 'maria_narbutis_1532'}


def slug(code):
    return SLUGS.get(int(code), f'empresa_{code}')


def accounts(code):
    banks = dict(CAPABILITIES.get(int(code), {}).get('banks', {}))
    if int(code) == 242:
        return {'bb': '8', 'itau_508': '508', 'itau_509': '509'}
    if int(code) == 1408:
        return {'itau_512': '512'}
    banks.update(CAPABILITIES.get(int(code), {}).get('base_accounts', {}))
    return {key: str(value) for key, value in banks.items() if value}


def dates(options):
    start, end = options.get('data_inicial'), options.get('data_final')
    if bool(start) != bool(end):
        raise ValueError('Informe as duas datas do período.')
    if not start:
        return None, None
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if end < start:
        raise ValueError('A Data Final não pode ser anterior à Data Inicial.')
    return start.date(), end.date()


def filter_frame(frame, options):
    start, end = dates(options)
    return engine.filtrar_dataframe_periodo(frame, start, end) if start else frame.copy()


def filter_groups(groups, options):
    return {key: filtered for key, frame in (groups or {}).items()
            if not (filtered := filter_frame(frame, options)).empty}


def normalize_selected_banks(values):
    if values is None:
        return None
    aliases = {
        'itau': 'Itaú',
        'itaú': 'Itaú',
        'bradesco': 'Bradesco',
        'fibra': 'Fibra',
        'banco fibra': 'Fibra',
        'daycoval': 'Daycoval',
        'banco do brasil': 'Banco do Brasil',
        'banco_brasil': 'Banco do Brasil',
        'sicredi': 'Sicredi',
        'caixa': 'Caixa',
        'inter': 'Banco Inter',
        'banco inter': 'Banco Inter',
        'safra': 'Safra',
        'btg': 'BTG',
        'santander': 'Santander',
    }
    normalized = []
    for value in values:
        text = str(value or '').strip()
        normalized.append(aliases.get(text.casefold(), text))
    return normalized


SICREDI_PDF_TITULARES = {
    1000: "ACCEDE AUTOMACAO",
    1001: "ACCEDE EQUIPAMENTOS",
    1064: "TECH CONTROL",
    1096: "UP PACK",
}


def _sicredi_pdf_empresa(code, content):
    from app.advanced import _aplicar_conta
    from razync.valean_625 import processar_sicredi_625

    frame = processar_sicredi_625(content, titular=SICREDI_PDF_TITULARES.get(code))
    return _aplicar_conta(frame, accounts(code).get("sicredi", ""))


def statement(code, bank, content, filename):
    """Use specialized original readers; never mask a validation failure."""
    bank = str(bank).strip().casefold()
    if code == 1092:
        if bank != "sicredi" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1092: envie o extrato Sicredi em PDF.")
        from app.sicredi_1092 import read_statement
        return read_statement(content, accounts(code)[bank])
    if code == 1130:
        from app.rt_moto_1130 import statement as read_rt_statement
        return read_rt_statement(bank, content, filename)
    if code in {1165, 1166}:
        from app.otom_1165 import statement as otom_statement
        return otom_statement(bank, content, filename, company=code)
    if code == 1535:
        if bank != "banco_brasil" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1535: envie o extrato Banco do Brasil em PDF.")
        from app.bb_1535 import read_statement

        return read_statement(content)
    if code == 1536:
        if bank != "itau" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1536: envie o extrato Itaú em PDF.")
        from app.itau_1399 import read_statement

        return read_statement(content, holder=r"RODRIGUEZ\s+GONCALES\s+ASS\s+E\s+CONS\s+EMPRESARIAL\s+LTDA",
                              tax_id="50.958.498/0001-78", agency="0644", account="0098660-6",
                              accounting_account=accounts(code)[bank], allow_ocr=True)
    if code == 1537:
        if bank != "itau" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1537: envie o extrato Itaú em PDF.")
        from app.itau_1399 import read_statement

        names = frozenset(" ".join(name.casefold().split())
                          for name in os.getenv("RAZYNC_1537_SALARY_NAMES", "").splitlines()
                          if name.strip())
        if not names:
            raise ValueError("A lista de favorecidos de salários da empresa 1537 precisa ser configurada.")
        return read_statement(content, holder=r"RODRIGUEZ\s+GONCALES\s+SOCIEDADE\s+DE\s+ADVOGADOS",
                              tax_id=None, agency="0644", account="0007377-7",
                              accounting_account=accounts(code)[bank], salary_names=names)
    if code == 1050:
        if bank != "itau" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1050: envie o extrato mensal Itaú PDF.")
        from app.company_1050 import read_statement
        return read_statement(content)
    if code == 1303:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1303: extratos devem estar em PDF.")
        from app.company_1303 import READERS
        if bank not in READERS:
            raise ValueError("Empresa 1303: banco não cadastrado.")
        return READERS[bank](content)
    if code == 1167:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1167: extratos devem ser PDF.")
        from app.company_1167 import READERS
        if bank not in READERS:
            raise ValueError("Empresa 1167: banco não cadastrado.")
        return READERS[bank](content)
    if code == 1160:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1160: extratos devem ser PDF.")
        from app.company_1160 import READERS
        if bank not in READERS:
            raise ValueError("Banco não cadastrado para empresa 1160.")
        return READERS[bank](content)
    if code == 933:
        if bank != "itau" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 933: envie o extrato mensal Itaú PDF.")
        from app.company_933 import read_statement
        return read_statement(content)
    if code == 799:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 799: extratos devem ser PDF.")
        from app.company_799 import read_bradesco, read_santander
        if bank=="bradesco":
            return read_bradesco(content)
        if bank=="santander":
            return read_santander(content)
        raise ValueError("Empresa 799: banco não cadastrado.")
    if code == 1399:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1399: envie o extrato bancário PDF.")
        if bank == "itau":
            from app.itau_1399 import read_statement
        elif bank == "bradesco":
            from app.bradesco_1399 import read_statement
        else:
            raise ValueError("Banco não cadastrado na empresa 1399.")
        return read_statement(content)
    if code == 1187:
        if bank != "inter" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1187: envie extrato Banco Inter PDF.")
        from app.company_1187 import read_statement
        return read_statement(content)
    if code == 1151:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1151: extrato bancário deve ser PDF.")
        from app.company_1151 import read_itau, read_nubank
        if bank=="itau":
            return read_itau(content)
        if bank=="nubank":
            return read_nubank(content)
        raise ValueError("Banco não configurado para a empresa 1151.")
    if code == 1131:
        if bank != "itau" or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1131: envie o extrato Itaú PDF.")
        from app.itau_1131 import read_bank
        return read_bank(content)[0]
    if code == 1058:
        from app.company_1058 import read_caixa
        if bank == 'caixa':
            if not filename.lower().endswith('.pdf'):
                raise ValueError('Empresa 1058: a Caixa exige extrato PDF.')
            return read_caixa(content)
        if bank == 'itau':
            if not filename.lower().endswith(('.pdf', '.ofx', '.xls', '.xlsx', '.csv')):
                raise ValueError('Empresa 1058: envie extrato Itaú PDF, OFX, XLS, XLSX ou CSV.')
            from app.company_1058 import read_itau_statement
            return read_itau_statement(content, filename)
        raise ValueError('Banco não configurado para a empresa 1058.')
    if code == 1033:
        from app.bradesco_1033 import read_statement
        if bank != 'bradesco' or not filename.lower().endswith('.pdf'):
            raise ValueError('Empresa 1033: envie um extrato Bradesco em PDF.')
        return read_statement(content)
    if code == 1024:
        from app.empresa_1024 import _statement
        if bank not in {"bb", "banco_brasil"} or not filename.lower().endswith(".pdf"):
            raise ValueError("Empresa 1024: envie o extrato BB em PDF.")
        return _statement(content)[0]
    if code == 745:
        from app.itau_monthly_745 import read_statement
        return read_statement(content)
    if code == 521:
        from app.caixa_521 import read_payments
        from app.global_tools import processar_arquivo
        report = read_payments(content, optional=True) if filename.lower().endswith(".xlsx") else None
        if report is not None:
            return report
        frame = processar_arquivo(content, filename)
        banks = {engine.identificar_chave_banco_empresa(value) for value in frame["DESCRIÇÃO"]}
        if banks - {"", "caixa"}:
            raise ValueError("O extrato enviado não corresponde ao banco Caixa.")
        return frame
    with engine.processing_context(slug(code)):
        if bank == 'sicredi' and content.startswith(b'%PDF'):
            if code == 1001:
                return _sicredi_pdf_empresa(code, content)
            if code not in {625, 626, 912}:
                from app.advanced import _aplicar_conta
                from razync.valean_625 import _texto_pdf, ler_sicredi_sem_texto

                if not _texto_pdf(content).strip():
                    frame = ler_sicredi_sem_texto(content, titular=SICREDI_PDF_TITULARES.get(code))
                    return _aplicar_conta(frame, accounts(code).get(bank, ""))
        # Na 1529, valida o PDF Consultas sem alterar leitores das outras empresas.
        if code == 1529 and bank in {'banco_brasil', 'bb'} and str(filename).lower().endswith('.pdf'):
            from app.bb_consultas import parece_extrato_bb_consultas, ler_extrato_bb_consultas
            if parece_extrato_bb_consultas(content):
                return pd.DataFrame(ler_extrato_bb_consultas(content), columns=COLUNAS)
        if code == 1522 and bank == 'santander':
            from app.santander_consolidado_1522 import read_statement
            return read_statement(content, filename)
        if code == 734:
            from app.bank_734 import read_bank_pdf
            return read_bank_pdf(bank, content, filename)
        # Empresa 266: layout BB Consultas com coluna Valor R$ e natureza C/D.
        # Não substituir os outros leitores BB (Autorizável, CRJ, etc.).
        if code == 266 and bank in {'banco_brasil', 'bb'} and str(filename).lower().endswith('.pdf'):
            from app.bb_consultas_266 import (
                parece_extrato_bb_consultas_266, ler_extrato_bb_consultas_266,
            )
            if parece_extrato_bb_consultas_266(content):
                return pd.DataFrame(ler_extrato_bb_consultas_266(content), columns=COLUNAS)
        if code == 1248:
            from razync.rgr_1248 import ler_extrato_itau_rgr
            return ler_extrato_itau_rgr(content)
        if code in {88, 625, 626, 841, 969, 1208, 1530}:
            from app.main import _process_modular
            return _process_modular(code, bank, content, filename)
        if code == 47:
            return engine._processar_bb_crj_47(content)
        if code == 154:
            return (engine._processar_bradesco_154 if bank == 'bradesco' else engine._processar_itau_154)(content)
        if code == 912:
            return engine._processar_sicredi_912(content)
        if code == 964:
            return engine._processar_bradesco_964(content)
        if code == 1532:
            from razync.engekraft_969 import processar_extrato_itau_modelo
            return processar_extrato_itau_modelo(content, '508', ('MARIA A D P NARB', '59.124.979/0001-52', '0097731-6'), '1532 - Maria Narbutis')
        if code == 968 and bank == 'bradesco':
            from razync.bradesco_radani import processar_extrato_bradesco_radani
            return pd.DataFrame(processar_extrato_bradesco_radani(content)[0], columns=COLUNAS)
        # PDF Aplicativo Santander Empresas (Valor + Saldo): aceita em todas
        # as empresas configuradas com Santander, sem alterar SIG/XLS.
        if bank == 'santander' and filename.lower().endswith('.pdf'):
            from app.santander_aplicativo import (
                parece_extrato_santander_aplicativo,
                processar_extrato_santander_aplicativo_pdf,
            )
            text_first = (engine.PdfReader(io.BytesIO(content), strict=False).pages[0].extract_text() or '')
            if parece_extrato_santander_aplicativo(text_first):
                return pd.DataFrame(processar_extrato_santander_aplicativo_pdf(content), columns=COLUNAS)
        if code == 285 and bank == 'santander':
            from razync.santander_statement import processar_extrato_santander_empresarial_texto
            text = '\n'.join(p.extract_text() or '' for p in engine.PdfReader(io.BytesIO(content)).pages)
            records = processar_extrato_santander_empresarial_texto(text)
            if not records:
                raise ValueError('Formato Santander não reconhecido. Envie o PDF original do extrato.')
            return pd.DataFrame(records, columns=COLUNAS)
        if code == 1211 and bank == 'itau':
            from razync.gz_1211 import ler_extrato_itau_gz
            return ler_extrato_itau_gz(content)
        aliases = {88: 'itau_hw88', 969: 'itau_969', 1530: 'itau_1530'}
        if code in {625, 626}:
            forced = f'{bank}_{code}'
        elif code == 1208:
            forced = f'{bank}_1208'
        elif code == 841:
            forced = 'inter_841'
        else:
            forced = aliases.get(code, 'itau' if bank.startswith('itau') else bank)
        rows = engine.processar_extrato_conferencia_empresa(content, filename, forced)
        frame = pd.DataFrame(rows, columns=COLUNAS)
        if frame.empty:
            raise ValueError(engine.request_state.get().get('ultimo_erro_extrato') or 'Nenhum lançamento válido foi encontrado no extrato.')
        return frame


def reconcile(code, bank, model, statements, options=None):
    options = options or {}
    with engine.processing_context(slug(code)):
        real_bank = 'itau' if bank.startswith('itau') else bank
        account = CAPABILITIES.get(code, {}).get('banks', {}).get(bank) if code in {242, 799, 933, 977, 1050, 1092, 1160, 1167, 1303, 1408, 1058, 1130, 1151, 1165, 1166, 1187, 1399, 1535, 1536, 1537} else None
        main, excluded, _ = engine.ler_planilha_organizada_conferencia(model, real_bank, account)
        main, excluded = filter_frame(main, options), filter_frame(excluded, options)
        if code == 521:
            main = main.loc[main["VALOR"] < 0]
            excluded = excluded.loc[excluded["VALOR"] < 0]
        if main.empty:
            raise ValueError('Nenhum lançamento do banco/conta selecionado foi encontrado no Modelo Domínio.')
        if code == 977:
            from app.francesinhas_977 import bank_frames

            pdfs = [upload for upload in statements if upload[0].lower().endswith(".pdf")]
            zips = [upload for upload in statements if upload[0].lower().endswith(".zip")]
            if not pdfs or len(pdfs) + len(zips) != len(statements):
                raise ValueError("Envie o extrato em PDF e, para o Bradesco, o ZIP das francesinhas se utilizado.")
            movements = filter_frame(bank_frames(bank, pdfs, zips), options)
        else:
            frames = [statement(code, bank, content, filename) for filename, content in statements]
            movements = filter_frame(pd.concat(frames, ignore_index=True), options)
            if code in {1165, 1166} and not dates(options)[0]:
                months = set(pd.to_datetime(main["DATA"]).dt.to_period("M"))
                movements = movements.loc[pd.to_datetime(movements["DATA"]).dt.to_period("M").isin(months)]
            if code == 1151 and bank == 'nubank' and not dates(options)[0]:
                # O extrato Nubank cruza agosto e setembro: comparar somente
                # as competências presentes no Modelo Domínio, já conferido.
                model_months = set(pd.to_datetime(main['DATA'], dayfirst=True).dt.to_period('M'))
                statement_months = pd.to_datetime(movements['DATA'], dayfirst=True).dt.to_period('M')
                movements = movements.loc[statement_months.isin(model_months)].copy()
        if code == 521:
            movements = movements.loc[movements["VALOR"] < 0]
            if movements.empty:
                raise ValueError("Nenhum pagamento encontrado no extrato no período selecionado.")
        daily, missing, extra, ignored = engine.conciliar_empresa_com_extrato(main, movements, excluded)
        summary = {'ok': missing.empty and extra.empty, 'planilha': len(main),
                   'extrato': len(movements), 'conferidos': len(main) - len(extra),
                   'faltando_planilha': len(missing), 'a_mais_planilha': len(extra),
                   'ignorados': len(ignored)}
        if code == 521:
            summary['escopo'] = 'Somente pagamentos'
        for side, suffix in [('planilha', 'PLANILHA'), ('extrato', 'EXTRATO')]:
            for name, label in [('entradas', 'ENTRADAS'), ('saidas', 'SAÍDAS')]:
                summary[f'{name}_{side}'] = round(float(daily[f'{label} {suffix}'].sum()), 2)
        return summary, {'Resumo': pd.DataFrame([summary]), 'Conferência diária': daily,
                         'Faltando na planilha': missing, 'A mais na planilha': extra,
                         'Estornos ignorados': ignored, 'Modelo analisado': main, 'Extrato analisado': movements}


def eletro_reports(code, roles, options):
    from razync.eletro_forte import (processar_despesas, processar_fornecedores,
        processar_recebidos, inferir_ano_recebidos, gerar_modelo_dominio_eletro_forte,
        gerar_consolidado_bancos_eletro_forte)
    from razync.eletro_forte_francesinhas import processar_zip_francesinhas, corrigir_datas_com_francesinhas
    start, end = dates(options)
    if start and start.year != end.year:
        raise ValueError('Selecione um período dentro do mesmo ano para estes relatórios.')
    year = start.year if start else int(options.get('ano') or datetime.now().year)
    single = '512' if code == 1408 else None
    groups, artifacts, extras = {}, {}, {}
    for name, parser in [('despesas', processar_despesas), ('fornecedores', processar_fornecedores), ('recebidos', processar_recebidos)]:
        uploads = roles.get(name, [])
        parsed = {}
        for filename, content in uploads:
            part = parser(content, year, single)
            for account, frame in part.items():
                parsed.setdefault(account, []).append(frame)
        groups[name] = {key: pd.concat(frames, ignore_index=True) for key, frames in parsed.items()}
    if roles.get('francesinhas') and groups['recebidos']:
        frames, notices = [], []
        for _, content in roles['francesinhas']:
            data, warnings = processar_zip_francesinhas(content, single)
            frames.append(data); notices.extend(warnings)
        corrected, summary, pending = corrigir_datas_com_francesinhas(groups['recebidos'], pd.concat(frames, ignore_index=True))
        groups['recebidos'] = corrected
        extras = {'Pendências francesinhas': pending, 'Resumo francesinhas': pd.DataFrame([summary]), 'Avisos francesinhas': pd.DataFrame({'AVISO': notices})}
    for name in groups:
        groups[name] = filter_groups(groups[name], options)
        if groups[name]:
            filename, content = roles[name][0]
            book = gerar_modelo_dominio_eletro_forte(content, filename, _template_bytes(),
                groups[name] if name == 'despesas' else None,
                groups[name] if name == 'fornecedores' else {},
                groups[name] if name == 'recebidos' else {})
            artifacts[f'ELETRO_FORTE_{code}_{name.upper()}.xlsx'] = append_dataframe_sheets(book, extras) if name == 'recebidos' and extras else book
    if not artifacts:
        raise ValueError('Envie Despesa, Fornecedor e/ou Recebido com lançamentos no período selecionado.')
    consolidated = gerar_consolidado_bancos_eletro_forte(_template_bytes(), groups['despesas'], groups['fornecedores'], groups['recebidos'])
    artifacts[f'ELETRO_FORTE_{code}_CONSOLIDADO.xlsx'] = append_dataframe_sheets(consolidated, extras) if extras else consolidated
    return artifacts


def workflow(code, roles, options):
    result = _workflow(code, roles, options)
    # These are the two automatic task-completion rules in app_legacy.py.
    if code in {285,266,1396}:
        try:
            from app.tasks import set_company_status
            from razync.task_deadlines import obter_competencia_operacional
            _, competencia = obter_competencia_operacional()
            set_company_status('285' if code == 285 else '266', competencia.isoformat(), True)
        except Exception:
            import logging
            logging.getLogger(__name__).warning('Modelo gerado; tarefa não atualizada.', exc_info=True)
    return result


def _workflow_1408(roles):
    from razync.eletro_forte_filial_1408 import montar_modelo_1408
    from razync.eletro_forte_francesinhas import processar_zip_francesinhas

    extratos = roles.get('extrato') or []
    recebidos = roles.get('recebidos') or []
    if not extratos:
        raise ValueError('Envie o Extrato Itaú da empresa 1408.')
    if not recebidos:
        raise ValueError('Envie a Planilha de recebidos da empresa 1408.')

    movements = pd.concat(
        [statement(1408, 'itau', content, name) for name, content in extratos],
        ignore_index=True,
    )
    datas = pd.to_datetime(movements.get('DATA'), dayfirst=True, errors='coerce').dropna()
    if datas.empty:
        raise ValueError('Não foi possível identificar o ano pelo Extrato Itaú da empresa 1408.')
    year = int(datas.dt.year.mode().iloc[0])

    parts = []
    parser_warnings = []
    for _, content in (roles.get('francesinhas') or []):
        parsed, warnings = processar_zip_francesinhas(content, '512')
        parts.append(parsed)
        parser_warnings.extend(warnings)
    details = pd.concat(parts, ignore_index=True) if parts else None
    frame, summary = montar_modelo_1408(
        movements.to_dict('records'),
        recebidos[0][1],
        year,
        details,
    )
    summary = dict(summary)
    summary['avisos_francesinhas'] = parser_warnings + list(summary.get('avisos_francesinhas') or [])
    book = engine.gerar_excel_modelo_dominio(frame)
    return book, 'ELETRO_FORTE_1408_MODELO_DOMINIO.xlsx', summary


def _workflow(code, roles, options):
    from app.advanced import workflow_modelo
    with engine.processing_context(slug(code)):
        if code == 1130:
            from app.rt_moto_1130 import workflow as rt_workflow
            return rt_workflow(roles, options)
        if code in {1165, 1166}:
            from app.otom_1165 import workflow as otom_workflow
            return otom_workflow(roles, options, company=code)
        if code == 1050:
            from app.company_1050 import workflow_1050
            return workflow_1050(roles, options)
        if code == 1303:
            from app.company_1303 import workflow_1303
            return workflow_1303(roles, options)
        if code == 1167:
            from app.company_1167 import workflow_1167
            return workflow_1167(roles,options)
        if code == 1160:
            from app.company_1160 import workflow_1160
            return workflow_1160(roles,options)
        if code == 933:
            from app.company_933 import workflow_933
            return workflow_933(roles,options)
        if code == 799:
            from app.company_799 import workflow_799
            return workflow_799(roles,options)
        if code == 1399:
            from app.company_1399 import workflow_1399
            return workflow_1399(roles,options)
        if code == 1187:
            from app.company_1187 import workflow_1187
            return workflow_1187(roles, options)
        if code == 1151:
            from app.company_1151 import workflow_1151
            return workflow_1151(roles,options)
        if code == 1131:
            from app.itau_1131 import workflow_1131
            return workflow_1131(roles, options)
        if code == 1058:
            from app.company_1058 import workflow_1058
            return workflow_1058(roles, options)
        if code == 1033:
            from app.bradesco_1033 import workflow_1033
            return workflow_1033(roles, options)
        if code == 1024:
            from app.empresa_1024 import workflow_1024
            return workflow_1024(roles, options)
        if code == 977:
            from app.francesinhas_977 import bank_frames

            zips = roles.get("francesinhas", [])
            if zips and not roles.get("bradesco"):
                raise ValueError("Envie o extrato Bradesco junto com o ZIP das francesinhas.")
            sheets = {}
            for bank, label in (("bradesco", "Bradesco"), ("banco_brasil", "Banco do Brasil")):
                uploads = roles.get(bank, [])
                if not uploads:
                    continue
                frame = filter_frame(bank_frames(bank, uploads, zips if bank == "bradesco" else ()), options)
                if frame.empty:
                    continue
                paid = frame["VALOR"] < 0
                account = accounts(code)[bank]
                frame["DÉBITO"] = ["" if payment else account for payment in paid]
                frame["CRÉDITO"] = [account if payment else "" for payment in paid]
                frame["HISTÓRICO"] = [
                    ("Pago: " if payment else "Recebido: ") + re.sub(r"^(?:Pago|Recebido):\s*", "", history, flags=re.I)
                    for payment, history in zip(paid, frame["HISTÓRICO"])
                ]
                sheets[label] = frame.sort_values("DATA", kind="stable")
            if not sheets:
                raise ValueError("Envie pelo menos um extrato com lançamentos no período.")
            return gerar_modelo_abas(sheets, date_format="dd/mm/yyyy"), "EMPRESA_977_MODELO_DOMINIO.xlsx"
        if code == 1092:
            from app.sicredi_1092 import enrich

            extracts = roles.get("extrato", [])
            if len(extracts) != 1:
                raise ValueError("Envie um extrato mensal Sicredi por processamento.")
            filename, content = extracts[0]
            frame = statement(code, "sicredi", content, filename)
            frame = filter_frame(enrich(frame, [pdf for _, pdf in roles.get("comprovantes", [])]), options)
            if frame.empty:
                raise ValueError("Nenhum lançamento no período selecionado.")
            return gerar_modelo_abas({"Sicredi": frame.sort_values("DATA", kind="stable")}, date_format="dd/mm/yyyy"), "HOREB_1092_SICREDI_MODELO_DOMINIO.xlsx"
        if code == 818:
            from app.santander_boletos_818 import enrich

            extracts, reports = roles.get("extrato", []), roles.get("boletos", [])
            if len(extracts) != 1 or len(reports) != 1:
                raise ValueError("Envie um extrato e um relatório de boletos liquidados da mesma competência.")
            filename, statement_pdf = extracts[0]
            frame = statement(code, "santander", statement_pdf, filename)
            frame = filter_frame(enrich(frame, statement_pdf, reports[0][1]), options)
            if frame.empty:
                raise ValueError("Nenhum lançamento no período selecionado.")
            paid = frame["VALOR"] < 0
            frame["DÉBITO"] = ["509" if not payment else "" for payment in paid]
            frame["CRÉDITO"] = ["509" if payment else "" for payment in paid]
            frame["HISTÓRICO"] = [
                ("Pago: " if payment else "Recebido: ") + re.sub(r"^(?:Pago|Recebido):\s*", "", history, flags=re.I)
                for payment, history in zip(paid, frame["HISTÓRICO"])
            ]
            return gerar_modelo_abas({"Santander": frame.sort_values("DATA", kind="stable")}, date_format="dd/mm/yyyy"), "YOUZ_818_SANTANDER_MODELO_DOMINIO.xlsx"
        if code == 803:

            uploads = roles.get("extrato", [])
            if not uploads:
                raise ValueError("Envie o Extrato Mensal Bradesco em PDF.")
            frames = [statement(code, "bradesco", content, filename) for filename, content in uploads]
            frame = filter_frame(pd.concat(frames, ignore_index=True), options)
            if frame.empty:
                raise ValueError("Nenhum lançamento no período selecionado.")
            paid = frame["VALOR"] < 0
            frame["DÉBITO"] = ["9" if not payment else "" for payment in paid]
            frame["CRÉDITO"] = ["9" if payment else "" for payment in paid]
            frame["HISTÓRICO"] = [
                ("Pago: " if payment else "Recebido: ") + history
                for payment, history in zip(paid, frame["HISTÓRICO"])
            ]
            return gerar_modelo_abas({"Bradesco": frame.sort_values("DATA", kind="stable")}, date_format="dd/mm/yyyy"), "FELIX_GITTI_803_BRADESCO_MODELO_DOMINIO.xlsx"
        if code == 745:
            from app.itau_monthly_745 import read_statement

            uploads = roles.get("extrato", [])
            if not uploads:
                raise ValueError("Envie o Extrato Mensal Itaú em PDF.")
            frames = [read_statement(content) for _, content in uploads]
            periods = [frame["DATA"].iloc[0].to_period("M") for frame in frames]
            if len(set(periods)) != len(periods):
                raise ValueError("Envie somente um extrato mensal por competência.")
            frame = filter_frame(pd.concat(frames, ignore_index=True), options)
            if frame.empty:
                raise ValueError("Nenhum lançamento no período selecionado.")
            return gerar_modelo_abas({"Itaú": frame.sort_values("DATA", kind="stable")}, date_format="dd/mm/yyyy"), "DOURADO_745_ITAU_MODELO_DOMINIO.xlsx"
        if code == 521:
            from app.caixa_521 import read_payments

            uploads = roles.get("pagamentos", [])
            if not uploads:
                raise ValueError("Envie o relatório de pagamentos com a aba Caixa.")
            frame = filter_frame(pd.concat([read_payments(content) for _, content in uploads], ignore_index=True), options)
            if frame.empty:
                raise ValueError("Nenhum pagamento no período selecionado.")
            return gerar_modelo_abas({"Caixa": frame.sort_values("DATA", kind="stable")}, date_format="dd/mm/yyyy"), "BORMAIS_521_CAIXA_MODELO_DOMINIO.xlsx"
        if code == 1522:
            from app.santander_consolidado_1522 import workflow_1522
            return workflow_1522(roles, options)
        if code == 734:
            from app.bank_734 import workflow_734
            return workflow_734(roles, options)
        if code == 1408:
            book, filename, _ = _workflow_1408(roles)
            return book, filename
        if code == 242 and any(roles.get(name) for name in ('despesas', 'fornecedores', 'recebidos')):
            reports = eletro_reports(code, roles, options)
            key = f'ELETRO_FORTE_{code}_CONSOLIDADO.xlsx'
            return reports[key], key
        if code in {3, 178, 343}:
            maps = roles.get('mapa', [])
            if not maps:
                raise ValueError('Envie o mapa bancário.')
            groups = {}
            selected_banks = normalize_selected_banks(options.get('bancos'))
            allowed = selected_banks or ['Itaú', 'Daycoval']
            for filename, content in maps:
                data, _ = engine.processar_mapa_autokraft(content, filename)
                for bank, block in data.items():
                    if bank in allowed:
                        groups.setdefault(bank, []).append(filter_frame(block['principal'], options))
            data = {bank: {'principal': pd.concat(parts, ignore_index=True), 'retirados': pd.DataFrame()} for bank, parts in groups.items()}
            if not data or all(block['principal'].empty for block in data.values()):
                raise ValueError('Nenhum lançamento no período/bancos selecionados.')
            return engine.gerar_excel_nova_geracao(data), f'RAZYNC_{code}_MODELO_DOMINIO.xlsx'
        if code in {266, 1396}:
            uploads = roles.get('consolidada', [])
            if not uploads:
                raise ValueError('Envie a planilha consolidada.')
            if code == 266:
                from app.nova_geracao_bb_266 import ABA_MODELO, processar_nova_geracao_bb_266
                parsers = {
                    'Itaú': engine.processar_nova_geracao_itau,
                    'Bradesco': engine.processar_nova_geracao_bradesco,
                    'Fibra': engine.processar_nova_geracao_fibra,
                    'Banco do Brasil': processar_nova_geracao_bb_266,
                }
            else:
                parsers = {
                    'Itaú': engine.processar_nova_geracao_filial_itau,
                    'Bradesco': engine.processar_nova_geracao_filial_bradesco,
                }
            data = {}
            errors = []
            selected_banks = normalize_selected_banks(options.get('bancos'))
            for bank, parser in parsers.items():
                if selected_banks is not None and bank not in selected_banks:
                    continue
                principal, removed = [], []
                for _, content in uploads:
                    try:
                        main, excluded = parser(content)
                        principal.append(filter_frame(main, options)); removed.append(filter_frame(excluded, options) if not excluded.empty else excluded)
                    except ValueError as exc:
                        if selected_banks is not None:
                            raise ValueError(f'{bank}: {exc}') from exc
                        errors.append(f'{bank}: {exc}')
                if principal:
                    sheet = ABA_MODELO if code == 266 and bank == 'Banco do Brasil' else bank
                    data[sheet] = {'principal': pd.concat(principal, ignore_index=True).sort_values('DATA',kind='stable'), 'retirados': pd.concat(removed, ignore_index=True).sort_values('DATA',kind='stable')}
            if not data:
                raise ValueError('; '.join(errors))
            return engine.gerar_excel_nova_geracao(data, _template_bytes(), prefixar_historicos=False), f'RAZYNC_{code}_MODELO_DOMINIO.xlsx'
        if code in {1000, 1001, 1064}:
            data = {}
            permitted_banks = ('itau', 'sicredi', 'santander') if code == 1001 else ('itau', 'sicredi')
            for bank in permitted_banks:
                if roles.get(bank):
                    if bank == 'santander' and code == 1001:
                        # Extrato PDF real do Aplicativo Santander Empresas:
                        # mantém as verificações de sequência de saldos em centavos
                        # e não reutiliza o leitor de planilhas SIG.
                        from app.santander_aplicativo import processar_extrato_santander_aplicativo_pdf
                        import hashlib
                        frames = []
                        seen_files = set()
                        for filename, content in roles[bank]:
                            if not str(filename).lower().endswith('.pdf') or not content.startswith(b'%PDF'):
                                raise ValueError('Santander 513: envie o extrato original em PDF.')
                            fingerprint = hashlib.sha256(content).digest()
                            if fingerprint in seen_files:
                                raise ValueError('Santander 513: mesmo extrato PDF enviado mais de uma vez.')
                            seen_files.add(fingerprint)
                            part = pd.DataFrame(
                                processar_extrato_santander_aplicativo_pdf(content), columns=COLUNAS
                            )
                            from pypdf import PdfReader
                            header = (PdfReader(io.BytesIO(content), strict=False).pages[0].extract_text() or '')
                            if 'ACCEDE EQUIPAMENTOS' not in ' '.join(header.upper().split()):
                                raise ValueError('Santander 513: o titular do extrato não corresponde à empresa 1001.')
                            # Datas brasileiras explícitas: 03/08 não pode virar 08/03.
                            part['DATA'] = pd.to_datetime(
                                part['DATA'], format='%d/%m/%Y', errors='raise'
                            )
                            frames.append(part)
                    elif bank == 'sicredi':
                        frames = [
                            _sicredi_pdf_empresa(code, content)
                            if content.startswith(b'%PDF')
                            else engine.processar_planilha_accede_sig(content, bank, slug(code))
                            for _, content in roles[bank]
                        ]
                    else:
                        frames = [
                            engine.processar_planilha_accede_sig(content, bank, slug(code))
                            for _, content in roles[bank]
                        ]
                    frame = filter_frame(pd.concat(frames, ignore_index=True), options)
                    if bank == 'santander' and code == 1001:
                        if frame.empty:
                            raise ValueError('Santander 513: nenhum lançamento no período selecionado.')
                        # Leitor valida os saldos na ordem original; o Modelo Domínio
                        # recebe as movimentações em ordem cronológica estável.
                        frame = frame.sort_values('DATA', kind='stable').reset_index(drop=True).copy()
                        frame['DÉBITO'] = frame['VALOR'].apply(lambda value: '513' if float(value) > 0 else '')
                        frame['CRÉDITO'] = frame['VALOR'].apply(lambda value: '513' if float(value) < 0 else '')
                    data[bank.title()] = {'principal': frame, 'retirados': pd.DataFrame()}
            if not data:
                if code == 1064:
                    raise ValueError('Envie o Sicredi em SIG ou PDF.')
                if code == 1001:
                    raise ValueError('Envie a planilha SIG do Itaú, o Sicredi em SIG ou PDF, ou o extrato PDF do Santander.')
                raise ValueError('Envie o SIG Itaú e/ou o Sicredi em SIG ou PDF.')
            filename = 'TECH_CONTROL_1064_SICREDI_505_MODELO_DOMINIO.xlsx' if code == 1064 else f'ACCEDE_{code}_MODELO_DOMINIO.xlsx'
            return engine.gerar_excel_nova_geracao(data, _template_bytes()), filename
        # Existing modular processors remain intact. Replace only universal readers
        # and rewritten SIG/map functions with their original implementations.
        if code == 1248:
            from razync.rgr_1248 import processar_rgr
            if not roles.get('extrato') or not roles.get('movimentos'):
                raise ValueError('Envie extrato Itaú PDF e planilha Entradas e Saídas.')
            frame, _, _, _, _ = processar_rgr(roles['extrato'][0][1], roles['movimentos'][0][1])
            frame = filter_frame(frame, options)
            datas = pd.to_datetime(frame['DATA'], errors='coerce').dropna()
            periodo = f"{datas.min():%d%m%Y}_A_{datas.max():%d%m%Y}" if not datas.empty else 'PERIODO'
            return engine.gerar_excel_modelo_dominio(frame, formato_data='dd/mm/yyyy'), f'RGR_1248_ITAU_508_MODELO_DOMINIO_{periodo}.xlsx'
        if code == 285:
            from razync.lcarlos import processar_planilhas_lcarlos
            if not roles.get('jaguar') or not roles.get('entradas'):
                raise ValueError('Envie Jaguar e Entradas detalhadas.')
            frame, _, _ = processar_planilhas_lcarlos(roles['jaguar'][0][1], roles['entradas'][0][1])
            return engine.gerar_excel_modelo_dominio(filter_frame(frame, options)), 'LCARLOS_285_MODELO_DOMINIO.xlsx'
        if code == 1402:
            from razync.vgv_1402 import ler_caixa_vgv
            if not roles.get('planilha'):
                raise ValueError('Envie a planilha Caixa VGV. O extrato é opcional para conferência.')
            return engine.gerar_excel_modelo_dominio(filter_frame(ler_caixa_vgv(roles['planilha'][0][1])[COLUNAS], options)), 'VGV_1402_MODELO_DOMINIO.xlsx'
        if code == 1211:
            from razync.gz_1211 import processar_gz, gerar_modelo_dominio_gz
            if not roles.get('extrato') or not roles.get('boletos'):
                raise ValueError('Envie Extrato Itaú e Boletos liquidados em PDF.')
            frame, _, _, _ = processar_gz(roles['extrato'][0][1], roles['boletos'][0][1])
            return gerar_modelo_dominio_gz(filter_frame(frame, options), _template_bytes()), 'GZ_1211_MODELO_DOMINIO.xlsx'
        if code == 1096:
            from razync.up_pack import processar_planilha_up_pack
            groups = {}
            for bank in ('santander', 'sicredi'):
                if roles.get(bank):
                    frames = [
                        _sicredi_pdf_empresa(code, content)
                        if bank == 'sicredi' and content.startswith(b'%PDF')
                        else processar_planilha_up_pack(content, bank)
                        for _, content in roles[bank]
                    ]
                    groups[bank.title()] = {'principal': filter_frame(pd.concat(frames, ignore_index=True), options), 'retirados': pd.DataFrame()}
            if not groups:
                raise ValueError('Envie o SIG Santander e/ou o Sicredi em SIG ou PDF.')
            return engine.gerar_excel_nova_geracao(groups, _template_bytes()), 'UP_PACK_1096_MODELO_DOMINIO.xlsx'
        if code == 1529:
            from razync.nibo import processar_extrato_nibo_pdf
            from app.bb_consultas import parece_extrato_bb_consultas
            from app.organizer_jobs import progress
            current_file = 0
            total_files = sum(len(roles.get(bank, [])) for bank in ('itau', 'banco_brasil'))
            groups = {}
            for bank, description in [('itau', 'BANCO ITAÚ'), ('banco_brasil', 'BANCO DO BRASIL')]:
                frames = []
                for filename, content in roles.get(bank, []):
                    current_file += 1
                    progress(current_file, total_files)
                    # O extrato original do BB tem colunas diferentes do Nibo.
                    # Use o mesmo leitor validado da conferência; erros de saldo
                    # precisam interromper a geração, sem tentar OCR como fallback.
                    if bank == 'banco_brasil' and parece_extrato_bb_consultas(content):
                        frame = statement(code, bank, content, filename)[COLUNAS].copy()
                    else:
                        frame = processar_extrato_nibo_pdf(content)[COLUNAS].copy()
                    frame['DESCRIÇÃO'] = description
                    frames.append(frame)
                if frames:
                    frame = pd.concat(frames, ignore_index=True)
                    frame['_DATA_ORDEM'] = pd.to_datetime(frame['DATA'], dayfirst=True, errors='coerce')
                    frame = frame.sort_values('_DATA_ORDEM', kind='stable').drop(columns=['_DATA_ORDEM']).reset_index(drop=True)
                    frame = filter_frame(frame, options)
                    groups['Itaú' if bank == 'itau' else 'Banco do Brasil'] = engine.padronizar_historicos_modelo(frame)
            if not groups:
                raise ValueError('Envie PDF Nibo do Itaú e/ou Banco do Brasil, ou o extrato original BB Consultas.')
            return gerar_modelo_abas(groups), 'DIAS_PEREIRA_1529_MODELO_DOMINIO.xlsx'
        if code == 968:
            from razync.radani import analisar_desmembramentos, consolidar_comprovantes_sispag
            from razync.bradesco_radani import processar_extrato_bradesco_radani
            groups = {}
            for bank, label in [('itau','Itaú'),('bradesco','Bradesco')]:
                frames = []
                for filename, content in roles.get(bank, []):
                    frame = pd.DataFrame(processar_extrato_bradesco_radani(content)[0], columns=COLUNAS) if bank == 'bradesco' else pd.DataFrame(engine._radani_cache_extrato_pdf(content, filename))
                    frames.append(frame)
                if not frames:
                    continue
                frame = pd.concat(frames, ignore_index=True)
                frame['DATA'] = pd.to_datetime(frame['DATA'], dayfirst=True, errors='coerce')
                frame = frame.dropna(subset=['DATA'])
                if frame.empty:
                    raise ValueError(f'Nenhum lançamento válido no {label}.')
                receipts = consolidar_comprovantes_sispag(roles['sispag'], frame['DATA'].min().isoformat(), frame['DATA'].max().isoformat()) if bank == 'itau' and roles.get('sispag') else pd.DataFrame()
                analysis = analisar_desmembramentos(frame, label, receipts)
                groups[label] = {'principal': filter_frame(analysis.organizado, options), 'retirados': pd.DataFrame()}
            if not groups:
                raise ValueError('Envie ao menos um extrato Itaú ou Bradesco.')
            return engine.gerar_excel_nova_geracao(groups, _template_bytes()), 'RADANI_968_MODELO_DOMINIO.xlsx'
        return workflow_modelo(code, roles, options)


def package(reports):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in reports.items():
            archive.writestr(name, content)
    return output.getvalue()


def diagnostics(code, roles, options):
    """Retain the original processors' review tables outside the import workbook."""
    with engine.processing_context(slug(code)):
        if code == 1248:
            from razync.rgr_1248 import processar_rgr
            _, table, unused, expenses, summary = processar_rgr(roles['extrato'][0][1], roles['movimentos'][0][1])
            return {'Boletos recebidos':table,'Boletos não vinculados':unused,'Saídas não vinculadas':expenses,'Resumo':pd.DataFrame([summary])}
        if code == 285:
            from razync.lcarlos import processar_planilhas_lcarlos
            _, table, summary = processar_planilhas_lcarlos(roles['jaguar'][0][1],roles['entradas'][0][1])
            return {'Conciliação Jaguar':table,'Resumo':pd.DataFrame([summary])}
        if code == 1211:
            from razync.gz_1211 import processar_gz
            _, table, unused, summary = processar_gz(roles['extrato'][0][1],roles['boletos'][0][1])
            return {'Boletos x extrato':table,'Boletos não utilizados':unused,'Resumo':pd.DataFrame([summary])}
        if code == 1402 and roles.get('extrato'):
            from razync.vgv_1402 import processar_vgv
            table, statement_frame, missing, summary = processar_vgv(roles['planilha'][0][1],roles['extrato'][0][1])
            return {'Caixa x BTG':table,'Extrato BTG':statement_frame,'Sem planilha':missing,'Resumo':pd.DataFrame([summary])}
        if code == 968:
            from razync.radani import analisar_desmembramentos,consolidar_comprovantes_sispag
            tables = {}
            for bank,label in [('itau','Itaú'),('bradesco','Bradesco')]:
                parts = [statement(code,bank,content,name) for name,content in roles.get(bank,[])]
                if not parts:
                    continue
                frame = pd.concat(parts,ignore_index=True)
                frame['DATA'] = pd.to_datetime(frame['DATA'],dayfirst=True,errors='coerce')
                receipts = consolidar_comprovantes_sispag(roles['sispag'],frame['DATA'].min().isoformat(),frame['DATA'].max().isoformat()) if bank == 'itau' and roles.get('sispag') else pd.DataFrame()
                result = analisar_desmembramentos(frame,label,receipts)
                tables[f'Revisões {label}'] = result.revisoes
                tables[f'Detalhamentos {label}'] = result.detalhamentos
                tables[f'Extrato original {label}'] = frame
            return tables
        if code == 1408:
            _, _, summary = _workflow_1408(roles)
            warnings = list(summary.get('avisos_francesinhas') or [])
            summary_table = dict(summary)
            summary_table.pop('avisos_francesinhas', None)
            tables = {'Resumo extrato 1408': pd.DataFrame([summary_table])}
            if warnings:
                tables['Avisos francesinhas 1408'] = pd.DataFrame({'AVISO': warnings})
            return tables
        return {}


def workflow_reports(code, roles, options):
    if code == 242:
        return eletro_reports(code,roles,options)
    content,name = workflow(code,roles,options)
    reports = {name:content}
    tables = diagnostics(code,roles,options)
    if tables:
        buffer=io.BytesIO()
        with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
            for title,frame in tables.items():
                frame.to_excel(writer,sheet_name=title[:31],index=False)
        reports[f'RAZYNC_{code}_CONFERENCIAS.xlsx']=buffer.getvalue()
    return reports


def francesinhas(code, uploads, data_inicial='', data_final=''):
    from razync.eletro_forte_francesinhas import processar_zip_francesinhas, gerar_excel_francesinhas
    frames, notices = [], []
    for _, content in uploads:
        frame, warnings = processar_zip_francesinhas(content, '512' if code == 1408 else None)
        frames.append(frame); notices.extend(warnings)
    frame = pd.concat(frames, ignore_index=True)
    frame = filter_frame(frame, {'data_inicial': data_inicial, 'data_final': data_final})
    if frame.empty:
        raise ValueError('Nenhuma liquidação foi encontrada no período informado.')
    book = gerar_excel_francesinhas(_template_bytes(), frame, (('512', 'Francesinhas - Itau 512'),) if code == 1408 else None)
    return book, {'lancamentos': len(frame), 'avisos': notices}

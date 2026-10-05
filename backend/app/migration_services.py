"""Web orchestration of the original business rules, without Streamlit UI."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

import pandas as pd
from app import engine
from app.advanced import append_dataframe_sheets
from app.excel import _template_bytes, gerar_modelo_abas
from app.registry import CAPABILITIES

COLUNAS = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
SLUGS = {3: 'autokraft_industrial', 178: 'autokraft_projetos', 343: 'isa',
         242: 'eletro_forte', 1408: 'eletro_forte_filial_1408',
         266: 'nova_geracao_matriz', 1396: 'nova_geracao_filial',
         285: 'lcarlos', 968: 'radani', 1000: 'accede_automacao',
         1001: 'accede_equipamentos', 1096: 'up_pack', 1211: 'gz_1211',
         1402: 'vgv_1402', 1529: 'dias_pereira', 47: 'crj_47',
         154: 'rm_postais_154', 625: 'valean_625', 626: 'valean_626',
         841: 'lucrativite_841', 912: 'vital_safety_912', 964: 'willians_964',
         88: 'hw_88', 969: 'engekraft_969', 1208: 'kairos_1208',
         1530: 'dias_pereira_1530', 1532: 'maria_narbutis_1532'}


def slug(code):
    return SLUGS.get(int(code), f'empresa_{code}')


def accounts(code):
    banks = dict(CAPABILITIES.get(int(code), {}).get('banks', {}))
    if int(code) == 242:
        return {'bb': '8', 'itau_508': '508', 'itau_509': '509'}
    if int(code) == 1408:
        return {'itau_512': '512'}
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


def statement(code, bank, content, filename):
    """Use specialized original readers; never mask a validation failure."""
    bank = str(bank).strip().casefold()
    with engine.processing_context(slug(code)):
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
            return processar_extrato_bradesco_radani(content)[0]
        if code == 285 and bank == 'santander':
            from razync.santander_statement import processar_extrato_santander_empresarial_texto
            text = '\n'.join(p.extract_text() or '' for p in engine.PdfReader(io.BytesIO(content)).pages)
            return pd.DataFrame(processar_extrato_santander_empresarial_texto(text), columns=COLUNAS)
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
        account = CAPABILITIES.get(code, {}).get('banks', {}).get(bank) if code in {242, 1408} else None
        main, excluded, _ = engine.ler_planilha_organizada_conferencia(model, real_bank, account)
        main, excluded = filter_frame(main, options), filter_frame(excluded, options)
        if main.empty:
            raise ValueError('Nenhum lançamento do banco/conta selecionado foi encontrado no Modelo Domínio.')
        frames = [statement(code, bank, content, filename) for filename, content in statements]
        movements = filter_frame(pd.concat(frames, ignore_index=True), options)
        daily, missing, extra, ignored = engine.conciliar_empresa_com_extrato(main, movements, excluded)
        summary = {'ok': missing.empty and extra.empty, 'planilha': len(main),
                   'extrato': len(movements), 'conferidos': len(main) - len(extra),
                   'faltando_planilha': len(missing), 'a_mais_planilha': len(extra),
                   'ignorados': len(ignored)}
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
    from app.advanced import workflow_modelo
    with engine.processing_context(slug(code)):
        if code == 1408 and roles.get('extrato'):
            from razync.eletro_forte_filial_1408 import montar_modelo_1408
            from razync.eletro_forte_francesinhas import processar_zip_francesinhas
            movements = pd.concat([statement(code, 'itau', content, name) for name, content in roles['extrato']], ignore_index=True)
            receipts = roles.get('recebidos', [(None,None)])[0][1]
            parts = [processar_zip_francesinhas(content, '512')[0] for _,content in roles.get('francesinhas',[])]
            details = pd.concat(parts,ignore_index=True) if parts else None
            frame, summary = montar_modelo_1408(movements.to_dict('records'), receipts, int(options.get('ano') or datetime.now().year), details)
            book = engine.gerar_excel_modelo_dominio(filter_frame(frame,options))
            return book, 'ELETRO_FORTE_1408_MODELO_DOMINIO.xlsx'
        if code in {242, 1408} and any(roles.get(name) for name in ('despesas', 'fornecedores', 'recebidos')):
            reports = eletro_reports(code, roles, options)
            key = f'ELETRO_FORTE_{code}_CONSOLIDADO.xlsx'
            return reports[key], key
        if code in {3, 178, 343}:
            maps = roles.get('mapa', [])
            if not maps:
                raise ValueError('Envie o mapa bancário.')
            groups = {}
            allowed = options.get('bancos') or ['Itaú', 'Daycoval']
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
            parsers = {'Itaú': engine.processar_nova_geracao_itau, 'Bradesco': engine.processar_nova_geracao_bradesco, 'Fibra': engine.processar_nova_geracao_fibra} if code == 266 else {'Itaú': engine.processar_nova_geracao_filial_itau, 'Bradesco': engine.processar_nova_geracao_filial_bradesco}
            data = {}
            errors = []
            for bank, parser in parsers.items():
                if options.get('bancos') is not None and bank not in options['bancos']:
                    continue
                principal, removed = [], []
                for _, content in uploads:
                    try:
                        main, excluded = parser(content)
                        principal.append(filter_frame(main, options)); removed.append(filter_frame(excluded, options) if not excluded.empty else excluded)
                    except ValueError as exc:
                        if options.get('bancos') is not None:
                            raise ValueError(f'{bank}: {exc}') from exc
                        errors.append(f'{bank}: {exc}')
                if principal:
                    data[bank] = {'principal': pd.concat(principal, ignore_index=True).sort_values('DATA',kind='stable'), 'retirados': pd.concat(removed, ignore_index=True).sort_values('DATA',kind='stable')}
            if not data:
                raise ValueError('; '.join(errors))
            return engine.gerar_excel_nova_geracao(data, _template_bytes(), prefixar_historicos=False), f'RAZYNC_{code}_MODELO_DOMINIO.xlsx'
        if code in {1000, 1001}:
            data = {}
            for bank in ('itau', 'sicredi'):
                if roles.get(bank):
                    frames = [engine.processar_planilha_accede_sig(content, bank, slug(code)) for _, content in roles[bank]]
                    data[bank.title()] = {'principal': filter_frame(pd.concat(frames, ignore_index=True), options), 'retirados': pd.DataFrame()}
            if not data:
                raise ValueError('Envie a planilha SIG do Itaú e/ou Sicredi.')
            return engine.gerar_excel_nova_geracao(data, _template_bytes()), f'ACCEDE_{code}_MODELO_DOMINIO.xlsx'
        # Existing modular processors remain intact. Replace only universal readers
        # and rewritten SIG/map functions with their original implementations.
        if code == 285:
            from razync.lcarlos import processar_planilhas_lcarlos
            if not roles.get('jaguar') or not roles.get('entradas'):
                raise ValueError('Envie Jaguar e Entradas detalhadas.')
            frame, _, _ = processar_planilhas_lcarlos(roles['jaguar'][0][1], roles['entradas'][0][1])
            return engine.gerar_excel_modelo_dominio(frame), 'LCARLOS_285_MODELO_DOMINIO.xlsx'
        if code == 1402:
            from razync.vgv_1402 import ler_caixa_vgv
            if not roles.get('planilha'):
                raise ValueError('Envie a planilha Caixa VGV. O extrato é opcional para conferência.')
            return engine.gerar_excel_modelo_dominio(ler_caixa_vgv(roles['planilha'][0][1])[COLUNAS]), 'VGV_1402_MODELO_DOMINIO.xlsx'
        if code == 1211:
            from razync.gz_1211 import processar_gz, gerar_modelo_dominio_gz
            if not roles.get('extrato') or not roles.get('boletos'):
                raise ValueError('Envie Extrato Itaú e Boletos liquidados em PDF.')
            frame, _, _, _ = processar_gz(roles['extrato'][0][1], roles['boletos'][0][1])
            return gerar_modelo_dominio_gz(frame, _template_bytes()), 'GZ_1211_MODELO_DOMINIO.xlsx'
        if code == 1096:
            from razync.up_pack import processar_planilha_up_pack
            groups = {}
            for bank in ('santander', 'sicredi'):
                if roles.get(bank):
                    frames = [processar_planilha_up_pack(content, bank) for _, content in roles[bank]]
                    groups[bank.title()] = {'principal': filter_frame(pd.concat(frames, ignore_index=True), options), 'retirados': pd.DataFrame()}
            if not groups:
                raise ValueError('Envie SIG Santander e/ou Sicredi.')
            return engine.gerar_excel_nova_geracao(groups, _template_bytes()), 'UP_PACK_1096_MODELO_DOMINIO.xlsx'
        if code == 1529:
            from razync.nibo import processar_extrato_nibo_pdf
            frames = []
            for bank, description in [('itau', 'BANCO ITAÚ'), ('banco_brasil', 'BANCO DO BRASIL')]:
                for _, content in roles.get(bank, []):
                    frame = processar_extrato_nibo_pdf(content)[COLUNAS].copy()
                    frame['DESCRIÇÃO'] = description
                    frames.append(frame)
            if not frames:
                raise ValueError('Envie PDF Nibo do Itaú e/ou Banco do Brasil.')
            frame = pd.concat(frames, ignore_index=True)
            frame['_DATA_ORDEM'] = pd.to_datetime(frame['DATA'], dayfirst=True, errors='coerce')
            frame = frame.sort_values(['_DATA_ORDEM','DESCRIÇÃO'], kind='stable').drop(columns=['_DATA_ORDEM']).reset_index(drop=True)
            return engine.gerar_excel_modelo_dominio(frame), 'DIAS_PEREIRA_1529_MODELO_DOMINIO.xlsx'
        if code == 968:
            from razync.radani import analisar_desmembramentos, consolidar_comprovantes_sispag
            from razync.bradesco_radani import processar_extrato_bradesco_radani
            groups = {}
            for bank, label in [('itau','Itaú'),('bradesco','Bradesco')]:
                frames = []
                for filename, content in roles.get(bank, []):
                    frame = processar_extrato_bradesco_radani(content)[0] if bank == 'bradesco' else pd.DataFrame(engine._radani_cache_extrato_pdf(content, filename))
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
                groups[label] = {'principal': analysis.organizado, 'retirados': pd.DataFrame()}
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
        if code == 1408 and roles.get('extrato'):
            from razync.eletro_forte_filial_1408 import montar_modelo_1408
            from razync.eletro_forte_francesinhas import processar_zip_francesinhas
            parts = [statement(code,'itau',content,name) for name,content in roles['extrato']]
            details = [processar_zip_francesinhas(content,'512')[0] for _,content in roles.get('francesinhas',[])]
            _,summary = montar_modelo_1408(pd.concat(parts,ignore_index=True).to_dict('records'),roles.get('recebidos',[(None,None)])[0][1],int(options.get('ano') or datetime.now().year),pd.concat(details,ignore_index=True) if details else None)
            return {'Resumo extrato 1408':pd.DataFrame([summary])}
        return {}


def workflow_reports(code, roles, options):
    if code in {242,1408} and not roles.get('extrato'):
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


def francesinhas(code, uploads):
    from razync.eletro_forte_francesinhas import processar_zip_francesinhas, gerar_excel_francesinhas
    frames, notices = [], []
    for _, content in uploads:
        frame, warnings = processar_zip_francesinhas(content, '512' if code == 1408 else None)
        frames.append(frame); notices.extend(warnings)
    frame = pd.concat(frames, ignore_index=True)
    book = gerar_excel_francesinhas(_template_bytes(), frame, (('512', 'Francesinhas - Itau 512'),) if code == 1408 else None)
    return book, {'lancamentos': len(frame), 'avisos': notices}

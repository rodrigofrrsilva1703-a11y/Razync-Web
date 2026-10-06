"""Business rules extracted from Razync; UI and cache decorators removed.

Source provenance is recorded in resources/engine_manifest.json. Request state
is isolated by ContextVar; importing this module never executes Streamlit pages.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
import base64

request_state = ContextVar('razync_request_state')
TEMPLATE = Path(__file__).resolve().parents[1] / 'resources' / 'Modelo dominio.xlsx'

@contextmanager
def processing_context(company=''):
    state = {'empresa_organizador': company, 'warnings': []}
    token = request_state.set(state)
    try:
        yield state
    finally:
        request_state.reset(token)

def record_warning(message):
    request_state.get()['warnings'].append(str(message))

import pandas as pd
import re
import struct
import calendar
import io
import os
import tempfile
import time
import unicodedata
import json
import hashlib
import hmac
import zipfile
import difflib
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from pypdf import PdfReader
from razync.companies import CONFIGURACOES_AUTOKRAFT, CONFIGURACOES_ACCEDE
from razync.company_catalog import EMPRESAS, EMPRESAS_POR_REGIME, EMPRESAS_POR_CHAVE
from razync.nibo import processar_extrato_nibo_pdf
from razync.history import padronizar_historicos_modelo, prefixar_historico_movimento
from razync.accede_1000 import (
    aplicar_regras_accede_1000, identificar_conta_folha_accede_1000,
)
from razync.bank_validation import diagnostico_pdf_sem_lancamentos, validar_fechamento_saldo
from razync.bb_statement import parece_extrato_bb_autorizavel, processar_extrato_bb_autorizavel
from razync.task_deadlines import calcular_prioridade_empresa, obter_competencia_operacional
from razync.task_center import classificar_tarefa, ordenar_tarefas, resumir_tarefas
from razync.lcarlos import processar_planilhas_lcarlos
from razync.up_pack import identificar_banco_up_pack, processar_planilha_up_pack
from razync.santander_statement import (parece_extrato_santander_empresarial, processar_extrato_santander_empresarial_texto)
from razync.radani import analisar_desmembramentos, consolidar_comprovantes_sispag
from razync.bradesco_radani import processar_extrato_bradesco_radani
from razync.eletro_forte import (
    CONTAS_ELETRO_FORTE, gerar_consolidado_bancos_eletro_forte,
    gerar_modelo_dominio_eletro_forte, inferir_ano_recebidos,
    processar_despesas, processar_fornecedores, processar_recebidos,
)
from razync.eletro_forte_francesinhas import (
    corrigir_datas_com_francesinhas, gerar_excel_francesinhas,
    processar_zip_francesinhas,
)
from razync.eletro_forte_filial_1408 import montar_modelo_1408
from razync.gz_1211 import (
    CONTA_ITAU_GZ, gerar_modelo_dominio_gz, processar_gz,
)
from razync.engekraft_969 import (
    CONTA_ITAU_969, gerar_modelo_dominio_engekraft_969,
    processar_extrato_engekraft_969, processar_extrato_itau_modelo,
)
from razync.vgv_1402 import (
    COLUNAS_MODELO as COLUNAS_MODELO_VGV,
    ler_caixa_vgv,
    processar_extrato_btg_vgv,
    processar_vgv,
)
from razync.hw_88 import (
    COLUNAS_MODELO as COLUNAS_MODELO_HW88,
    processar_extrato_hw88,
)

def _radani_cache_extrato_pdf(conteudo: bytes, nome_arquivo: str):
    caminho = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(conteudo)
            caminho = tmp.name
        return processar_arquivo_pdf(caminho, nome_arquivo)
    finally:
        if caminho and os.path.exists(caminho):
            os.unlink(caminho)

def _radani_cache_bradesco_pdf(conteudo: bytes):
    return processar_extrato_bradesco_radani(conteudo)

def _radani_cache_comprovantes(arquivos_tuple, inicio_iso: str, fim_iso: str):
    return consolidar_comprovantes_sispag(
        list(arquivos_tuple),
        pd.Timestamp(inicio_iso),
        pd.Timestamp(fim_iso),
    )

def limpar_caracteres_ilegais(val):
    if isinstance(val, str): return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', val)
    return val

def normalizar_texto(texto):
    if not isinstance(texto, str): return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn').lower()

def formatar_moeda(valor):
    try: return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except: return "R$ 0,00"

def formatar_dataframe_moeda_br(df, colunas):
    """Formata apenas a cópia exibida; os dados originais continuam numéricos."""
    exibicao = df.copy()
    for coluna in colunas:
        if coluna in exibicao.columns:
            exibicao[coluna] = exibicao[coluna].apply(
                lambda valor: formatar_moeda(valor) if pd.notna(valor) and valor != '' else ''
            )
    return exibicao

def sanitizar_dataframe(df):
    for col in df.select_dtypes(include=['object', 'string']).columns: df[col] = df[col].apply(limpar_caracteres_ilegais)
    return df

def interpretar_sinal_inteligente(historico_str, valor_num, explicit_nature=""):
    """
    Motor Inteligente Universal:
    Avalia se o lançamento é Entrada (+) ou Saída (-) com base em indicadores
    explícitos e análise semântica avançada do histórico.
    """
    val = abs(float(valor_num))
    ind = normalizar_texto(str(explicit_nature)).strip()
    ind_tokens = set(re.findall(r'[a-z]+', ind))
    h_norm = normalizar_texto(historico_str)
    
    # 1. Indicador explícito de natureza (C/D, Crédito/Débito, Entrada/Saída)
    natureza_debito = (
        ind in {'d', 'deb', 'db', 'debito', 'saida'} or
        bool(ind_tokens.intersection({'debito', 'saida', 'pagamento', 'pagto', 'emitido'}))
    )
    natureza_credito = (
        ind in {'c', 'cred', 'cr', 'credito', 'entrada'} or
        bool(ind_tokens.intersection({'credito', 'entrada', 'recebimento', 'recebido'}))
    )
    if natureza_debito:
        return -val
    if natureza_credito:
        return val
        
    # 2. Se o valor já veio negativo do arquivo original
    if valor_num < 0:
        return -val

    # 3. Indicadores inequívocos de entrada têm prioridade sobre termos como
    # "aplic" que podem aparecer no complemento de um rendimento.
    termos_entrada = [
        'pix recebido', 'ted recebida', 'ted recebido', 'recebimento',
        'recebimentos', 'rendimento', 'rendimentos', 'deposito',
        'boleto recebido', 'boletos recebidos', 'estorno cred', 'credito'
    ]
    if any(termo in h_norm for termo in termos_entrada):
        return val
        
    # 4. Análise semântica inteligente por palavras-chave de saída no histórico
    termos_saida = [
        'ted emitido', 'ted emi do', 'pix env', 'pix enviado', 'ted env', 'doc env', 'pagto', 'pagamento', 
        'tarifa', 'manut', 'cobranca', 'debito', 'saque', 'compra', 'cartao', 
        'transferencia env', 'transf env', 'cpfl', 'darf', 'gps', 'iss', 'imposto',
        'aplicacao', 'aplic', 'investimento', 'estorno deb', 'saida', 'db', 'sispag',
        'concessionaria', 'tributo', 'boleto pago', 'tarifa emissao', 'tarifa emissao de ted', 'emitido'
    ]
    
    if any(termo in h_norm for termo in termos_saida):
        return -val
        
    # Padrão para recebimentos, pix recebido, ted recebida, rendimentos, etc.
    return val

def limpar_valor_monetario(v_val):
    if pd.isna(v_val) or v_val == '': return 0.0
    if isinstance(v_val, (int, float)): return float(v_val)
    
    s = str(v_val).strip().upper()
    is_negative = False
    if '-' in s or s.endswith('D') or s.endswith('SAÍDA') or s.endswith('SAIDA') or re.search(r'\(\s*[\d\.,]+\s*\)', s):
        is_negative = True
        
    s = re.sub(r'[^\d,\.]', '', s)
    if not s: return 0.0
    
    if ',' in s and '.' in s:
        last_dot, last_comma = s.rfind('.'), s.rfind(',')
        s = s.replace('.', '').replace(',', '.') if last_comma > last_dot else s.replace(',', '')
    elif ',' in s: 
        s = s.replace(',', '.')
        
    try: 
        val = float(s)
        return -abs(val) if is_negative else abs(val)
    except: 
        return 0.0

def identificar_banco_inteligente(texto_conteudo, filename_str=""):
    # O nome do arquivo tem prioridade para impedir que fornecedores citados no
    # histórico sejam confundidos com o banco emissor do extrato.
    nome = normalizar_texto(str(filename_str)).upper()
    cabecalho = normalizar_texto(str(texto_conteudo)[:6000]).upper()
    digitos_nome = re.sub(r'\D', '', str(filename_str))
    digitos_cabecalho = re.sub(r'\D', '', str(texto_conteudo)[:6000])

    # Contas Itaú da Eletro Forte. A identificação explícita pelo nome deve
    # ocorrer antes de analisar códigos de bancos citados nos lançamentos.
    if any(conta in digitos_nome for conta in ['105318', '181537']):
        return 'BANCO ITAU'

    # Os arquivos do Banco do Brasil costumam ser nomeados apenas como "BB" e
    # o PDF Autorizável não imprime o nome completo do banco na camada de texto.
    # Sem estas assinaturas, um código 341 de uma TED dentro do extrato fazia o
    # documento inteiro ser confundido com Itaú.
    if re.search(r'(^|[^A-Z0-9])BB([^A-Z0-9]|$)', nome):
        return 'BANCO DO BRASIL'
    if (
        'EXTRATO DE CONTA CORRENTE - AUTORIZAVEL' in cabecalho
        and 'CLIENTE - CONTA ATUAL' in cabecalho
    ):
        return 'BANCO DO BRASIL'

    # As empresas também nomeiam os extratos apenas com agência/conta. Essa
    # identificação não depende do mês ou do ano presentes no nome do arquivo.
    contas_nova_geracao = [
        ('995495', 'BANCO ITAU'),
        ('4519906', 'BANCO BRADESCO'),
        ('6739471', 'BANCO FIBRA'),
    ]
    for conta, banco in contas_nova_geracao:
        if conta in digitos_nome:
            return banco

    bancos = [
        (['BTG', 'PACTUAL'], 'BANCO BTG'),
        (['ITAU'], 'BANCO ITAU'),
        (['BRADESCO'], 'BANCO BRADESCO'),
        (['FIBRA'], 'BANCO FIBRA'),
        (['DAYCOVAL', 'DAYCONNECT'], 'BANCO DAYCOVAL'),
        (['SANTANDER'], 'BANCO SANTANDER'),
        (['SICOOB'], 'SICOOB'),
        (['SICREDI'], 'SICREDI'),
        (['NUBANK', 'NU PAGAMENTO'], 'NUBANK'),
        (['CAIXA ECONOMICA'], 'CAIXA ECONOMICA'),
        (['BANCO DO BRASIL'], 'BANCO DO BRASIL'),
        (['BANCO INTER'], 'BANCO INTER'),
    ]
    for termos, banco in bancos:
        if any(termo in nome for termo in termos):
            return banco
    for termos, banco in bancos:
        if any(termo in cabecalho for termo in termos):
            return banco
    for conta, banco in contas_nova_geracao:
        if conta in digitos_cabecalho:
            return banco

    # Itaú Empresas: em alguns PDFs o logotipo é imagem e a palavra "Itaú"
    # não existe na camada de texto. Identificamos então pela assinatura estrutural
    # exclusiva do extrato detalhado, sem depender do nome do arquivo.
    assinatura_itau = (
        (
            'LANCAMENTOS DO PERIODO' in cabecalho
            and 'RAZAO SOCIAL' in cabecalho
            and 'CNPJ/CPF' in cabecalho
            and 'VALOR (R$)' in cabecalho
            and 'SALDO (R$)' in cabecalho
            and ('LIMITE DA CONTA' in cabecalho or 'SALDO TOTAL' in cabecalho)
        )
        or (
            'LANCAMENTOS PERIODO' in cabecalho
            and 'CONTA CORRENTE' in cabecalho
            and 'AG/ORIGEM' in cabecalho
            and 'VALOR (R$)' in cabecalho
            and 'SALDO (R$)' in cabecalho
            and ('SISPAG' in cabecalho or 'APLIC AUT' in cabecalho)
        )
    )
    if assinatura_itau:
        return 'BANCO ITAU'

    if '58.616.418' in str(texto_conteudo)[:6000]: return 'BANCO FIBRA'
    if re.search(r'\b0?341\b', cabecalho): return 'BANCO ITAU'
    return "BANCO CONTA CORRENTE"

def processar_ofx(file_bytes, filename):
    lancamentos = []
    texto = ""
    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
        try: texto = file_bytes.decode(enc); break
        except: pass
    if not texto: texto = file_bytes.decode('latin1', errors='ignore')
    
    banco_detectado = identificar_banco_inteligente(texto, filename)
    raw_blocks = re.split(r'<STMTTRN>', texto, flags=re.IGNORECASE)
    
    for block in raw_blocks[1:]:
        block_clean = re.split(r'</STMTTRN>|</BANKTRANLIST>', block, flags=re.IGNORECASE)[0]
        match_date = re.search(r'<DTPOSTED>\s*(\d{4}[-/\.]?\d{2}[-/\.]?\d{2}|\d{8})', block_clean, re.IGNORECASE)
        match_amt = re.search(r'<TRNAMT>\s*([\+\-]?[\d\.\,]+)', block_clean, re.IGNORECASE)
        match_memo = re.search(r'<(?:MEMO|NAME|PAYEE)>\s*(.*?)(?:\r|\n|<|$)', block_clean, re.IGNORECASE)
        match_type = re.search(r'<TRNTYPE>\s*([A-Z]+)', block_clean, re.IGNORECASE)
        
        if match_date and match_amt:
            dt_s = match_date.group(1).replace('-', '').replace('/', '').replace('.', '')
            if len(dt_s) >= 8: data_fmt = f"{dt_s[6:8]}/{dt_s[4:6]}/{dt_s[:4]}"
            else: continue
            
            valor_bruto = limpar_valor_monetario(match_amt.group(1).strip())
            trntype = match_type.group(1).upper() if match_type else ""
            historico = limpar_caracteres_ilegais(match_memo.group(1).strip().replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')) if match_memo else "TRANSACAO OFX"
            
            if 'SALDO' in historico.upper(): continue
            
            if trntype in ['DEBIT', 'PAYMENT', 'FEE']:
                valor_float = -abs(valor_bruto)
            elif trntype in ['CREDIT', 'DEP', 'DIRECTDEP']:
                valor_float = abs(valor_bruto)
            else:
                valor_float = interpretar_sinal_inteligente(historico, valor_bruto)
                
            if valor_float != 0: 
                lancamentos.append({'DESCRIÇÃO': banco_detectado, 'DATA': data_fmt, 'VALOR': valor_float, 'DÉBITO': '', 'CRÉDITO': '', 'HISTÓRICO': historico})
    return lancamentos

def processar_planilha_universal(file_bytes, filename):
    lancamentos, df = [], None
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.xlsx', '.xls']:
        try:
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            for sheet in xls.sheet_names:
                df_temp = pd.read_excel(xls, sheet_name=sheet, dtype=str)
                if df_temp is not None and not df_temp.empty and df_temp.shape[1] > 1:
                    df = df_temp
                    break
        except Exception:
            try: dfs = pd.read_html(io.BytesIO(file_bytes))
            except Exception: pass
            if dfs: df = dfs[0]
    if df is None:
        for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1', 'utf-16']:
            for sep in [';', ',', '\t', '|']:
                try: df_temp = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, dtype=str)
                except Exception: pass
                if df_temp is not None and df_temp.shape[1] > 1: df = df_temp; break
            if df is not None: break
    if df is None or df.empty: return []
    
    texto_amostra = " ".join([str(v) for row in df.head(10).values for v in row if pd.notna(v)])
    banco_detectado = identificar_banco_inteligente(texto_amostra, filename)
    
    header_idx = None
    for idx, row in df.iterrows():
        row_str = normalizar_texto(" ".join([str(v) for v in row.values if pd.notna(v)]))
        if ('data' in row_str or 'dt' in row_str) and ('valor' in row_str or 'credito' in row_str or 'debito' in row_str or 'lancamento' in row_str or 'historico' in row_str):
            header_idx = idx; break
            
    if header_idx is not None:
        df.columns = [str(v).strip() for v in df.iloc[header_idx].values]
        df = df.iloc[header_idx+1:].copy()
    
    cols_map = {c: normalizar_texto(c) for c in df.columns}
    col_data = next((c for c, nc in cols_map.items() if any(p in nc for p in ['data', 'dt', 'date', 'dia'])), None)
    col_hist = next((c for c, nc in cols_map.items() if any(p in nc for p in ['lancamento', 'historico', 'hist', 'razao social', 'descric', 'detalhe', 'memo'])), None)
    col_val = next((c for c, nc in cols_map.items() if any(p in nc for p in ['valor', 'val', 'monto', 'amount'])), None)
    col_cred = next((c for c, nc in cols_map.items() if any(p in nc for p in ['credito', 'credit', 'entrada', 'vlr_cred', 'crd'])), None)
    col_deb = next((c for c, nc in cols_map.items() if any(p in nc for p in ['debito', 'debit', 'saida', 'vlr_deb', 'deb'])), None)
    col_tipo = next((c for c, nc in cols_map.items() if any(p in nc for p in ['tipo', 'natureza', 'operacao', 'c/d'])), None)

    if not col_data: return []
    
    for _, row in df.iterrows():
        dt_raw = str(row[col_data]).strip() if pd.notna(row[col_data]) else ''
        if dt_raw.upper() in ['TOTAL', 'ÚLTIMOS LANÇAMENTOS', 'ULTIMOS LANCAMENTOS', 'SALDOS INVEST FÁCIL / PLUS', 'NAN', 'SALDO ANTERIOR']:
            if dt_raw.upper() == 'TOTAL': break
            continue
            
        match_dt = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', dt_raw)
        if not match_dt: continue
        dt_fmt = match_dt.group(1).replace('-', '/')
        
        hist_raw = limpar_caracteres_ilegais(str(row[col_hist]).strip()) if col_hist and pd.notna(row[col_hist]) else 'MOVIMENTO BANCARIO'
        hist_fmt = hist_raw if hist_raw.lower() != 'nan' else 'MOVIMENTO BANCARIO'
        if any(term in hist_fmt.upper() for term in ['SALDO', 'SUBTOTAL', 'TOTAL', 'TRANSPORTAR']): continue
        
        valor_float = 0.0
        
        if col_cred or col_deb:
            v_cred = limpar_valor_monetario(row[col_cred]) if col_cred and pd.notna(row[col_cred]) else 0.0
            v_deb = limpar_valor_monetario(row[col_deb]) if col_deb and pd.notna(row[col_deb]) else 0.0
            if v_cred != 0: valor_float = abs(v_cred)
            elif v_deb != 0: valor_float = -abs(v_deb)
        elif col_val and pd.notna(row[col_val]):
            val_cru = limpar_valor_monetario(row[col_val])
            tipo_str = str(row[col_tipo]).strip() if col_tipo and pd.notna(row[col_tipo]) else ""
            valor_float = interpretar_sinal_inteligente(hist_fmt, val_cru, tipo_str)

        if valor_float != 0:
            lancamentos.append({'DESCRIÇÃO': banco_detectado, 'DATA': dt_fmt, 'VALOR': valor_float, 'DÉBITO': '', 'CRÉDITO': '', 'HISTÓRICO': hist_fmt})
    return lancamentos

def extrair_periodo_extrato(caminho_pdf):
    try:
        reader = PdfReader(caminho_pdf, strict=False)
        texto = "".join([p.extract_text() for p in reader.pages[:3]])
        datas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
        if len(datas) >= 2: return datetime.strptime(datas[0], '%d/%m/%Y'), datetime.strptime(datas[1], '%d/%m/%Y')
    except: pass
    return None, None

def processar_pdf_layout_universal(reader, banco_identificado):
    """
    Analisa tabelas bancárias pela estrutura do próprio PDF, sem regras por banco.

    O motor combina: cabeçalhos detectados, posição das colunas, última data
    válida, sinais C/D, semântica do histórico e variação matemática do saldo.
    """
    lancamentos = []
    tabela_ativa = False
    encontrou_cabecalho = False
    data_atual = None
    saldo_anterior = None
    pos_credito = None
    pos_debito = None
    pos_valor = None
    pos_saldo = None
    historico_pendente = ""

    date_regex = re.compile(r'(?<!\d)(\d{2}/\d{2}/\d{4})(?!\d)')
    valor_regex = re.compile(
        r'(?<!\d)(?:R\$\s*)?(\(?\s*[+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2}\s*\)?\s*[CD]?)(?!\d)',
        re.IGNORECASE
    )

    def limpar_historico_linha(linha, data_linha=None):
        hist = linha
        if data_linha:
            hist = hist.replace(data_linha, ' ', 1)
        hist = valor_regex.sub(' ', hist).replace('R$', ' ')
        hist = hist.replace('Emi\x00do', 'Emitido').replace('\x00', '')
        return re.sub(r'\s+', ' ', hist).strip(' -|')

    def linha_auxiliar_valida(linha):
        norm = normalizar_texto(linha)
        if re.match(r'^\s*\d+\s*/\s*\d+\s*$', linha):
            return False
        bloqueios = [
            'extrato mensal', 'nome do usuario', 'data da operacao', 'folha ',
            'pagina ', 'sujeito a alteracoes', 'fim de relatorio', 'cnpj:',
            'agencia | conta', 'total disponivel', 'extrato de:', 'lancamento dcto',
            'lembramos que', 'movimentacao de saldo', 'sua validade restrita'
        ]
        return bool(linha.strip()) and not any(item in norm for item in bloqueios)

    parar_processamento = False
    for pagina in reader.pages:
        try:
            texto_layout = pagina.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError):
            texto_layout = pagina.extract_text() or ""

        linhas = texto_layout.splitlines()
        for indice_linha, linha in enumerate(linhas):
            norm = normalizar_texto(linha)

            # Encerra o extrato principal antes de avisos, projeções ou uma nova
            # tabela de lançamentos futuros existente no mesmo PDF.
            if lancamentos and (
                'lancamentos futuros do periodo' in norm or
                norm.startswith('aviso: os saldos acima') or
                (norm.startswith('saldo de ') and not date_regex.search(linha)) or
                norm.startswith('posicao em:')
            ):
                parar_processamento = True
                break

            # Detecta dinamicamente as colunas da tabela.
            tem_data = re.search(r'\bdata\b', norm) is not None
            tem_coluna_monetaria = any(k in norm for k in ['credito', 'debito', 'valor', 'saldo'])
            if tem_data and tem_coluna_monetaria:
                tabela_ativa = True
                encontrou_cabecalho = True
                if 'credito' in norm:
                    pos_credito = normalizar_texto(linha).find('credito')
                if 'debito' in norm:
                    pos_debito = normalizar_texto(linha).find('debito')
                if 'valor' in norm:
                    pos_valor = normalizar_texto(linha).find('valor')
                if 'saldo' in norm:
                    pos_saldo = normalizar_texto(linha).find('saldo')
                continue

            # Finaliza a primeira tabela principal antes de resumos ou outras seções.
            if tabela_ativa and lancamentos and re.match(r'^\s*total\b', norm):
                parar_processamento = True
                break

            ocorrencias = list(valor_regex.finditer(linha))
            match_data = date_regex.search(linha)
            datas_na_linha = date_regex.findall(linha)

            # PDFs sem cabeçalho ainda podem iniciar por uma linha transacional.
            if not tabela_ativa and not encontrou_cabecalho:
                if (match_data and len(datas_na_linha) == 1 and ocorrencias and
                        not any(k in norm for k in ['periodo', 'saldo', 'disponivel', 'limite'])):
                    tabela_ativa = True
                else:
                    continue

            if not tabela_ativa:
                continue

            # Saldo anterior/de abertura serve para validar matematicamente o sinal.
            if 'saldo anterior' in norm or 'saldo inicial' in norm:
                if match_data:
                    data_atual = match_data.group(1)
                if ocorrencias:
                    saldo_anterior = limpar_valor_monetario(ocorrencias[-1].group(1))
                continue

            # Linhas isoladas de saldo não são lançamentos.
            if ('saldo' in norm and not any(k in norm for k in ['rentab', 'rendimento'])):
                if ocorrencias:
                    saldo_anterior = limpar_valor_monetario(ocorrencias[-1].group(1))
                continue

            # Resumos financeiros e limites não representam movimentações.
            if any(k in norm for k in [
                'disponivel', 'limite adicional', 'bloqueado', 'c.p.m.f',
                'provisionado', 'lancamentos futuros', 'tarifas pendentes',
                'previsao encargos', 'posicao em:'
            ]):
                continue

            # Uma linha com movimento + saldo tem ao menos dois valores. Quando há
            # apenas um, o cabeçalho/posição e o histórico definem sua natureza.
            if not ocorrencias:
                # Alguns PDFs quebram um valor alto: a linha da transação termina
                # em "R$" e o número aparece sozinho na linha seguinte.
                if match_data and len(datas_na_linha) == 1 and 'R$' in linha:
                    data_atual = match_data.group(1)
                    historico_pendente = limpar_historico_linha(linha, data_atual)
                    continue
                if lancamentos and linha_auxiliar_valida(linha):
                    complemento = limpar_historico_linha(linha)
                    if complemento and not date_regex.search(complemento):
                        hist_atual = lancamentos[-1]['HISTÓRICO']
                        lancamentos[-1]['HISTÓRICO'] = re.sub(r'\s+', ' ', f"{hist_atual} {complemento}").strip()
                continue

            if match_data:
                data_atual = match_data.group(1)
            if not data_atual:
                continue

            # Valores anteriores ao último são movimento; o último é saldo quando
            # a tabela possui coluna Saldo e há mais de um valor na linha.
            tem_saldo_linha = pos_saldo is not None and len(ocorrencias) >= 2
            saldo_linha = limpar_valor_monetario(ocorrencias[-1].group(1)) if tem_saldo_linha else None
            candidatos = ocorrencias[:-1] if tem_saldo_linha else ocorrencias
            candidatos_validos = [m for m in candidatos if limpar_valor_monetario(m.group(1)) != 0]
            if not candidatos_validos:
                if saldo_linha is not None:
                    saldo_anterior = saldo_linha
                continue

            mov = candidatos_validos[0]
            token_mov = mov.group(1).strip()
            valor_bruto = limpar_valor_monetario(token_mov)
            valor_abs = abs(valor_bruto)
            natureza = ''
            if re.search(r'D\s*$', token_mov, re.IGNORECASE):
                natureza = 'D'
            elif re.search(r'C\s*$', token_mov, re.IGNORECASE):
                natureza = 'C'

            hist_linha = limpar_historico_linha(linha, match_data.group(1) if match_data else None)
            hist = re.sub(r'\s+', ' ', f"{historico_pendente} {hist_linha}").strip()
            historico_pendente = ""
            hist_norm = normalizar_texto(hist)
            if any(k in hist_norm for k in ['saldo invest', 'saldo anterior', 'saldo final', 'saldo do dia']):
                if saldo_linha is not None:
                    saldo_anterior = saldo_linha
                continue

            # Prioridade 1: sinal explícito no próprio valor.
            if valor_bruto < 0 or natureza == 'D':
                valor_final = -valor_abs
            elif natureza == 'C':
                valor_final = valor_abs
            else:
                valor_final = None

            # Prioridade 2: diferença exata entre saldo atual e saldo anterior.
            if valor_final is None and saldo_linha is not None and saldo_anterior is not None:
                diferenca = round(saldo_linha - saldo_anterior, 2)
                if abs(abs(diferenca) - valor_abs) <= 0.05:
                    valor_final = valor_abs if diferenca > 0 else -valor_abs

            # Prioridade 3: posição em colunas Débito/Crédito detectadas.
            if valor_final is None and pos_debito is not None and pos_credito is not None:
                pos_movimento = linha.find('R$', max(0, mov.start() - 4), mov.end())
                if pos_movimento < 0:
                    pos_movimento = mov.start(1)
                dist_debito = abs(pos_movimento - pos_debito)
                dist_credito = abs(pos_movimento - pos_credito)
                valor_final = -valor_abs if dist_debito < dist_credito else valor_abs

            # Prioridade 4: sinal semântico como último recurso.
            if valor_final is None:
                valor_final = interpretar_sinal_inteligente(hist, valor_bruto, natureza)

            if valor_abs != 0:
                lancamentos.append({
                    'DESCRIÇÃO': banco_identificado,
                    'DATA': data_atual,
                    'VALOR': valor_final,
                    'DÉBITO': '',
                    'CRÉDITO': '',
                    'HISTÓRICO': limpar_caracteres_ilegais(hist or 'MOVIMENTO BANCARIO')
                })

            if saldo_linha is not None:
                saldo_anterior = saldo_linha

        if parar_processamento:
            break

    return lancamentos

def extrair_valor_lancamento_pdf(texto_bloco):
    """
    Seleciona o valor da movimentação sem confundi-lo com o saldo.

    Extratos normalmente exibem o valor do lançamento antes do saldo. Esta
    função também descarta números ligados explicitamente a saldo anterior,
    saldo atual, disponível, limite e resumos semelhantes.
    """
    padrao_valor = re.compile(
        r'(?<!\d)(?:R\$\s*)?(\(?\s*[+-]?[\d\.]+,\d{2}\s*\)?\s*[CD]?)(?!\d)',
        re.IGNORECASE
    )
    ocorrencias = list(padrao_valor.finditer(texto_bloco))
    if not ocorrencias:
        return None, ""

    termos_resumo = [
        'saldo', 'disponivel', 'limite', 'bloqueado', 'provisionado',
        'saldo atual', 'saldo anterior', 'saldo final', 'saldo do dia'
    ]
    candidatos = []
    for ocorrencia in ocorrencias:
        contexto_antes = normalizar_texto(texto_bloco[max(0, ocorrencia.start() - 35):ocorrencia.start()])
        if any(termo in contexto_antes for termo in termos_resumo):
            continue
        candidatos.append(ocorrencia)

    # Se todos foram marcados como resumo, não cria um lançamento de saldo.
    if not candidatos:
        return None, ""

    # Nos formatos Valor + Saldo, Débito + Saldo ou Crédito + Saldo, o primeiro
    # valor monetário útil pertence ao lançamento e os seguintes são saldos.
    escolhido = candidatos[0]
    token = escolhido.group(1).strip()
    natureza = ""
    if re.search(r'D\s*$', token, re.IGNORECASE):
        natureza = "D"
    elif re.search(r'C\s*$', token, re.IGNORECASE):
        natureza = "C"

    return token, natureza

def processar_pdf_itau_detalhado(reader, banco_identificado):
    """Lê os formatos detalhados do Itaú Empresas sem importar linhas de saldo."""
    textos = [(pagina.extract_text() or '') for pagina in reader.pages]
    texto_total = '\n'.join(textos)
    texto_norm = normalizar_texto(texto_total)

    assinatura_moderno = (
        'lancamentos do periodo' in texto_norm
        and 'razao social' in texto_norm
        and 'valor (r$)' in texto_norm
        and 'saldo (r$)' in texto_norm
    )
    assinatura_abreviado = (
        'lancamentos periodo' in texto_norm
        and 'conta corrente' in texto_norm
        and 'ag/origem' in texto_norm
        and 'valor (r$)' in texto_norm
        and 'saldo (r$)' in texto_norm
        and ('sispag' in texto_norm or 'aplic aut' in texto_norm)
    )
    if (
        banco_identificado not in {'BANCO ITAU', 'BANCO ITAÚ'}
        and 'itau' not in texto_norm
        and not assinatura_moderno
        and not assinatura_abreviado
    ):
        return []

    termos_saldo = [
        'saldo anterior', 'saldo aplic', 'saldo aplic. aut',
        'saldo total disponivel dia', 'saldo movimentacao conta',
        'sdo aplic aut mais ap', 'saldo em conta corrente',
        'saldo da conta corrente', 'saldo disponivel sem investimentos',
        'saldo em aplicacao automatica', 'valor total em aplicacoes automaticas',
        'saldo total disponivel', 'saldo total', 'limite da conta',
        'total disponivel para uso', 'utilizado', 'disponivel',
    ]
    padrao_valor = re.compile(r'(?<!\d)([-+]?\s*\d{1,3}(?:\.\d{3})*,\d{2})(?!\d)')

    # Formato Itaú Empresas em que o PDF extrai datas como "02 / mar" e,
    # frequentemente, cola a data DEPOIS do valor: "-1.621,0002 / mar".
    # O período declarado no cabeçalho define o ano e também impede que a seção
    # de lançamentos futuros (por exemplo, abril em um extrato de março) seja lida.
    periodo_match = re.search(
        r'lancamentos\s+periodo\s*:\s*(\d{2}/\d{2}/\d{4})\s+ate\s+(\d{2}/\d{2}/\d{4})',
        texto_norm,
        re.IGNORECASE,
    )
    if assinatura_abreviado and periodo_match:
        try:
            periodo_inicio = datetime.strptime(periodo_match.group(1), '%d/%m/%Y').date()
            periodo_fim = datetime.strptime(periodo_match.group(2), '%d/%m/%Y').date()
        except ValueError:
            periodo_inicio = periodo_fim = None

        if periodo_inicio and periodo_fim:
            meses = {
                'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4,
                'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8,
                'set': 9, 'out': 10, 'nov': 11, 'dez': 12,
            }
            moeda = r'[-+]?\d{1,3}(?:\.\d{3})*,\d{2}'
            padrao_data_sufixo = re.compile(
                rf'^(?P<hist>.+?)\s+(?P<valor>{moeda})(?P<dia>\d{{2}})\s*/\s*(?P<mes>[A-Za-zÀ-ÿ#]+)$'
            )
            padrao_data_prefixo = re.compile(
                rf'^(?P<dia>\d{{2}})\s*/\s*(?P<mes>[A-Za-zÀ-ÿ#]+)\s+(?P<hist>.+?)\s+(?P<valor>{moeda})$'
            )

            def resolver_data_curta(dia_raw, mes_raw):
                mes_norm = normalizar_texto(str(mes_raw)).replace('#', '')[:3]
                numero_mes = meses.get(mes_norm)
                if not numero_mes:
                    return None
                for ano in sorted({periodo_inicio.year, periodo_fim.year}):
                    try:
                        candidato = datetime(ano, numero_mes, int(dia_raw)).date()
                    except ValueError:
                        continue
                    if periodo_inicio <= candidato <= periodo_fim:
                        return candidato
                return None

            lancamentos_abreviados = []
            for texto_pagina in textos:
                for linha_bruta in texto_pagina.splitlines():
                    linha = re.sub(r'\s+', ' ', linha_bruta).strip()
                    if not linha:
                        continue
                    correspondencia = padrao_data_sufixo.match(linha)
                    if correspondencia is None:
                        correspondencia = padrao_data_prefixo.match(linha)
                    if correspondencia is None:
                        continue

                    data_lancamento = resolver_data_curta(
                        correspondencia.group('dia'), correspondencia.group('mes')
                    )
                    if data_lancamento is None:
                        continue

                    historico = re.sub(r'\s+', ' ', correspondencia.group('hist')).strip(' -|')
                    historico_norm = normalizar_texto(historico)
                    if not historico or any(termo in historico_norm for termo in termos_saldo):
                        continue

                    valor = limpar_valor_monetario(correspondencia.group('valor'))
                    if abs(valor) < 0.005:
                        continue

                    lancamentos_abreviados.append({
                        'DESCRIÇÃO': banco_identificado if banco_identificado in {'BANCO ITAU', 'BANCO ITAÚ'} else 'BANCO ITAU',
                        'DATA': data_lancamento.strftime('%d/%m/%Y'),
                        'VALOR': valor,
                        'DÉBITO': '',
                        'CRÉDITO': '',
                        'HISTÓRICO': limpar_caracteres_ilegais(historico),
                    })

            if lancamentos_abreviados:
                return lancamentos_abreviados

    # Formato detalhado atual, com datas completas no início da linha.
    linhas_por_pagina = [
        [re.sub(r'\s+', ' ', linha).strip() for linha in texto.splitlines() if linha.strip()]
        for texto in textos
    ]
    padrao_data = re.compile(r'^(\d{2}/\d{2}/\d{4})\s+(.*)$')
    blocos = []
    atual = None

    for linhas_pagina in linhas_por_pagina:
        for linha in linhas_pagina:
            m = padrao_data.match(linha)
            if m:
                # Na quebra de página o Itaú pode repetir a mesma data para
                # continuar um lançamento cujo valor ficou na página seguinte.
                atual_sem_valor = bool(atual) and not padrao_valor.search(atual[1])
                if atual_sem_valor and atual[0] == m.group(1):
                    atual[1] += ' ' + m.group(2)
                    continue
                if atual:
                    blocos.append(atual)
                atual = [m.group(1), m.group(2)]
            elif atual:
                atual[1] += ' ' + linha
    if atual:
        blocos.append(atual)

    lancamentos = []
    for data_str, conteudo in blocos:
        conteudo_norm = normalizar_texto(conteudo)
        if any(termo in conteudo_norm for termo in termos_saldo):
            continue
        if conteudo_norm.startswith(('aviso', 'atualizado em')):
            continue

        valores = list(padrao_valor.finditer(conteudo))
        if not valores:
            continue

        valor_match = valores[-1]
        valor = limpar_valor_monetario(valor_match.group(1))
        if abs(valor) < 0.005:
            continue

        historico = (conteudo[:valor_match.start()] + ' ' + conteudo[valor_match.end():]).strip()
        historico = re.sub(r'\s+', ' ', historico).strip(' -|')
        if not historico:
            historico = 'MOVIMENTO BANCARIO'

        lancamentos.append({
            'DESCRIÇÃO': banco_identificado or 'BANCO ITAU',
            'DATA': data_str,
            'VALOR': valor,
            'DÉBITO': '',
            'CRÉDITO': '',
            'HISTÓRICO': limpar_caracteres_ilegais(historico),
        })

    return lancamentos

def processar_pdf_daycoval_detalhado(reader, banco_identificado):
    """
    Lê extratos detalhados Dayconnect/Daycoval antigos e recentes.

    Alguns PDFs preservam o texto normalmente; outros inserem espaços entre
    letras, datas e valores (ex.: ``01/ 05 T A R I F A ... - R $  7 , 3 7``).
    O parser normaliza essa fragmentação, preserva lançamentos repetidos reais,
    respeita o período declarado no extrato e usa o modo layout somente como
    fallback quando a extração textual simples não produz lançamentos.
    """
    textos_simples = [(pagina.extract_text() or '') for pagina in reader.pages]
    texto_identificacao = normalizar_texto('\n'.join(textos_simples[:2]))
    if (
        banco_identificado != 'BANCO DAYCOVAL'
        and 'daycoval' not in texto_identificacao
        and 'dayconnect' not in texto_identificacao
    ):
        return []

    padrao_data_inicio = re.compile(
        r'^\s*(\d)\s*(\d)\s*/\s*(\d)\s*(\d)\s+(.*)$'
    )
    padrao_data_completa = re.compile(
        r'(\d)\s*(\d)\s*/\s*(\d)\s*(\d)\s*/\s*(2)\s*(0)\s*(\d)\s*(\d)'
    )
    padrao_moeda = re.compile(
        r'([+-]?\s*R\s*\$\s*[+-]?\s*\d[\d\s.]*,\s*\d\s*\d)',
        re.IGNORECASE
    )

    def desfragmentar_linha(linha):
        texto = str(linha or '').replace('\xa0', ' ')
        tokens = texto.split()
        alfabeticos = [
            token for token in tokens
            if any(caractere.isalpha() for caractere in token)
        ]
        unitarios = [
            token for token in alfabeticos
            if len(re.sub(r'[^A-Za-zÀ-ÿ]', '', token)) == 1
        ]
        fragmentado = bool(alfabeticos) and (
            len(unitarios) / len(alfabeticos) >= 0.45
        )
        if fragmentado:
            # Remove somente ESPAÇO SIMPLES entre letras. Espaços duplos do PDF
            # continuam separando palavras e são colapsados apenas ao final.
            texto = re.sub(
                r'(?<=[A-Za-zÀ-ÿ]) (?=[A-Za-zÀ-ÿ])', '', texto
            )
        return re.sub(r'\s+', ' ', texto).strip()

    def converter_moeda(valor_raw):
        texto = re.sub(r'\s+', '', str(valor_raw).upper()).replace('R$', '')
        sinal = -1.0 if texto.startswith('-') else 1.0
        texto = texto.lstrip('+-').replace('.', '').replace(',', '.')
        try:
            return sinal * float(texto)
        except (TypeError, ValueError):
            return 0.0

    def extrair_data_match(match):
        dia = match.group(1) + match.group(2)
        mes = match.group(3) + match.group(4)
        ano = '20' + match.group(7) + match.group(8)
        try:
            return datetime.strptime(
                f'{dia}/{mes}/{ano}', '%d/%m/%Y'
            ).date()
        except ValueError:
            return None

    def localizar_periodo(texto_total):
        linhas = texto_total.splitlines()
        for indice, linha in enumerate(linhas):
            normalizada = normalizar_texto(desfragmentar_linha(linha))
            if 'periodo' not in normalizada:
                continue
            janela = ' '.join(linhas[indice:indice + 4])
            datas = list(padrao_data_completa.finditer(janela))
            if len(datas) >= 2:
                data_inicial = extrair_data_match(datas[0])
                data_final = extrair_data_match(datas[1])
                if data_inicial and data_final and data_inicial <= data_final:
                    return data_inicial, data_final
        return None

    def processar_fonte(texto_total):
        periodo = localizar_periodo(texto_total)
        if periodo:
            ano_referencia = periodo[0].year
        else:
            data_completa = padrao_data_completa.search(texto_total)
            data_referencia = extrair_data_match(data_completa) if data_completa else None
            ano_referencia = data_referencia.year if data_referencia else datetime.now().year

        blocos = []
        atual = None
        prefixos_fim = (
            'impressao realizada', 'central de atendimento',
            'horario de atendimento', 'sac daycoval',
            'central para deficientes', 'ouvidoria:', 'os saldos acima',
            'saldo anterior', 'extrato detalhado', 'conta corrente',
            'saldo disponivel', 'titular', 'periodo', 'agencia', 'conta ',
            'saldo atual', 'limite ', 'saldo bloqueado', 'valor bloqueado',
            'provisao de encargos', 'lancamentos futuros'
        )

        for linha_bruta in texto_total.splitlines():
            correspondencia = padrao_data_inicio.match(linha_bruta)
            if correspondencia:
                if atual:
                    blocos.append(atual)
                atual = {
                    'dia': correspondencia.group(1) + correspondencia.group(2),
                    'mes': correspondencia.group(3) + correspondencia.group(4),
                    'linhas': [correspondencia.group(5)]
                }
                continue

            if atual:
                linha_normalizada = normalizar_texto(
                    desfragmentar_linha(linha_bruta)
                )
                if (
                    any(linha_normalizada.startswith(prefixo) for prefixo in prefixos_fim)
                    or ('feira' in linha_normalizada and 'saldo:' in linha_normalizada)
                ):
                    blocos.append(atual)
                    atual = None
                    continue
                atual['linhas'].append(linha_bruta)

        if atual:
            blocos.append(atual)

        lancamentos = []
        for bloco in blocos:
            conteudo = ' '.join(bloco['linhas'])
            moedas = list(padrao_moeda.finditer(conteudo))
            if not moedas:
                continue

            # O primeiro valor monetário pertence ao lançamento. Isso evita que
            # um "Saldo Anterior" posterior contamine o último movimento da página.
            moeda = moedas[0]
            valor = converter_moeda(moeda.group(1))
            if abs(valor) < 0.005:
                continue

            historico = desfragmentar_linha(
                conteudo[:moeda.start()]
            ).strip(' -|')
            if not historico:
                continue
            historico_normalizado = normalizar_texto(historico)
            if historico_normalizado.startswith('saldo ') or 'saldo:' in historico_normalizado:
                continue

            try:
                data_lancamento = datetime(
                    ano_referencia,
                    int(bloco['mes']),
                    int(bloco['dia'])
                ).date()
            except ValueError:
                continue

            # Extratos emitidos no início do mês seguinte podem exibir um movimento
            # posterior ao período solicitado. Para conciliação, prevalece o período
            # declarado pelo próprio banco.
            if periodo and not (periodo[0] <= data_lancamento <= periodo[1]):
                continue

            lancamentos.append({
                'DESCRIÇÃO': banco_identificado or 'BANCO DAYCOVAL',
                'DATA': data_lancamento.strftime('%d/%m/%Y'),
                'VALOR': round(valor, 2),
                'DÉBITO': '',
                'CRÉDITO': '',
                'HISTÓRICO': limpar_caracteres_ilegais(historico)
            })

        return lancamentos

    # Prioriza a extração simples: é a mais fiel nos modelos recentes e nos PDFs
    # antigos com texto fragmentado. O layout fica como fallback real, não é somado,
    # portanto lançamentos legítimos repetidos no mesmo dia/valor são preservados.
    texto_simples_total = '\n'.join(textos_simples)
    lancamentos_simples = processar_fonte(texto_simples_total)
    if lancamentos_simples:
        return lancamentos_simples

    textos_layout = []
    for pagina, texto_simples in zip(reader.pages, textos_simples):
        try:
            texto_layout = pagina.extract_text(extraction_mode='layout') or texto_simples
        except (TypeError, ValueError):
            texto_layout = texto_simples
        textos_layout.append(texto_layout)

    return processar_fonte('\n'.join(textos_layout))

def processar_pdf_fibra_extrato(reader, banco_identificado='BANCO FIBRA'):
    """Lê o extrato de C/C do Banco Fibra sem depender do layout posicional do PDF."""
    texto_total = '\n'.join((pagina.extract_text() or '') for pagina in reader.pages)
    texto_norm = normalizar_texto(texto_total)
    if banco_identificado != 'BANCO FIBRA' and 'banco fibra' not in texto_norm:
        return []
    if 'extrato de c/c para simples conferencia' not in texto_norm:
        return []

    linhas = [
        re.sub(r'\s+', ' ', linha.replace('Emi\x00do', 'Emitido').replace('emi\x00do', 'emitido').replace('\x00', '')).strip()
        for linha in texto_total.splitlines() if linha.strip()
    ]
    regex_data = re.compile(r'^(\d{2}/\d{2}/\d{4})\s+(.*)$')
    regex_valor = re.compile(r'R\$\s*([\d.]+,\d{2})|(?<!\d)([\d.]+,\d{2})(?!\d)')

    blocos = []
    atual = None
    for linha in linhas:
        norm = normalizar_texto(linha)
        if norm.startswith(('posicao em:', 'saldo atual:', '= disponivel:', 'saldo liquido:',
                            'lancamentos futuros:', 'tarifas pendentes:', 'previsao encargos:',
                            '= saldo provisionado:', 'fim de relatorio')):
            if atual:
                blocos.append(atual)
                atual = None
            break
        if norm.startswith('saldo '):
            if atual:
                blocos.append(atual)
                atual = None
            continue
        if norm.startswith(('pagina ', 'sujeito a alteracoes')):
            continue

        m = regex_data.match(linha)
        if m:
            if atual:
                blocos.append(atual)
            atual = {'data': m.group(1), 'linhas': [m.group(2)]}
        elif atual:
            atual['linhas'].append(linha)
    if atual:
        blocos.append(atual)

    lancamentos = []
    for bloco in blocos:
        conteudo = ' '.join(bloco['linhas'])
        norm = normalizar_texto(conteudo)
        if any(t in norm for t in ['saldo anterior', 'saldo atual', 'saldo provisionado']):
            continue

        valores = []
        for m in regex_valor.finditer(conteudo):
            token = m.group(1) or m.group(2)
            if token:
                valores.append((m, token))
        if not valores:
            continue

        m_valor, token_valor = valores[-1]
        valor_abs = abs(limpar_valor_monetario(token_valor))
        if valor_abs < 0.005:
            continue

        hist = re.sub(r'\s+', ' ', (conteudo[:m_valor.start()] + ' ' + conteudo[m_valor.end():])).strip()
        hist_norm = normalizar_texto(hist)

        if any(t in hist_norm for t in [
            'ted emitido', 'tarifa', 'debito', 'pix enviado', 'pagamento',
            'saque', 'transferencia enviada', 'ted enviado', 'doc emitido'
        ]):
            valor = -valor_abs
        elif any(t in hist_norm for t in [
            'ted recebido', 'pix recebido', 'credito', 'deposito',
            'transferencia recebida', 'recebimento'
        ]):
            valor = valor_abs
        else:
            valor = interpretar_sinal_inteligente(hist, valor_abs)

        try:
            data = datetime.strptime(bloco['data'], '%d/%m/%Y')
        except ValueError:
            continue

        lancamentos.append({
            'DESCRIÇÃO': banco_identificado or 'BANCO FIBRA',
            'DATA': data,
            'VALOR': round(valor, 2),
            'DÉBITO': '',
            'CRÉDITO': '',
            'HISTÓRICO': limpar_caracteres_ilegais(hist or 'MOVIMENTO BANCARIO')
        })

    return lancamentos

def processar_arquivo_pdf(caminho_pdf, filename_original=None):
    lancamentos = []
    try:
        reader = PdfReader(caminho_pdf, strict=False)
        # O pypdf converte o caminho em BytesIO e perde reader.stream.name.
        # Guardamos explicitamente o arquivo temporário para o fallback OCR.
        reader._razync_source_path = caminho_pdf
        texto_completo = ""
        for pagina in reader.pages:
            texto_completo += (pagina.extract_text() or "") + "\n"
            
        nome_para_identificacao = filename_original or os.path.basename(caminho_pdf)
        banco_identificado = identificar_banco_inteligente(texto_completo, nome_para_identificacao)

        if banco_identificado == 'BANCO BTG':
            with open(caminho_pdf, 'rb') as arquivo_btg:
                return processar_extrato_btg_vgv(
                    arquivo_btg.read()
                ).to_dict('records')

        # Santander Empresarial: formato Data / Histórico / Valor.
        # É processado antes do parser universal porque o próprio PDF informa
        # o sinal com "- R$" nas saídas e sem hífen nas entradas.
        if parece_extrato_santander_empresarial(texto_completo):
            lancamentos_santander = processar_extrato_santander_empresarial_texto(
                texto_completo,
                banco='BANCO SANTANDER',
            )
            if lancamentos_santander:
                return lancamentos_santander

        # O extrato detalhado Dayconnect usa DD/MM nas linhas e informa o ano
        # somente no cabeçalho do período. Esse formato é tratado antes do
        # analisador estrutural geral e fica disponível em todos os fluxos.
        if banco_identificado == 'BANCO DAYCOVAL':
            lancamentos_daycoval = processar_pdf_daycoval_detalhado(
                reader, banco_identificado
            )
            if lancamentos_daycoval:
                return lancamentos_daycoval

        if banco_identificado in {'BANCO ITAU', 'BANCO ITAÚ'}:
            lancamentos_itau = processar_pdf_itau_detalhado(
                reader, banco_identificado
            )
            if lancamentos_itau:
                return lancamentos_itau

        if banco_identificado == 'BANCO BRADESCO':
            lancamentos_bradesco = processar_pdf_bradesco_mensal(
                reader, banco_identificado
            )
            fechamento_bradesco = getattr(reader, '_razync_balance_check', None)
            if fechamento_bradesco:
                request_state.get()['ultimo_fechamento_extrato'] = fechamento_bradesco
            if lancamentos_bradesco:
                return lancamentos_bradesco
            if not texto_completo.strip():
                request_state.get()['ultimo_erro_extrato'] = diagnostico_pdf_sem_lancamentos(
                    banco_identificado,
                    True,
                    bool(getattr(reader, '_razync_ocr_executado', False)),
                    str(getattr(reader, '_razync_ocr_error', '') or '')
                )

        if banco_identificado == 'BANCO FIBRA':
            lancamentos_fibra = processar_pdf_fibra_extrato(
                reader, banco_identificado
            )
            if lancamentos_fibra:
                return lancamentos_fibra

        # Primeiro tenta o analisador estrutural único, independente do banco.
        lancamentos_layout = processar_pdf_layout_universal(reader, banco_identificado)
        if lancamentos_layout:
            return lancamentos_layout

        linhas = [l.strip() for l in texto_completo.split('\n') if l.strip()]
        date_regex = re.compile(r'^(\d{2}/\d{2}/\d{4})')
        
        i = 0
        while i < len(linhas):
            linha = linhas[i]
            match_date = date_regex.match(linha)
            if match_date:
                data_str = match_date.group(1)
                bloco_linhas = [linha]
                j = i + 1
                while j < len(linhas):
                    next_linha = linhas[j]
                    if date_regex.match(next_linha) or 'SALDO' in next_linha.upper() or 'Página' in next_linha:
                        break
                    bloco_linhas.append(next_linha)
                    j += 1
                
                texto_bloco = " ".join(bloco_linhas)
                val_str, natureza_valor = extrair_valor_lancamento_pdf(texto_bloco)

                if val_str is not None:
                    v_num = limpar_valor_monetario(val_str)

                    hist = texto_bloco.replace(data_str, '', 1)
                    hist = re.sub(
                        r'(?<!\d)(?:R\$\s*)?\(?\s*[+-]?[\d\.]+,\d{2}\s*\)?\s*[CD]?(?!\d)',
                        ' ', hist, flags=re.IGNORECASE
                    )
                    hist = re.sub(r'\s+', ' ', hist).strip()

                    if not any(termo in hist.upper() for termo in ['SALDO ANTERIOR', 'SALDO FINAL', 'SALDO DO DIA']) and v_num != 0:
                        v_final = interpretar_sinal_inteligente(hist, v_num, natureza_valor)
                        lancamentos.append({'DESCRIÇÃO': banco_identificado, 'DATA': data_str, 'VALOR': v_final, 'DÉBITO': '', 'CRÉDITO': '', 'HISTÓRICO': limpar_caracteres_ilegais(hist)})
                i = j - 1
            i += 1
    except Exception as e:
        print(f"Erro no processamento PDF universal: {e}")
    return lancamentos

def processar_extrato_unificado(file_bytes, filename):
    """Leitor único de extratos usado por todas as ferramentas do Razync."""
    extensao = os.path.splitext(filename)[1].lower()
    if extensao == '.ofx':
        return processar_ofx(file_bytes, filename)
    if extensao in ['.csv', '.xlsx', '.xls']:
        return processar_planilha_universal(file_bytes, filename)
    if extensao != '.pdf':
        return []

    request_state.get().pop('ultimo_erro_extrato', None)
    request_state.get().pop('ultimo_fechamento_extrato', None)
    caminho_temporario = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temporario:
            temporario.write(file_bytes)
            caminho_temporario = temporario.name
        # O nome ORIGINAL é sempre passado. Isso evita que um arquivo temporário
        # faça o identificador perder banco/conta e cair no parser errado.
        return processar_arquivo_pdf(caminho_temporario, filename)
    finally:
        if caminho_temporario and os.path.exists(caminho_temporario):
            os.remove(caminho_temporario)

def gerar_excel_modelo_dominio(df, formato_data=None):
    """Preenche uma cópia fiel do Modelo Domínio, preservando sua estrutura e estilos."""
    from copy import copy
    from openpyxl import load_workbook

    caminho_modelo = next(
        (caminho for caminho in [str(TEMPLATE), 'Modelo dominio(6).xlsx']
         if os.path.exists(caminho)),
        None
    )
    if not caminho_modelo:
        raise FileNotFoundError('Modelo Domínio não encontrado no sistema.')

    wb = load_workbook(caminho_modelo)
    ws = wb[wb.sheetnames[0]]

    # Localiza a linha real do cabeçalho sem presumir que seja sempre a primeira.
    cabecalho_linha = None
    mapa_colunas = {}
    for linha in range(1, min(ws.max_row, 25) + 1):
        mapa_temp = {}
        for coluna in range(1, ws.max_column + 1):
            valor = ws.cell(linha, coluna).value
            nome = normalizar_texto(str(valor or '')).strip()
            if nome:
                mapa_temp[nome] = coluna
        if 'data' in mapa_temp and 'valor' in mapa_temp and 'historico' in mapa_temp:
            cabecalho_linha = linha
            mapa_colunas = mapa_temp
            break

    if cabecalho_linha is None:
        raise ValueError('Cabeçalho do Modelo Domínio não foi localizado.')

    df = padronizar_historicos_modelo(df)
    nomes_df = {normalizar_texto(str(c)).strip(): c for c in df.columns}
    linha_modelo = cabecalho_linha + 1

    # Guarda o estilo da primeira linha de dados do próprio modelo para replicá-lo.
    estilos = {}
    for coluna in range(1, ws.max_column + 1):
        celula = ws.cell(linha_modelo, coluna)
        estilos[coluna] = {
            'font': copy(celula.font),
            'fill': copy(celula.fill),
            'border': copy(celula.border),
            'alignment': copy(celula.alignment),
            'number_format': celula.number_format,
            'protection': copy(celula.protection),
        }

    # Remove somente conteúdos antigos da área de dados. Cabeçalho, larguras,
    # filtros, congelamentos, impressão e demais propriedades ficam intactos.
    for linha in range(cabecalho_linha + 1, ws.max_row + 1):
        for coluna in range(1, ws.max_column + 1):
            ws.cell(linha, coluna).value = None

    for indice, registro in enumerate(df.to_dict('records'), start=cabecalho_linha + 1):
        for nome_normalizado, coluna_excel in mapa_colunas.items():
            coluna_df = nomes_df.get(nome_normalizado)
            if coluna_df is None:
                continue
            valor = registro.get(coluna_df, '')
            if pd.isna(valor):
                valor = ''
            if nome_normalizado == 'data' and valor not in ('', None):
                data = pd.to_datetime(valor, dayfirst=True, errors='coerce')
                valor = data.to_pydatetime() if not pd.isna(data) else valor

            celula = ws.cell(indice, coluna_excel)
            celula.value = valor
            estilo = estilos.get(coluna_excel)
            if estilo:
                celula.font = copy(estilo['font'])
                celula.fill = copy(estilo['fill'])
                celula.border = copy(estilo['border'])
                celula.alignment = copy(estilo['alignment'])
                celula.number_format = estilo['number_format']
                celula.protection = copy(estilo['protection'])
            if nome_normalizado == 'data' and formato_data:
                celula.number_format = formato_data

    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()

def carregar_modelo_dominio_base():
    """Lê o arquivo-base uma vez e reutiliza entre reruns do Streamlit."""
    colunas = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
    caminho = str(TEMPLATE)
    if not os.path.exists(caminho):
        return pd.DataFrame(columns=colunas)
    try:
        df = pd.read_excel(caminho)
    except Exception:
        return pd.DataFrame(columns=colunas)
    if 'DESCRIÇÃO' not in df.columns:
        return pd.DataFrame(columns=colunas)
    return df

def gerar_txt_dominio(df):
    df = padronizar_historicos_modelo(df)
    linhas_txt = []
    for _, row in df.iterrows():
        hist_limpo = limpar_caracteres_ilegais(str(row['HISTÓRICO'])).replace(';', ' ')
        linhas_txt.append(f"{row['DATA']};{row['DÉBITO'] if pd.notna(row['DÉBITO']) else ''};{row['CRÉDITO'] if pd.notna(row['CRÉDITO']) else ''};{float(row['VALOR']):.2f};{hist_limpo}\n")
    return "".join(linhas_txt)

def recuperar_xls_biff_irregular(file_bytes):
    """
    Recupera relatórios .xls antigos cujo contêiner OLE está legível, mas os
    endereços internos das planilhas estão inconsistentes. A correção ocorre
    somente em memória; o arquivo enviado pelo usuário não é alterado.
    """
    try:
        from xlrd.compdoc import CompDoc

        documento = CompDoc(file_bytes, ignore_workbook_corruption=True)
        fluxo_workbook = documento.get_named_stream('Workbook')
        if not fluxo_workbook:
            fluxo_workbook = documento.get_named_stream('Book')
        if not fluxo_workbook:
            return None

        fluxo = bytearray(fluxo_workbook)
        registros_abas = []
        posicao = 0
        fim_dos_globais = None

        # Localiza os registros BOUNDSHEET no bloco global do BIFF.
        while posicao + 4 <= len(fluxo):
            codigo, tamanho = struct.unpack_from('<HH', fluxo, posicao)
            fim_registro = posicao + 4 + tamanho
            if fim_registro > len(fluxo):
                break
            if codigo == 0x0085 and tamanho >= 4:
                registros_abas.append(posicao)
            posicao = fim_registro
            if codigo == 0x000A:
                fim_dos_globais = posicao
                break

        if not registros_abas or fim_dos_globais is None:
            return None

        # Procura os BOFs reais das planilhas, gráficos ou macros.
        inicios_reais = []
        cursor = fim_dos_globais
        while True:
            indice = fluxo.find(b'\x09\x08', cursor)
            if indice < 0:
                break
            if indice + 8 <= len(fluxo):
                tamanho = struct.unpack_from('<H', fluxo, indice + 2)[0]
                if tamanho >= 4 and indice + 4 + tamanho <= len(fluxo):
                    versao, tipo_fluxo = struct.unpack_from('<HH', fluxo, indice + 4)
                    if versao in (0x0500, 0x0600) and tipo_fluxo in (0x0010, 0x0020, 0x0040):
                        inicios_reais.append(indice)
            cursor = indice + 2

        if len(inicios_reais) < len(registros_abas):
            return None

        for registro_aba, inicio_real in zip(registros_abas, inicios_reais):
            struct.pack_into('<I', fluxo, registro_aba + 4, inicio_real)

        arquivo_recuperado = io.BytesIO(bytes(fluxo))
        xls = pd.ExcelFile(arquivo_recuperado, engine='xlrd')
        for nome_aba in xls.sheet_names:
            df_temp = pd.read_excel(
                xls, sheet_name=nome_aba, dtype=str, header=None
            )
            if df_temp is not None and not df_temp.empty and df_temp.shape[1] > 1:
                return df_temp
    except Exception:
        return None

    return None

def processar_razao_dominio(file_bytes, filename):
    df = None
    ext = os.path.splitext(filename)[1].lower()

    try:
        if ext == '.xlsx':
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            for sheet in xls.sheet_names:
                df_temp = pd.read_excel(
                    xls, sheet_name=sheet, dtype=str, header=None
                )
                if df_temp is not None and not df_temp.empty and df_temp.shape[1] > 1:
                    df = df_temp
                    break
        elif ext == '.xls':
            try:
                df = pd.read_excel(
                    io.BytesIO(file_bytes),
                    dtype=str,
                    header=None,
                    engine='xlrd'
                )
            except Exception:
                # Alguns relatórios com extensão XLS são tabelas HTML.
                try:
                    tabelas = pd.read_html(io.BytesIO(file_bytes), header=None)
                    if tabelas:
                        df = tabelas[0].astype(str)
                except Exception:
                    df = None

                # Relatórios binários antigos da Domínio podem conter os dados
                # intactos, mas apontadores BIFF incorretos. Recuperamos tudo
                # em memória para evitar conversões manuais.
                if df is None or df.empty:
                    df = recuperar_xls_biff_irregular(file_bytes)
                    if df is not None and not df.empty:
                        request_state.get()['razao_xls_recuperado'] = True
                    else:
                        request_state.get()['erro_bof_xls'] = True
                        return None
        else:
            for enc in ['utf-8', 'latin1', 'cp1252']:
                for sep in [';', '\t', '|', ',']:
                    try:
                        df = pd.read_csv(
                            io.BytesIO(file_bytes),
                            sep=sep,
                            encoding=enc,
                            dtype=str,
                            header=None,
                            on_bad_lines='skip'
                        )
                        if df.shape[1] > 1:
                            break
                    except Exception:
                        continue
                if df is not None and df.shape[1] > 1:
                    break
    except Exception:
        return None

    if df is None or df.empty:
        return None

    header_row_idx = 0
    for idx, row in df.iterrows():
        row_str = " ".join(
            [str(v) for v in row.values if pd.notna(v)]
        ).upper()
        possui_data = 'DATA' in row_str or re.search(r'\bDT\b', row_str)
        possui_valor = any(
            termo in row_str
            for termo in ['VALOR', 'DEBITO', 'DÉBITO', 'CREDITO', 'CRÉDITO']
        )
        if possui_data and possui_valor:
            header_row_idx = idx
            break

    if header_row_idx > 0:
        df.columns = [
            str(v).strip().upper() for v in df.iloc[header_row_idx].values
        ]
        df = df.iloc[header_row_idx + 1:].copy()
    else:
        df.columns = [str(v).strip().upper() for v in df.iloc[0].values]
        df = df.iloc[1:].copy()

    df.columns = [re.sub(r'[^\w\s]', '', coluna) for coluna in df.columns]
    cols = list(df.columns)

    col_data = next(
        (c for c in cols if any(p in c for p in ['DATA', 'DT'])),
        None
    )
    col_deb = next(
        (c for c in cols if any(
            p in c for p in ['DEBITO', 'DÉBITO', 'SAIDA', 'DEB']
        )),
        None
    )
    col_cred = next(
        (c for c in cols if any(
            p in c for p in ['CREDITO', 'CRÉDITO', 'ENTRADA', 'CRE']
        )),
        None
    )
    col_val = next(
        (c for c in cols if any(p in c for p in ['VALOR', 'VL'])),
        None
    )
    col_hist = next(
        (c for c in cols if any(
            p in c
            for p in [
                'HISTORICO', 'HISTÓRICO', 'HIST', 'COMPLEMENTO',
                'LANCAMENTO', 'DESCRI'
            ]
        )),
        None
    )

    if not col_data:
        return None

    dados = []
    for _, row in df.iterrows():
        dt_raw = str(row[col_data]).strip() if pd.notna(row[col_data]) else ''

        # Datas lidas de XLS podem chegar como AAAA-MM-DD. Nesse caso não se
        # deve aplicar dayfirst, pois 2026-03-02 viraria 03/02/2026.
        if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', dt_raw):
            data_parseada = pd.to_datetime(
                dt_raw, yearfirst=True, errors='coerce'
            )
        else:
            match_dt = re.search(
                r'(?<!\d)(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})(?!\d)',
                dt_raw
            )
            data_parseada = (
                pd.to_datetime(
                    match_dt.group(1), dayfirst=True, errors='coerce'
                )
                if match_dt else pd.NaT
            )

        if pd.isna(data_parseada):
            continue
        dt_fmt = data_parseada.strftime('%d/%m/%Y')

        v_ent, v_sai = 0.0, 0.0

        if col_deb and col_cred:
            v_sai = (
                abs(limpar_valor_monetario(row[col_deb]))
                if pd.notna(row[col_deb]) else 0.0
            )
            v_ent = (
                abs(limpar_valor_monetario(row[col_cred]))
                if pd.notna(row[col_cred]) else 0.0
            )
        elif col_val and pd.notna(row[col_val]):
            val_num = limpar_valor_monetario(row[col_val])
            if val_num < 0:
                v_sai = abs(val_num)
            else:
                v_ent = val_num

        hist_str = (
            limpar_caracteres_ilegais(str(row[col_hist]).strip())
            if col_hist and pd.notna(row[col_hist])
            else 'LANCAMENTO RAZAO'
        )

        if v_ent != 0 or v_sai != 0:
            dados.append({
                'DATA': dt_fmt,
                'ENTRADAS_RAZAO': v_ent,
                'SAIDAS_RAZAO': v_sai,
                'HISTÓRICO': hist_str
            })

    if not dados:
        return None

    df_res = pd.DataFrame(dados)
    df_res['DATA_DT'] = pd.to_datetime(
        df_res['DATA'], dayfirst=True, errors='coerce'
    )
    return df_res.dropna(subset=['DATA_DT'])

def texto_celula_seguro(valor):
    if valor is None or pd.isna(valor): return ""
    if isinstance(valor, float) and valor.is_integer(): return str(int(valor))
    return limpar_caracteres_ilegais(str(valor)).strip()

def identificar_estorno_de_baixa(*campos):
    """Reconhece apenas estornos ligados a baixa, preservando outros estornos."""
    texto = normalizar_texto(" ".join(texto_celula_seguro(c) for c in campos))
    tokens = re.findall(r'[a-z0-9]+', texto)
    pos_estorno = [i for i, token in enumerate(tokens) if token.startswith(('estorn', 'revers'))]
    pos_baixa = [i for i, token in enumerate(tokens) if token.startswith('baix')]
    return any(abs(i - j) <= 6 for i in pos_estorno for j in pos_baixa)

def criar_assinatura_classificacao(historico):
    """Remove documentos variáveis e preserva natureza, empresa e observação útil."""
    texto = normalizar_texto(texto_celula_seguro(historico))
    texto = re.sub(r'\b(?:pagar|pagamento)\b', 'pago', texto)
    texto = re.sub(r'\b(?:receber|recebimento)\b', 'recebido', texto)
    natureza = (
        'pago' if re.search(r'\bpago\b', texto)
        else 'recebido' if re.search(r'\brecebido\b', texto)
        else 'outro'
    )
    empresa_match = re.search(r'empresa\s*:\s*(.*?)(?:\s+obs\s*:|$)', texto)
    empresa = empresa_match.group(1) if empresa_match else texto
    empresa = re.sub(r'[^a-z0-9]+', ' ', empresa)
    tokens_empresa = [
        token for token in empresa.split()
        if not (any(c.isdigit() for c in token) and len(token) >= 3)
    ]
    empresa = ' '.join(tokens_empresa).strip()

    observacao = ''
    observacao_match = re.search(r'\s+obs\s*:\s*(.*)$', texto)
    if observacao_match:
        observacao_bruta = re.sub(r'[^a-z0-9]+', ' ', observacao_match.group(1))
        # Números, documentos, parcelas e datas mudam a cada mês. Palavras como
        # BANCO FIBRA, TRANSFERENCIA ou DEVOLUCAO alteram a classificação e ficam.
        tokens_observacao = [
            token for token in observacao_bruta.split()
            if token.isalpha() and token not in {'doc', 'documento'}
        ]
        observacao = ' '.join(tokens_observacao).strip()

    partes = [natureza, empresa]
    if observacao:
        partes.append(observacao)
    return '|'.join(partes) if empresa else ''

def decompor_assinatura_classificacao(assinatura):
    partes = str(assinatura or '').split('|')
    natureza = partes[0] if partes else ''
    empresa = partes[1] if len(partes) > 1 else ''
    observacao = '|'.join(partes[2:]) if len(partes) > 2 else ''
    return natureza, empresa, observacao

def extrair_nome_empresa_classificacao(historico, assinatura=''):
    """
    Extrai a entidade do histórico e elimina somente ruídos que mudam por mês,
    preservando as palavras que realmente identificam o fornecedor ou cliente.
    """
    texto = normalizar_texto(texto_celula_seguro(historico))
    empresa_match = re.search(
        r'empresa\s*:\s*(.*?)(?:\s+obs\s*:|$)', texto
    )
    if empresa_match:
        empresa = empresa_match.group(1)
    elif assinatura:
        _, empresa, _ = decompor_assinatura_classificacao(assinatura)
    else:
        empresa = re.sub(
            r'^\s*(?:pago|pagar|pagamento|recebido|receber|recebimento)\b',
            ' ',
            texto
        )
        # Remove um documento variável que apareça logo após a natureza.
        empresa = re.sub(
            r'^\s*[a-z0-9./-]*\d[a-z0-9./-]*\s+',
            ' ',
            empresa
        )

    tokens = re.findall(r'[a-z0-9]+', empresa)
    termos_ruido = {
        'ltda', 'limitada', 'eireli', 'epp', 'me', 'mei', 'sa', 's', 'a',
        'sociedade', 'anonima', 'unipessoal', 'de', 'da', 'do', 'das', 'dos',
        'e', 'doc', 'documento', 'nf', 'nfe', 'nota', 'fiscal', 'pedido',
        'parcela', 'pagto', 'pago', 'recebido', 'empresa', 'obs'
    }
    tokens_validos = []
    for token in tokens:
        if token in termos_ruido or token.isdigit() or len(token) < 2:
            continue
        # Protocolos mistos longos também variam entre os períodos. Marcas
        # curtas com números, como 3M, continuam preservadas.
        if any(caractere.isdigit() for caractere in token) and len(token) >= 4:
            continue
        tokens_validos.append(token)
    return ' '.join(tokens_validos).strip()

def normalizar_nome_empresa_classificacao(nome):
    """Normaliza um nome já extraído para comparação conservadora."""
    return extrair_nome_empresa_classificacao(nome)

def calcular_similaridade_nome_empresa(nome_a, nome_b):
    """
    Compara nomes por caracteres e palavras. Nomes de uma única palavra só
    passam quando são exatamente iguais, evitando aproximações arriscadas.
    """
    a = normalizar_nome_empresa_classificacao(nome_a)
    b = normalizar_nome_empresa_classificacao(nome_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    tokens_a, tokens_b = set(a.split()), set(b.split())
    if min(len(tokens_a), len(tokens_b)) < 2:
        return 0.0

    comuns = tokens_a & tokens_b
    if not comuns:
        return 0.0

    # Algumas palavras e siglas mudam a natureza contábil mesmo quando o nome
    # principal é igual. Elas precisam coincidir exatamente na aproximação.
    termos_criticos = {
        'antecipado', 'antecipada', 'adiantamento', 'ferias', 'rescisao',
        'salario', 'folha', 'inss', 'fgts', 'irrf', 'pis', 'cofins', 'csll',
        'icms', 'iss', 'gnre', 'imposto', 'tributo', 'tarifa', 'juros',
        'multa', 'aluguel', 'frete', 'transferencia', 'transf', 'devolucao',
        'emprestimo', 'aplicacao', 'rendimento', 'filial', 'matriz'
    }
    if (tokens_a & termos_criticos) != (tokens_b & termos_criticos):
        return 0.0

    # Siglas curtas costumam identificar empresas, estados ou tipos de operação.
    # BS e BD, por exemplo, não podem ser tratadas como simples erro de digitação.
    siglas_a = {token for token in tokens_a if len(token) <= 3}
    siglas_b = {token for token in tokens_b if len(token) <= 3}
    if siglas_a != siglas_b:
        return 0.0

    razao_caracteres = difflib.SequenceMatcher(None, a, b).ratio()
    cobertura = len(comuns) / min(len(tokens_a), len(tokens_b))
    uniao = tokens_a | tokens_b
    jaccard = len(comuns) / len(uniao) if uniao else 0.0

    # Um nome completo contido no outro é um sinal forte, desde que existam
    # pelo menos duas palavras distintivas em comum.
    if (a in b or b in a) and len(comuns) >= 2:
        return max(0.97, razao_caracteres)

    # Aceita pequenas variações de escrita ou complemento, mas nunca apenas
    # porque duas empresas compartilham uma palavra genérica.
    if len(comuns) >= 2 and cobertura >= 0.80 and razao_caracteres >= 0.72:
        return max(0.95, (razao_caracteres * 0.55) + (cobertura * 0.35) + (jaccard * 0.10))
    if len(comuns) >= 2 and cobertura >= 0.67 and razao_caracteres >= 0.90:
        return max(0.94, razao_caracteres)
    if len(comuns) >= 1 and razao_caracteres >= 0.95 and min(len(a), len(b)) >= 10:
        return razao_caracteres
    return 0.0

def encontrar_conta_por_nome_historico(historico, natureza, evidencias_nomes):
    """
    Retorna uma conta somente quando o nome foi confirmado em períodos
    diferentes, pertence à mesma natureza e não possui classificação concorrente.
    """
    nome_alvo = extrair_nome_empresa_classificacao(historico)
    if natureza not in {'pago', 'recebido'} or len(nome_alvo) < 4:
        return None, 0.0, 'nome_insuficiente'

    entidades_natureza = evidencias_nomes.get(natureza, {})
    evidencia_exata = entidades_natureza.get(nome_alvo)
    if evidencia_exata:
        if len(evidencia_exata) != 1:
            return None, 1.0, 'conflito'
        conta, evidencia = next(iter(evidencia_exata.items()))
        if len(evidencia['periodos']) >= 2:
            return conta, 1.0, 'nome_exato'
        # Um único mês não ensina uma regra contábil com segurança.
        return None, 1.0, 'evidencia_insuficiente'

    melhor_por_conta = {}
    for nome_base, contas in entidades_natureza.items():
        if len(contas) != 1:
            continue
        conta, evidencia = next(iter(contas.items()))
        # Aproximação textual exige uma conta repetida nos três meses da base.
        # Nome exatamente igual continua podendo ser confirmado em dois períodos.
        if len(evidencia['periodos']) < 3 or evidencia['ocorrencias'] < 3:
            continue
        similaridade = calcular_similaridade_nome_empresa(nome_alvo, nome_base)
        if similaridade > melhor_por_conta.get(conta, 0.0):
            melhor_por_conta[conta] = similaridade

    resultados = sorted(
        melhor_por_conta.items(), key=lambda item: item[1], reverse=True
    )
    if not resultados or resultados[0][1] < 0.94:
        return None, resultados[0][1] if resultados else 0.0, 'sem_correspondencia'

    melhor_conta, melhor_nota = resultados[0]
    segunda_nota = resultados[1][1] if len(resultados) > 1 else 0.0
    if segunda_nota >= 0.90 and (melhor_nota - segunda_nota) < 0.08:
        return None, melhor_nota, 'conflito'
    return melhor_conta, melhor_nota, 'nome_aproximado'

def identificar_banco_classificacao_eletro_forte(nome_aba='', descricao='', debito='', credito=''):
    """Distingue BB 8, Itaú 508 e Itaú 509 na empresa 242."""
    valores = {
        texto_celula_seguro(debito),
        texto_celula_seguro(credito),
    }
    if '509' in valores:
        return 'itau_509'
    if '508' in valores:
        return 'itau_508'
    if '512' in valores:
        return 'itau_512'
    if '8' in valores:
        return 'bb'

    texto = normalizar_texto(f"{nome_aba} {descricao}")
    if '509' in texto or '181537' in texto:
        return 'itau_509'
    if '508' in texto or '105318' in texto:
        return 'itau_508'
    if '512' in texto:
        return 'itau_512'
    if 'bb' in texto or 'banco do brasil' in texto:
        return 'bb'
    return ''

def ler_planilha_classificada(file_bytes, filename, empresa='nova_geracao'):
    """Lê planilha revisada e cria padrões exclusivos da empresa informada."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    registros = []
    banco_arquivo = identificar_chave_banco_empresa(filename)
    for nome_aba in xls.sheet_names:
        # Na empresa 242, a aba Principal é apenas a cópia preservada do relatório
        # original. A Base Inteligente aprende somente com as abas bancárias geradas.
        if empresa.startswith('eletro_forte') and normalizar_texto(nome_aba).strip() == 'principal':
            continue
        bruto = pd.read_excel(xls, sheet_name=nome_aba, header=None, dtype=object)
        indice_cabecalho = None
        for indice in range(min(30, len(bruto))):
            nomes = [normalizar_texto(texto_celula_seguro(v)).strip() for v in bruto.iloc[indice]]
            if all(nome in nomes for nome in ['data', 'valor', 'debito', 'credito']) and (
                'historico' in nomes
            ):
                indice_cabecalho = indice
                break
        if indice_cabecalho is None:
            continue
        cabecalhos = [texto_celula_seguro(v) for v in bruto.iloc[indice_cabecalho]]
        df = bruto.iloc[indice_cabecalho + 1:].copy()
        df.columns = cabecalhos
        mapa = {normalizar_texto(str(c)).strip(): c for c in df.columns}
        col_hist = mapa.get('historico')
        col_data = mapa.get('data')
        col_debito = mapa.get('debito')
        col_credito = mapa.get('credito')
        col_descricao = mapa.get('descricao')
        if col_hist is None or col_debito is None or col_credito is None:
            continue
        banco_aba = identificar_chave_banco_empresa(nome_aba)
        for _, linha in df.iterrows():
            historico = texto_celula_seguro(linha[col_hist])
            debito = texto_celula_seguro(linha[col_debito])
            credito = texto_celula_seguro(linha[col_credito])
            if not historico or not debito or not credito:
                continue
            descricao_linha = linha[col_descricao] if col_descricao is not None else ''
            if empresa.startswith('eletro_forte'):
                banco_linha = identificar_banco_classificacao_eletro_forte(
                    nome_aba, descricao_linha, debito, credito
                )
                bancos_validos = (
                    {'itau_512'} if empresa == 'eletro_forte_filial_1408'
                    else {'bb', 'itau_508', 'itau_509'}
                )
            else:
                banco_linha = (
                    identificar_chave_banco_empresa(descricao_linha)
                    if col_descricao is not None else ''
                ) or banco_aba or banco_arquivo
                if empresa in {'valean_625', 'valean_626'}:
                    bancos_validos = {'banco_brasil', 'caixa', 'sicredi'}
                else:
                    bancos_validos = {
                        'itau', 'bradesco', 'fibra', 'daycoval', 'sicredi',
                        'santander', 'btg'
                    }
            assinatura = criar_assinatura_classificacao(historico)
            if banco_linha not in bancos_validos or not assinatura:
                continue
            data_lancamento = (
                pd.to_datetime(linha[col_data], dayfirst=True, errors='coerce')
                if col_data is not None else pd.NaT
            )
            periodo = (
                data_lancamento.strftime('%Y-%m') if not pd.isna(data_lancamento)
                else normalizar_texto(filename)
            )
            identificador = hashlib.sha256(
                f"{empresa}|{banco_linha}|{assinatura}|{debito}|{credito}".encode('utf-8')
            ).hexdigest()
            registros.append({
                'id': identificador,
                'empresa': empresa,
                'banco': banco_linha,
                'assinatura': assinatura,
                'debito': debito,
                'credito': credito,
                'ocorrencias': 1,
                'periodos': [periodo],
                'exemplo_historico': historico[:500]
            })
    return registros

def importar_arquivos_classificados(
    arquivos, empresa='nova_geracao', contas_bancarias=None
):
    """Aceita XLSX/ZIP e mantém o aprendizado isolado por empresa."""
    from razync.dominio_ledger import ler_razao_dominio_base

    registros = []

    def ler_arquivo(conteudo, nome):
        if contas_bancarias:
            lancamentos_razao = ler_razao_dominio_base(
                conteudo, nome, contas_bancarias
            )
            if lancamentos_razao:
                aprendizados = []
                for item in lancamentos_razao:
                    assinatura = criar_assinatura_classificacao(item['historico'])
                    if not assinatura:
                        continue
                    periodo = item['data'].strftime('%Y-%m')
                    debito = texto_celula_seguro(item['debito'])
                    credito = texto_celula_seguro(item['credito'])
                    identificador = hashlib.sha256(
                        f"{empresa}|{item['banco']}|{assinatura}|{debito}|{credito}".encode('utf-8')
                    ).hexdigest()
                    aprendizados.append({
                        'id': identificador,
                        'empresa': empresa,
                        'banco': item['banco'],
                        'assinatura': assinatura,
                        'debito': debito,
                        'credito': credito,
                        'ocorrencias': 1,
                        'periodos': [periodo],
                        'exemplo_historico': item['historico'][:500],
                    })
                return aprendizados
        return ler_planilha_classificada(conteudo, nome, empresa)

    for arquivo in arquivos:
        conteudo = arquivo.getvalue()
        nome = arquivo.name
        if nome.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
                membros = [
                    membro for membro in pacote.infolist()
                    if not membro.is_dir() and membro.filename.lower().endswith(('.xlsx', '.xls'))
                ]
                if sum(membro.file_size for membro in membros) > 60 * 1024 * 1024:
                    raise ValueError('O conteúdo descompactado ultrapassa o limite de 60 MB.')
                for membro in membros:
                    if membro.file_size > 20 * 1024 * 1024:
                        raise ValueError(f'A planilha {membro.filename} ultrapassa 20 MB.')
                    registros.extend(ler_arquivo(
                        pacote.read(membro), os.path.basename(membro.filename)
                    ))
        else:
            registros.extend(ler_arquivo(conteudo, nome))

    agrupados = {}
    for registro in registros:
        chave = registro['id']
        if chave not in agrupados:
            agrupados[chave] = registro
        else:
            agrupados[chave]['ocorrencias'] += 1
            agrupados[chave]['periodos'] = sorted(set(
                agrupados[chave]['periodos'] + registro['periodos']
            ))
    return list(agrupados.values())

def aplicar_classificacoes_automaticas(df, banco, base_classificacoes):
    """Preenche apenas padrões repetidos e com uma única classificação conhecida."""
    resultado = df.copy()
    resultado['_CLASSIFICAÇÃO'] = 'Pendente'
    candidatos = {}
    periodos_por_assinatura = {}
    for item in base_classificacoes:
        if item.get('banco') != banco:
            continue
        assinatura = item.get('assinatura', '')
        par = (texto_celula_seguro(item.get('debito')), texto_celula_seguro(item.get('credito')))
        if assinatura and all(par):
            candidatos.setdefault(assinatura, set()).add(par)
            periodos_por_assinatura.setdefault(assinatura, set()).update(
                item.get('periodos') or []
            )
    mapa_seguro = {
        assinatura: next(iter(pares))
        for assinatura, pares in candidatos.items()
        if len(pares) == 1 and len(periodos_por_assinatura.get(assinatura, set())) >= 3
    }
    for indice, linha in resultado.iterrows():
        if texto_celula_seguro(linha.get('DÉBITO')) or texto_celula_seguro(linha.get('CRÉDITO')):
            resultado.at[indice, '_CLASSIFICAÇÃO'] = 'Já preenchido'
            continue
        assinatura = criar_assinatura_classificacao(linha.get('HISTÓRICO', ''))
        if assinatura in mapa_seguro:
            debito, credito = mapa_seguro[assinatura]
            resultado.at[indice, 'DÉBITO'] = debito
            resultado.at[indice, 'CRÉDITO'] = credito
            resultado.at[indice, '_CLASSIFICAÇÃO'] = 'Automática'
        elif assinatura in candidatos and len(candidatos[assinatura]) > 1:
            resultado.at[indice, '_CLASSIFICAÇÃO'] = 'Revisar conflito'
        elif assinatura in candidatos:
            resultado.at[indice, '_CLASSIFICAÇÃO'] = 'Revisar padrão novo'
    return resultado

def classificar_planilha_final(
    file_bytes, filename, base_classificacoes, contas_bancarias=None,
    empresa_classificacao='', coluna_substituir='', valores_substituiveis=None,
    modo_consolidado_eletro_forte=False,
):
    """Preenche Débito/Crédito somente na planilha final já conciliada."""
    from openpyxl import load_workbook

    if not filename.lower().endswith('.xlsx'):
        raise ValueError('A planilha final deve estar no formato .xlsx.')

    contas_bancarias = contas_bancarias or {
        'itau': '508', 'bradesco': '9', 'fibra': '506'
    }
    candidatos_por_banco = {}
    periodos_por_banco = {}
    evidencias_nomes_por_banco = {}
    for item in base_classificacoes:
        banco = item.get('banco', '')
        assinatura = item.get('assinatura', '')
        debito_item = texto_celula_seguro(item.get('debito'))
        credito_item = texto_celula_seguro(item.get('credito'))
        conta_banco_item = texto_celula_seguro(contas_bancarias.get(banco, ''))

        # Para padrões já aprendidos, a posição REAL da conta bancária é mais
        # confiável que palavras como "pago" ou "recebido" presentes no histórico.
        if banco in contas_bancarias and conta_banco_item:
            if credito_item == conta_banco_item and debito_item:
                natureza = 'pago'
                contrapartida = debito_item
            elif debito_item == conta_banco_item and credito_item:
                natureza = 'recebido'
                contrapartida = credito_item
            else:
                natureza = assinatura.split('|', 1)[0] if assinatura else ''
                contrapartida = ''
        else:
            natureza = assinatura.split('|', 1)[0] if assinatura else ''
            contrapartida = ''

        # Normaliza também a assinatura existente para a natureza real inferida
        # pela posição da conta do banco. Isso reaproveita a base antiga sem zerar.
        if assinatura and natureza in {'pago', 'recebido'}:
            partes_assinatura = assinatura.split('|', 1)
            sufixo_assinatura = partes_assinatura[1] if len(partes_assinatura) > 1 else ''
            assinatura = (
                f"{natureza}|{sufixo_assinatura}" if sufixo_assinatura else natureza
            )
        if banco not in contas_bancarias or not assinatura or not contrapartida:
            continue
        candidatos_por_banco.setdefault(banco, {}).setdefault(assinatura, set()).add(
            contrapartida
        )
        periodos_item = set(item.get('periodos') or [])
        periodos_por_banco.setdefault(banco, {}).setdefault(assinatura, set()).update(
            periodos_item
        )

        historico_exemplo = item.get('exemplo_historico') or ''
        nome_empresa = extrair_nome_empresa_classificacao(
            historico_exemplo, assinatura
        )
        if nome_empresa:
            por_natureza = evidencias_nomes_por_banco.setdefault(
                banco, {}
            ).setdefault(natureza, {})
            por_conta = por_natureza.setdefault(nome_empresa, {}).setdefault(
                contrapartida,
                {'periodos': set(), 'ocorrencias': 0}
            )
            por_conta['periodos'].update(periodos_item)
            try:
                ocorrencias_item = max(1, int(item.get('ocorrencias') or 1))
            except (TypeError, ValueError):
                ocorrencias_item = 1
            por_conta['ocorrencias'] += ocorrencias_item

    mapas_seguros = {}
    for banco, candidatos in candidatos_por_banco.items():
        mapas_seguros[banco] = {
            assinatura: next(iter(contas))
            for assinatura, contas in candidatos.items()
            if len(contas) == 1 and len(
                periodos_por_banco.get(banco, {}).get(assinatura, set())
            ) >= 3
        }

    def valor_conta_excel(conta):
        texto = texto_celula_seguro(conta)
        if texto.isdigit() and (texto == '0' or not texto.startswith('0')):
            return int(texto)
        return texto

    wb = load_workbook(io.BytesIO(file_bytes))
    resumo = {
        'automaticos': 0,
        'somente_banco': 0,
        'antecipados': 0,
        'regras_fixas_1000': 0,
        'por_nome_empresa': 0,
        'ja_preenchidos': 0,
        'parciais_completados': 0,
        'conflitos': 0,
        'padroes_novos': 0,
        'banco_nao_identificado': 0,
        'abas_processadas': 0,
        'elegiveis_regra': 0,
        'preservados_regra': 0,
    }
    banco_arquivo = identificar_chave_banco_empresa(filename)
    cache_similaridade = {}

    for ws in wb.worksheets:
        # Na 242, nunca classificar a aba Principal. Ela deve permanecer exatamente
        # como foi recebida; somente as abas BB/Itau do Modelo Domínio são alteradas.
        if empresa_classificacao.startswith('eletro_forte') and normalizar_texto(ws.title).strip() == 'principal':
            continue
        if 'retir' in normalizar_texto(ws.title):
            continue
        linha_cabecalho = None
        mapa_colunas = {}
        for numero_linha in range(1, min(ws.max_row, 30) + 1):
            mapa_teste = {
                normalizar_texto(texto_celula_seguro(ws.cell(numero_linha, coluna).value)).strip(): coluna
                for coluna in range(1, ws.max_column + 1)
            }
            if all(nome in mapa_teste for nome in ['historico', 'debito', 'credito']):
                linha_cabecalho = numero_linha
                mapa_colunas = mapa_teste
                break
        if linha_cabecalho is None:
            continue

        resumo['abas_processadas'] += 1
        col_hist = mapa_colunas['historico']
        col_debito = mapa_colunas['debito']
        col_credito = mapa_colunas['credito']
        col_valor = mapa_colunas.get('valor')
        col_descricao = mapa_colunas.get('descricao')
        banco_aba = identificar_chave_banco_empresa(ws.title) or banco_arquivo

        for numero_linha in range(linha_cabecalho + 1, ws.max_row + 1):
            historico = texto_celula_seguro(ws.cell(numero_linha, col_hist).value)
            if not historico:
                continue
            debito_atual = texto_celula_seguro(ws.cell(numero_linha, col_debito).value)
            credito_atual = texto_celula_seguro(ws.cell(numero_linha, col_credito).value)

            # Na 242, algumas contas são placeholders e precisam ser substituídas
            # pela Base Inteligente. Todo valor fora da lista é preservado.
            coluna_regra = normalizar_texto(coluna_substituir or '').strip()
            valores_regra = {
                texto_celula_seguro(v) for v in (valores_substituiveis or [])
            }
            if modo_consolidado_eletro_forte:
                valor_consolidado = (
                    limpar_valor_monetario(ws.cell(numero_linha, col_valor).value)
                    if col_valor is not None else 0.0
                )
                if valor_consolidado < 0:
                    coluna_regra = 'debito'
                    valores_regra = (
                        {'', '0'} if empresa_classificacao == 'eletro_forte_filial_1408'
                        else {'0', '166'}
                    )
                elif valor_consolidado > 0:
                    coluna_regra = 'credito'
                    valores_regra = (
                        {'', '0'} if empresa_classificacao == 'eletro_forte_filial_1408'
                        else {'', '0', '14', '16', '166'}
                    )
                else:
                    resumo['preservados_regra'] += 1
                    continue
            if coluna_regra in {'debito', 'credito'}:
                atual_regra = debito_atual if coluna_regra == 'debito' else credito_atual
                if atual_regra not in valores_regra:
                    resumo['preservados_regra'] += 1
                    resumo['ja_preenchidos'] += 1
                    continue
                resumo['elegiveis_regra'] += 1
                if coluna_regra == 'debito':
                    ws.cell(numero_linha, col_debito).value = None
                    debito_atual = ''
                else:
                    ws.cell(numero_linha, col_credito).value = None
                    credito_atual = ''
            elif debito_atual and credito_atual:
                resumo['ja_preenchidos'] += 1
                continue
            linha_estava_parcial = bool(debito_atual or credito_atual)

            descricao_linha = (
                ws.cell(numero_linha, col_descricao).value
                if col_descricao is not None else ''
            )
            if empresa_classificacao.startswith('eletro_forte'):
                banco_linha = identificar_banco_classificacao_eletro_forte(
                    ws.title, descricao_linha, debito_atual, credito_atual
                )
            else:
                banco_linha = (
                    identificar_chave_banco_empresa(descricao_linha)
                    if col_descricao is not None else ''
                ) or banco_aba
            if banco_linha not in contas_bancarias:
                resumo['banco_nao_identificado'] += 1
                continue

            assinatura = criar_assinatura_classificacao(historico)

            # REGRA PRINCIPAL: o sinal do VALOR decide a natureza.
            # Nunca usamos uma palavra perdida no histórico para decidir se o banco
            # entra no débito ou no crédito.
            valor_linha = (
                limpar_valor_monetario(ws.cell(numero_linha, col_valor).value)
                if col_valor is not None else 0.0
            )
            if valor_linha < 0:
                natureza = 'pago'
            elif valor_linha > 0:
                natureza = 'recebido'
            else:
                natureza = assinatura.split('|', 1)[0] if assinatura else ''

            # A assinatura usada para procurar a contrapartida também recebe a
            # natureza definida pelo sinal, evitando que "pago" dentro do histórico
            # faça um recebimento buscar padrões de pagamento (e vice-versa).
            if assinatura and natureza in {'pago', 'recebido'}:
                partes_assinatura = assinatura.split('|', 1)
                sufixo_assinatura = partes_assinatura[1] if len(partes_assinatura) > 1 else ''
                assinatura = (
                    f"{natureza}|{sufixo_assinatura}" if sufixo_assinatura else natureza
                )

            conta_banco = contas_bancarias[banco_linha]
            if natureza == 'pago':
                if not credito_atual:
                    ws.cell(numero_linha, col_credito).value = valor_conta_excel(conta_banco)
                coluna_contrapartida = col_debito
            elif natureza == 'recebido':
                if not debito_atual:
                    ws.cell(numero_linha, col_debito).value = valor_conta_excel(conta_banco)
                coluna_contrapartida = col_credito
            else:
                resumo['padroes_novos'] += 1
                continue

            contrapartida_atual = texto_celula_seguro(
                ws.cell(numero_linha, coluna_contrapartida).value
            )
            if contrapartida_atual:
                resumo['automaticos'] += 1
                if linha_estava_parcial:
                    resumo['parciais_completados'] += 1
                continue

            candidatos_banco = candidatos_por_banco.get(banco_linha, {})
            mapas_banco = mapas_seguros.get(banco_linha, {})
            candidatos = candidatos_banco.get(assinatura, set())
            conta_segura = mapas_banco.get(assinatura)

            # Quando a base foi aprendida a partir de histórico cru da Autokraft,
            # a assinatura fica "outro|...". Mantemos o restante da assinatura e
            # localizamos esse padrão também.
            if not candidatos and assinatura:
                partes_assinatura = assinatura.split('|', 1)
                sufixo_assinatura = partes_assinatura[1] if len(partes_assinatura) > 1 else ''
                assinatura_outro = f"outro|{sufixo_assinatura}" if sufixo_assinatura else assinatura
                candidatos = candidatos_banco.get(assinatura_outro, set())
                conta_segura = mapas_banco.get(assinatura_outro)
            conta_fixa_accede = (
                identificar_conta_folha_accede_1000(historico)
                if empresa_classificacao == 'accede_automacao'
                and natureza == 'pago'
                else ''
            )
            if conta_fixa_accede:
                ws.cell(
                    numero_linha, coluna_contrapartida
                ).value = valor_conta_excel(conta_fixa_accede)
                resumo['automaticos'] += 1
                resumo['regras_fixas_1000'] += 1
                if linha_estava_parcial:
                    resumo['parciais_completados'] += 1
            elif 'antecipad' in normalizar_texto(historico):
                ws.cell(numero_linha, coluna_contrapartida).value = 532
                resumo['automaticos'] += 1
                resumo['antecipados'] += 1
                if linha_estava_parcial:
                    resumo['parciais_completados'] += 1
            elif conta_segura:
                ws.cell(numero_linha, coluna_contrapartida).value = valor_conta_excel(
                    conta_segura
                )
                resumo['automaticos'] += 1
                if linha_estava_parcial:
                    resumo['parciais_completados'] += 1
            elif len(candidatos) > 1:
                resumo['conflitos'] += 1
                resumo['somente_banco'] += 1
            else:
                chave_cache = (banco_linha, natureza, assinatura)
                if chave_cache not in cache_similaridade:
                    cache_similaridade[chave_cache] = encontrar_conta_por_nome_historico(
                        historico,
                        natureza,
                        evidencias_nomes_por_banco.get(banco_linha, {})
                    )
                conta_similar, _, motivo_nome = cache_similaridade[chave_cache]
                if conta_similar:
                    ws.cell(numero_linha, coluna_contrapartida).value = valor_conta_excel(
                        conta_similar
                    )
                    resumo['automaticos'] += 1
                    resumo['por_nome_empresa'] += 1
                    if linha_estava_parcial:
                        resumo['parciais_completados'] += 1
                else:
                    if motivo_nome == 'conflito':
                        resumo['conflitos'] += 1
                    else:
                        resumo['padroes_novos'] += 1
                    resumo['somente_banco'] += 1

    if resumo['abas_processadas'] == 0:
        raise ValueError(
            'Nenhuma aba com as colunas HISTÓRICO, DÉBITO e CRÉDITO foi encontrada.'
        )

    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue(), resumo

def extrair_pendencias_revisao_inteligente(file_bytes, contas_bancarias):
    """Lista somente lançamentos que ainda precisam da conta de contrapartida."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(file_bytes), data_only=False)
    pendencias = []
    contas_bancarias = contas_bancarias or {}

    for ws in wb.worksheets:
        if 'retir' in normalizar_texto(ws.title):
            continue

        linha_cabecalho = None
        mapa_colunas = {}
        for numero_linha in range(1, min(ws.max_row, 30) + 1):
            mapa_teste = {
                normalizar_texto(texto_celula_seguro(ws.cell(numero_linha, coluna).value)).strip(): coluna
                for coluna in range(1, ws.max_column + 1)
            }
            if all(nome in mapa_teste for nome in ['historico', 'debito', 'credito']):
                linha_cabecalho = numero_linha
                mapa_colunas = mapa_teste
                break
        if linha_cabecalho is None:
            continue

        col_hist = mapa_colunas['historico']
        col_debito = mapa_colunas['debito']
        col_credito = mapa_colunas['credito']
        col_valor = mapa_colunas.get('valor')
        col_data = mapa_colunas.get('data')
        col_descricao = mapa_colunas.get('descricao')
        banco_aba = identificar_chave_banco_empresa(ws.title)

        for numero_linha in range(linha_cabecalho + 1, ws.max_row + 1):
            historico = texto_celula_seguro(ws.cell(numero_linha, col_hist).value)
            if not historico:
                continue

            banco = (
                identificar_chave_banco_empresa(ws.cell(numero_linha, col_descricao).value)
                if col_descricao is not None else ''
            ) or banco_aba
            if banco not in contas_bancarias:
                continue

            debito = texto_celula_seguro(ws.cell(numero_linha, col_debito).value)
            credito = texto_celula_seguro(ws.cell(numero_linha, col_credito).value)
            if debito and credito:
                continue

            assinatura = criar_assinatura_classificacao(historico)
            valor = 0.0
            if col_valor is not None:
                valor = limpar_valor_monetario(ws.cell(numero_linha, col_valor).value)

            # A Revisão Inteligente segue exatamente a mesma regra da classificação.
            if valor < 0:
                natureza = 'pago'
            elif valor > 0:
                natureza = 'recebido'
            else:
                natureza = assinatura.split('|', 1)[0] if assinatura else ''

            if natureza == 'pago':
                coluna_destino = col_debito
                coluna_banco = col_credito
                lado = 'DÉBITO'
            elif natureza == 'recebido':
                coluna_destino = col_credito
                coluna_banco = col_debito
                lado = 'CRÉDITO'
            else:
                continue

            contrapartida_atual = texto_celula_seguro(
                ws.cell(numero_linha, coluna_destino).value
            )
            if contrapartida_atual:
                continue

            data_texto = ''
            if col_data is not None:
                data_raw = ws.cell(numero_linha, col_data).value
                data_parseada = pd.to_datetime(data_raw, dayfirst=True, errors='coerce')
                if not pd.isna(data_parseada):
                    data_texto = data_parseada.strftime('%d/%m/%Y')
                else:
                    data_texto = texto_celula_seguro(data_raw)

            pendencias.append({
                'Banco': nome_banco_por_chave(banco),
                'Data': data_texto,
                'Valor': valor,
                'Histórico': historico,
                'Classificar em': lado,
                'Conta bancária': texto_celula_seguro(contas_bancarias.get(banco, '')),
                'Conta da contrapartida': '',
                '_aba': ws.title,
                '_linha': numero_linha,
                '_col_destino': coluna_destino,
                '_col_banco': coluna_banco,
                '_banco': banco,
                '_col_data': col_data or 0,
            })

    return pd.DataFrame(pendencias)

def aplicar_revisoes_inteligentes(
    file_bytes, revisoes, filename, empresa, contas_bancarias
):
    """Aplica as contas revisadas e gera somente os novos padrões confirmados pelo usuário."""
    from openpyxl import load_workbook

    if revisoes is None or revisoes.empty:
        return file_bytes, 0, []

    wb = load_workbook(io.BytesIO(file_bytes))
    registros = []
    aplicadas = 0

    def valor_conta_excel(conta):
        texto = texto_celula_seguro(conta)
        if texto.isdigit() and (texto == '0' or not texto.startswith('0')):
            return int(texto)
        return texto

    for _, item in revisoes.iterrows():
        conta_contrapartida = texto_celula_seguro(item.get('Conta da contrapartida'))
        if not conta_contrapartida:
            continue

        nome_aba = texto_celula_seguro(item.get('_aba'))
        if nome_aba not in wb.sheetnames:
            continue
        ws = wb[nome_aba]
        numero_linha = int(item.get('_linha'))
        col_destino = int(item.get('_col_destino'))
        col_banco = int(item.get('_col_banco'))
        banco = texto_celula_seguro(item.get('_banco'))
        conta_banco = texto_celula_seguro(contas_bancarias.get(banco, ''))

        if conta_banco and not texto_celula_seguro(ws.cell(numero_linha, col_banco).value):
            ws.cell(numero_linha, col_banco).value = valor_conta_excel(conta_banco)
        ws.cell(numero_linha, col_destino).value = valor_conta_excel(conta_contrapartida)
        aplicadas += 1

        # Lê o par final exatamente como ficou na planilha e aprende somente esta revisão.
        mapa_colunas = {}
        linha_cabecalho = None
        for linha_teste in range(1, min(ws.max_row, 30) + 1):
            mapa_teste = {
                normalizar_texto(texto_celula_seguro(ws.cell(linha_teste, coluna).value)).strip(): coluna
                for coluna in range(1, ws.max_column + 1)
            }
            if all(nome in mapa_teste for nome in ['historico', 'debito', 'credito']):
                mapa_colunas = mapa_teste
                linha_cabecalho = linha_teste
                break
        if linha_cabecalho is None:
            continue

        historico = texto_celula_seguro(ws.cell(numero_linha, mapa_colunas['historico']).value)
        debito = texto_celula_seguro(ws.cell(numero_linha, mapa_colunas['debito']).value)
        credito = texto_celula_seguro(ws.cell(numero_linha, mapa_colunas['credito']).value)
        assinatura = criar_assinatura_classificacao(historico)
        if not assinatura or not debito or not credito:
            continue

        periodo = normalizar_texto(filename)
        col_data = mapa_colunas.get('data')
        if col_data is not None:
            data_lancamento = pd.to_datetime(
                ws.cell(numero_linha, col_data).value, dayfirst=True, errors='coerce'
            )
            if not pd.isna(data_lancamento):
                periodo = data_lancamento.strftime('%Y-%m')

        identificador = hashlib.sha256(
            f"{empresa}|{banco}|{assinatura}|{debito}|{credito}".encode('utf-8')
        ).hexdigest()
        registros.append({
            'id': identificador,
            'empresa': empresa,
            'banco': banco,
            'assinatura': assinatura,
            'debito': debito,
            'credito': credito,
            'ocorrencias': 1,
            'periodos': [periodo],
            'exemplo_historico': historico[:500]
        })

    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue(), aplicadas, registros

def processar_nova_geracao_banco(file_bytes, nome_aba, conta_esperada, descricao_banco):
    """Localiza uma conta na planilha consolidada e transforma seus lançamentos."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    conta_normalizada = re.sub(r'\D', '', conta_esperada)

    df, colunas = None, None
    for aba_candidata in xls.sheet_names:
        df_candidata = pd.read_excel(xls, sheet_name=aba_candidata, dtype=object)
        mapa = {normalizar_texto(str(col)).strip(): col for col in df_candidata.columns}
        obrigatorias = ['conta', 'data', 'valor', 'lacto', 'historico', 'doc']
        if not all(nome in mapa for nome in obrigatorias):
            continue
        contas_aba = df_candidata[mapa['conta']].apply(
            lambda valor: re.sub(r'\D', '', texto_celula_seguro(valor))
        )
        if contas_aba.eq(conta_normalizada).any():
            df = df_candidata
            colunas = mapa
            break

    if df is None or colunas is None:
        raise ValueError(
            f"A conta {conta_esperada} ({nome_aba}) não foi encontrada em nenhuma aba "
            "válida da planilha consolidada."
        )

    col_conta = colunas['conta']
    col_data = colunas['data']
    col_valor = colunas['valor']
    col_lacto = colunas['lacto']
    col_hist = colunas['historico']
    col_doc = colunas['doc']
    col_tipo = colunas.get('tipo')

    colunas_saida = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
    principais, retirados = [], []

    for _, linha in df.iterrows():
        conta = re.sub(r'\D', '', texto_celula_seguro(linha[col_conta]))
        if conta != conta_normalizada:
            continue

        data_raw = linha[col_data]
        if isinstance(data_raw, (int, float)) and not pd.isna(data_raw):
            data = pd.to_datetime(data_raw, unit='D', origin='1899-12-30', errors='coerce')
        else:
            data = pd.to_datetime(data_raw, dayfirst=True, errors='coerce')
        if pd.isna(data):
            continue

        lacto_original = texto_celula_seguro(linha[col_lacto])
        lacto_normalizado = normalizar_texto(lacto_original).strip()
        lacto = re.sub(r'\bPAGAR\b', 'PAGO', lacto_original, flags=re.IGNORECASE)
        lacto = re.sub(
            r'\b(?:RECEBER|RECEBIMENTO)\b', 'RECEBIDO', lacto, flags=re.IGNORECASE
        )

        valor_raw = linha[col_valor]
        valor_original = (
            float(valor_raw)
            if isinstance(valor_raw, (int, float)) and not pd.isna(valor_raw)
            else limpar_valor_monetario(valor_raw)
        )
        if valor_original == 0:
            continue

        tipo_normalizado = normalizar_texto(texto_celula_seguro(linha[col_tipo])) if col_tipo else ''
        if lacto_normalizado.startswith(('pagar', 'pago')):
            valor = -abs(valor_original)
        elif lacto_normalizado.startswith(('receber', 'recebido', 'recebimento')):
            valor = abs(valor_original)
        elif 'debito' in tipo_normalizado:
            valor = -abs(valor_original)
        elif 'credito' in tipo_normalizado:
            valor = abs(valor_original)
        else:
            valor = valor_original

        historico_valor_original = linha[col_hist]
        historico_origem_exato = (
            '' if historico_valor_original is None or pd.isna(historico_valor_original)
            else limpar_caracteres_ilegais(str(historico_valor_original))
        )
        historico_origem = texto_celula_seguro(historico_valor_original)
        documento = texto_celula_seguro(linha[col_doc])

        # Empresas 266 e 1396 (Nova Geração): preserva o PAGO/RECEBIDO que já
        # vem do campo LACTO, mas não adiciona o prefixo extra "Pago:"/"Recebido:".
        # Se o histórico de origem já vier com esse prefixo com dois-pontos,
        # removemos apenas ele para evitar duplicidade como "PAGO Pago: ...".
        historico_origem_limpo = re.sub(
            r'^(?:Pago|Recebido)\s*:\s*',
            '',
            historico_origem,
            flags=re.IGNORECASE,
        ).strip()
        historico_final = re.sub(r'\s+', ' ', " ".join(
            parte for parte in [lacto, historico_origem_limpo, documento] if parte
        )).strip()

        registro = {
            'DESCRIÇÃO': descricao_banco,
            'DATA': data.to_pydatetime(),
            'VALOR': valor,
            'DÉBITO': '',
            'CRÉDITO': '',
            'HISTÓRICO': historico_final
        }

        if identificar_estorno_de_baixa(lacto_original, historico_origem, documento):
            registro_retirado = dict(registro)
            registro_retirado['HISTÓRICO'] = historico_origem_exato
            registro_retirado['MOTIVO'] = 'Estorno de baixa identificado'
            retirados.append(registro_retirado)
        else:
            principais.append(registro)

    if not principais and not retirados:
        raise ValueError(f"Nenhum lançamento da conta {nome_aba} {conta_esperada} foi encontrado.")

    return pd.DataFrame(principais, columns=colunas_saida), pd.DataFrame(
        retirados, columns=colunas_saida + ['MOTIVO']
    )

def processar_nova_geracao_itau(file_bytes):
    return processar_nova_geracao_banco(
        file_bytes, 'Itaú', '99549-5', 'BANCO ITAÚ'
    )

def processar_nova_geracao_bradesco(file_bytes):
    return processar_nova_geracao_banco(
        file_bytes, 'Bradesco', '451990-6', 'BANCO BRADESCO'
    )

def processar_nova_geracao_fibra(file_bytes):
    return processar_nova_geracao_banco(
        file_bytes, 'Fibra', '673947-1', 'BANCO FIBRA'
    )

def processar_nova_geracao_filial_itau(file_bytes):
    return processar_nova_geracao_banco(
        file_bytes, 'Itaú', '98002-6', 'BANCO ITAÚ'
    )

def processar_nova_geracao_filial_bradesco(file_bytes):
    return processar_nova_geracao_banco(
        file_bytes, 'Bradesco', '3084-8', 'BANCO BRADESCO'
    )

def processar_mapa_autokraft(file_bytes, filename=''):
    """Converte as abas diárias do mapa Autokraft para o Modelo Domínio."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    # Os mapas da Autokraft existem em dois padrões de nome de aba:
    # arquivos antigos usam DD.MM e arquivos mais novos usam DD-MM.
    # Aceitamos ambos sem incluir abas auxiliares de pagamentos/adiantamentos.
    abas_diarias = [
        aba for aba in xls.sheet_names
        if re.fullmatch(r'\d{2}[.-]\d{2}', str(aba).strip())
    ]
    if not abas_diarias:
        raise ValueError(
            "Nenhuma aba diária no formato DD-MM ou DD.MM foi encontrada no arquivo enviado."
        )

    ano_nome = re.search(r'(?<!\d)(20\d{2})(?!\d)', str(filename))
    ano_referencia = int(ano_nome.group(1)) if ano_nome else datetime.now().year
    colunas_saida = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
    registros = {'Itaú': [], 'Daycoval': []}
    abas_processadas = []

    for nome_aba in abas_diarias:
        df = pd.read_excel(xls, sheet_name=nome_aba, header=None, dtype=object)
        if df.empty or df.shape[1] < 6:
            continue

        data_raw = df.iloc[1, 2] if len(df.index) > 1 and df.shape[1] > 2 else None
        if isinstance(data_raw, (int, float)) and not pd.isna(data_raw):
            data_aba = pd.to_datetime(
                data_raw, unit='D', origin='1899-12-30', errors='coerce'
            )
        else:
            data_aba = pd.to_datetime(data_raw, dayfirst=True, errors='coerce')
        if pd.isna(data_aba):
            partes_data = re.split(r'[.-]', str(nome_aba).strip())
            if len(partes_data) != 2:
                continue
            dia, mes = [int(parte) for parte in partes_data]
            data_aba = pd.Timestamp(year=ano_referencia, month=mes, day=dia)

        banco_atual = None
        for _, linha in df.iterrows():
            nome_bloco = normalizar_texto(texto_celula_seguro(linha.iloc[0])).strip()
            if nome_bloco == 'itau':
                banco_atual = 'Itaú'
            elif nome_bloco == 'daycoval':
                banco_atual = 'Daycoval'

            historico_credito = texto_celula_seguro(linha.iloc[2])
            historico_debito = texto_celula_seguro(linha.iloc[4])
            texto_credito = normalizar_texto(historico_credito)
            texto_debito = normalizar_texto(historico_debito)

            if texto_credito.startswith('total de creditos') or texto_debito.startswith(
                'total de debitos'
            ):
                banco_atual = None
                continue
            if banco_atual is None:
                continue

            if historico_credito and not texto_credito.startswith('total'):
                valor_credito = abs(limpar_valor_monetario(linha.iloc[3]))
                if valor_credito:
                    historico_credito_final = limpar_caracteres_ilegais(
                        historico_credito
                    ).strip()
                    registros[banco_atual].append({
                        'DESCRIÇÃO': f'BANCO {banco_atual.upper()}',
                        'DATA': data_aba.to_pydatetime(),
                        'VALOR': valor_credito,
                        'DÉBITO': '',
                        'CRÉDITO': '',
                        'HISTÓRICO': f'Recebido: {historico_credito_final}'
                    })

            if historico_debito and not texto_debito.startswith('total'):
                valor_debito = abs(limpar_valor_monetario(linha.iloc[5]))
                if valor_debito:
                    historico_debito_final = limpar_caracteres_ilegais(
                        historico_debito
                    ).strip()
                    registros[banco_atual].append({
                        'DESCRIÇÃO': f'BANCO {banco_atual.upper()}',
                        'DATA': data_aba.to_pydatetime(),
                        'VALOR': -valor_debito,
                        'DÉBITO': '',
                        'CRÉDITO': '',
                        'HISTÓRICO': f'Pago: {historico_debito_final}'
                    })

        abas_processadas.append(str(nome_aba))

    dados_por_banco = {}
    for nome_banco, linhas in registros.items():
        df_banco = pd.DataFrame(linhas, columns=colunas_saida)
        if not df_banco.empty:
            df_banco = df_banco.sort_values('DATA', kind='stable').reset_index(drop=True)
        dados_por_banco[nome_banco] = {
            'principal': df_banco,
            'retirados': pd.DataFrame(columns=colunas_saida + ['MOTIVO'])
        }

    total_lancamentos = sum(
        len(dados['principal']) for dados in dados_por_banco.values()
    )
    if total_lancamentos == 0:
        raise ValueError(
            "As abas diárias foram encontradas, mas nenhum lançamento bancário válido foi lido."
        )
    return dados_por_banco, abas_processadas

def processar_planilha_accede_sig(file_bytes, banco_nome, empresa=''):
    """
    Converte planilhas SIG da ACCEDE para o Modelo Domínio.

    Regra estrutural: uma linha com DATA inicia o lançamento/grupo. Todas as linhas
    seguintes sem DATA pertencem a esse grupo até surgir uma nova DATA. Quando há
    detalhamento com valor individual, o total da linha principal não é duplicado.
    """
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    colunas_saida = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
    registros = []

    def texto_exato(valor):
        if valor is None or pd.isna(valor):
            return ''
        if isinstance(valor, float) and valor.is_integer():
            return str(int(valor))
        return limpar_caracteres_ilegais(str(valor)).strip()

    for nome_aba in xls.sheet_names:
        bruto = pd.read_excel(xls, sheet_name=nome_aba, header=None, dtype=object)
        if bruto.empty:
            continue

        idx_header = None
        nomes_header = None
        for idx in range(min(len(bruto), 30)):
            nomes = [normalizar_texto(texto_celula_seguro(v)).strip() for v in bruto.iloc[idx].tolist()]
            if all(nome in nomes for nome in ['data', 'complemento', 'entrada', 'saida']):
                idx_header = idx
                nomes_header = nomes
                break
        if idx_header is None:
            continue

        def coluna(nome):
            return nomes_header.index(nome) if nome in nomes_header else None

        c_data = coluna('data')
        c_dc = coluna('d/c')
        c_comp = coluna('complemento')
        c_conf = coluna('conf')
        c_ent = coluna('entrada')
        c_sai = coluna('saida')
        linhas = bruto.iloc[idx_header + 1:].reset_index(drop=True)
        i = 0

        while i < len(linhas):
            principal = linhas.iloc[i]
            data = pd.to_datetime(principal.iloc[c_data], dayfirst=True, errors='coerce')
            if pd.isna(data):
                i += 1
                continue

            j = i + 1
            detalhes = []
            while j < len(linhas):
                proxima_data = pd.to_datetime(linhas.iloc[j].iloc[c_data], dayfirst=True, errors='coerce')
                if not pd.isna(proxima_data):
                    break
                valores_linha = [texto_celula_seguro(v) for v in linhas.iloc[j].tolist()]
                if any(valores_linha):
                    detalhes.append(linhas.iloc[j])
                j += 1

            entrada = abs(limpar_valor_monetario(principal.iloc[c_ent])) if c_ent is not None else 0.0
            saida = abs(limpar_valor_monetario(principal.iloc[c_sai])) if c_sai is not None else 0.0
            sinal_grupo = 1 if entrada else (-1 if saida else 0)
            dc_principal = texto_exato(principal.iloc[c_dc]) if c_dc is not None else ''
            complemento = texto_exato(principal.iloc[c_comp]) if c_comp is not None else ''
            conf_principal = texto_exato(principal.iloc[c_conf]) if c_conf is not None else ''
            descricao_banco = 'BANCO ITAÚ' if normalizar_texto(banco_nome) == 'itau' else 'SICREDI'

            detalhes_validos = []
            for detalhe in detalhes:
                # Nos SIGs ACCEDE os detalhes aparecem deslocados para a esquerda:
                # [vazio/data, Conf/Documento, Valor, Favorecido/Descrição, ...].
                conf_doc = texto_exato(detalhe.iloc[1]) if len(detalhe) > 1 else ''
                valor_individual = abs(limpar_valor_monetario(detalhe.iloc[2])) if len(detalhe) > 2 else 0.0
                favorecido = texto_exato(detalhe.iloc[3]) if len(detalhe) > 3 else ''
                if valor_individual:
                    detalhes_validos.append((conf_doc, valor_individual, favorecido))

            if detalhes_validos:
                for conf_doc, valor_individual, favorecido in detalhes_validos:
                    historico = ' '.join(parte for parte in [favorecido, conf_doc] if parte).strip()
                    if not historico:
                        historico = complemento or conf_principal or dc_principal or 'MOVIMENTO BANCARIO'
                    registros.append({
                        'DESCRIÇÃO': descricao_banco,
                        'DATA': data.to_pydatetime(),
                        'VALOR': round(valor_individual * (sinal_grupo or -1), 2),
                        'DÉBITO': '',
                        'CRÉDITO': '',
                        'HISTÓRICO': historico
                    })
            else:
                valor = entrada if entrada else (-saida if saida else 0.0)
                if valor:
                    historico = complemento or conf_principal or dc_principal or 'MOVIMENTO BANCARIO'
                    registros.append({
                        'DESCRIÇÃO': descricao_banco,
                        'DATA': data.to_pydatetime(),
                        'VALOR': round(valor, 2),
                        'DÉBITO': '',
                        'CRÉDITO': '',
                        'HISTÓRICO': historico
                    })
            i = j

    df = pd.DataFrame(registros, columns=colunas_saida)
    if df.empty:
        raise ValueError(f'Nenhum lançamento válido foi encontrado na planilha SIG do {banco_nome}.')
    df = df.sort_values('DATA', kind='stable').reset_index(drop=True)
    if empresa == 'accede_automacao':
        conta_bancaria = CONFIGURACOES_ACCEDE[empresa]['contas_bancarias'][
            normalizar_texto(banco_nome)
        ]
        df = aplicar_regras_accede_1000(df, conta_bancaria)
    return df

def filtrar_dataframe_periodo(df, data_inicial, data_final):
    """Mantém somente os lançamentos entre as datas informadas, inclusive."""
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if 'DATA' not in df.columns:
        return df.iloc[0:0].copy()
    # Extratos brasileiros usam dia/mês/ano. Sem dayfirst=True, por exemplo,
    # 01/04/2026 seria interpretado como 4 de janeiro e sairia do filtro de abril.
    datas = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.date
    mascara = datas.between(data_inicial, data_final, inclusive='both')
    return df.loc[mascara].copy().reset_index(drop=True)

def identificar_chave_banco_empresa(valor):
    """Identifica os bancos conhecidos por descrição, aba, arquivo ou conta."""
    texto = normalizar_texto(texto_celula_seguro(valor))
    digitos = re.sub(r'\D', '', texto_celula_seguro(valor))
    if 'btg' in texto or 'pactual' in texto or '5606318' in digitos:
        return 'btg'
    if 'itau' in texto or any(conta in digitos for conta in ['995495', '980026']):
        return 'itau'
    if 'bradesco' in texto or any(conta in digitos for conta in ['4519906', '30848']):
        return 'bradesco'
    if 'fibra' in texto or '6739471' in digitos:
        return 'fibra'
    if 'daycoval' in texto:
        return 'daycoval'
    if 'sicredi' in texto:
        return 'sicredi'
    if 'santander' in texto:
        return 'santander'
    if 'banco do brasil' in texto:
        return 'banco_brasil'
    return ''

def nome_banco_por_chave(chave):
    return {
        'btg': 'BTG',
        'itau': 'Itaú', 'bradesco': 'Bradesco', 'fibra': 'Fibra',
        'daycoval': 'Daycoval', 'sicredi': 'Sicredi',
        'santander': 'Santander', 'banco_brasil': 'Banco do Brasil'
    }.get(chave, chave)

def ler_planilha_organizada_conferencia(file_bytes, banco_alvo, conta_alvo=None):
    """Lê a planilha final e retorna somente o banco escolhido para conferência."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    # Aceita aliases de banco (como itau_hw88), comparando pelo banco real.
    banco_alvo = 'itau' if str(banco_alvo).lower().startswith('itau') else banco_alvo
    colunas_base = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
    principais, retirados, bancos_encontrados = [], [], set()

    for nome_aba in xls.sheet_names:
        df_bruto = pd.read_excel(xls, sheet_name=nome_aba, header=None, dtype=object)
        if df_bruto.empty:
            continue

        indice_cabecalho = None
        for indice in range(min(len(df_bruto), 30)):
            nomes_linha = [
                normalizar_texto(texto_celula_seguro(valor)).strip()
                for valor in df_bruto.iloc[indice].tolist()
            ]
            if ('data' in nomes_linha and 'valor' in nomes_linha and
                    any(nome in nomes_linha for nome in ['historico', 'histórico'])):
                indice_cabecalho = indice
                break
        if indice_cabecalho is None:
            continue

        cabecalhos = [texto_celula_seguro(valor) for valor in df_bruto.iloc[indice_cabecalho]]
        df_aba = df_bruto.iloc[indice_cabecalho + 1:].copy()
        df_aba.columns = cabecalhos
        mapa = {normalizar_texto(str(coluna)).strip(): coluna for coluna in df_aba.columns}
        col_data = mapa.get('data')
        col_valor = mapa.get('valor')
        col_hist = mapa.get('historico')
        col_desc = mapa.get('descricao')
        col_motivo = mapa.get('motivo')
        col_debito = mapa.get('debito')
        col_credito = mapa.get('credito')
        if col_data is None or col_valor is None or col_hist is None:
            continue

        banco_aba = identificar_chave_banco_empresa(nome_aba)
        aba_retirados = 'retir' in normalizar_texto(nome_aba)
        for _, linha in df_aba.iterrows():
            if conta_alvo:
                contas_linha = {
                    re.sub(r'\D', '', texto_celula_seguro(linha[coluna]))
                    for coluna in [col_debito, col_credito]
                    if coluna is not None
                }
                conta_normalizada = re.sub(r'\D', '', str(conta_alvo))
                if conta_normalizada not in contas_linha:
                    continue
            banco_linha = (
                identificar_chave_banco_empresa(linha[col_desc]) if col_desc is not None else ''
            ) or banco_aba
            if banco_linha:
                bancos_encontrados.add(banco_linha)
            if banco_linha != banco_alvo:
                continue

            data_raw = linha[col_data]
            if pd.api.types.is_number(data_raw) and not pd.isna(data_raw):
                data = pd.to_datetime(float(data_raw), unit='D', origin='1899-12-30', errors='coerce')
            else:
                data = pd.to_datetime(data_raw, dayfirst=True, errors='coerce')
            valor = limpar_valor_monetario(linha[col_valor])
            if pd.isna(data) or valor == 0:
                continue

            descricao = texto_celula_seguro(linha[col_desc]) if col_desc is not None else ''
            if not descricao:
                descricao = {
                    'btg': 'BANCO BTG',
                    'itau': 'BANCO ITAÚ', 'bradesco': 'BANCO BRADESCO',
                    'fibra': 'BANCO FIBRA', 'daycoval': 'BANCO DAYCOVAL',
                    'sicredi': 'SICREDI', 'santander': 'BANCO SANTANDER',
                    'banco_brasil': 'BANCO DO BRASIL'
                }[banco_alvo]
            historico_valor = linha[col_hist]
            historico = (
                '' if historico_valor is None or pd.isna(historico_valor)
                else limpar_caracteres_ilegais(str(historico_valor))
            )
            registro = {
                'DESCRIÇÃO': descricao,
                'DATA': data.to_pydatetime(),
                'VALOR': valor,
                'DÉBITO': '',
                'CRÉDITO': '',
                'HISTÓRICO': historico
            }
            if aba_retirados:
                registro['MOTIVO'] = (
                    texto_celula_seguro(linha[col_motivo]) if col_motivo is not None
                    else 'Estorno de baixa identificado'
                )
                retirados.append(registro)
            else:
                principais.append(registro)

    # A conferência das empresas Autokraft/I.S.A também aceita o próprio mapa
    # bancário com abas diárias DD-MM ou DD.MM. Se ele não tiver o cabeçalho do
    # Modelo Domínio, reutiliza o mesmo leitor já usado pelo organizador.
    if not principais and banco_alvo in {'itau', 'daycoval'}:
        try:
            dados_mapa, _ = processar_mapa_autokraft(file_bytes)
            nome_mapa = 'Itaú' if banco_alvo == 'itau' else 'Daycoval'
            bloco_mapa = dados_mapa.get(nome_mapa, {})
            principal_mapa = bloco_mapa.get('principal', pd.DataFrame()).copy()
            retirados_mapa = bloco_mapa.get('retirados', pd.DataFrame()).copy()
            bancos_mapa = [
                nome for nome, dados in dados_mapa.items()
                if not dados.get('principal', pd.DataFrame()).empty
            ]
            if not principal_mapa.empty:
                return principal_mapa, retirados_mapa, bancos_mapa
        except Exception:
            # Não era um mapa diário: mantém o resultado normal do leitor do
            # Modelo Domínio e deixa a interface informar a ausência de dados.
            pass

    return (
        pd.DataFrame(principais, columns=colunas_base),
        pd.DataFrame(retirados, columns=colunas_base + ['MOTIVO']),
        [nome_banco_por_chave(chave) for chave in sorted(bancos_encontrados)]
    )

def gerar_excel_nova_geracao(dados_por_banco, modelo_bytes=None, prefixar_historicos=True):
    """Gera um único arquivo com uma aba do Modelo Domínio para cada banco.

    prefixar_historicos=False é exclusivo dos fluxos em que o histórico já traz
    PAGO/RECEBIDO da origem, como Nova Geração 266 e 1396.
    """
    from openpyxl import Workbook, load_workbook

    if modelo_bytes:
        wb = load_workbook(io.BytesIO(modelo_bytes))
        ws_modelo = wb[wb.sheetnames[0]]
        if ws_modelo.max_row > 1:
            ws_modelo.delete_rows(2, ws_modelo.max_row - 1)
    else:
        wb = Workbook()
        ws_modelo = wb.active
        ws_modelo.title = 'Modelo temporário'
        ws_modelo.append(['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO'])

    cabecalhos = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
    for col, cabecalho in enumerate(cabecalhos, 1):
        ws_modelo.cell(1, col, cabecalho)

    def preparar_linha_modelo(registro, colunas):
        linha = []
        for coluna in colunas:
            valor = registro.get(coluna, '')
            if coluna == 'DATA':
                data = pd.to_datetime(valor, errors='coerce')
                valor = data.strftime('%d/%m/%Y') if not pd.isna(data) else ''
            elif coluna == 'HISTÓRICO' and prefixar_historicos:
                valor = prefixar_historico_movimento(
                    valor, registro.get('VALOR', 0)
                )
            elif pd.isna(valor):
                valor = ''
            linha.append(valor)
        return linha

    nomes_criados = []
    retirados_gerais = []
    for nome_banco, dados_banco in dados_por_banco.items():
        nome_aba = str(nome_banco)[:31]
        if nome_aba in nomes_criados:
            sufixo = 2
            while f"{nome_aba[:28]} {sufixo}" in nomes_criados:
                sufixo += 1
            nome_aba = f"{nome_aba[:28]} {sufixo}"

        ws_banco = wb.copy_worksheet(ws_modelo)
        ws_banco.title = nome_aba
        nomes_criados.append(nome_aba)

        df_principal = dados_banco.get('principal', pd.DataFrame())
        df_retirados = dados_banco.get('retirados', pd.DataFrame())
        for registro in df_principal.to_dict('records'):
            ws_banco.append(preparar_linha_modelo(registro, cabecalhos))
        if not df_retirados.empty:
            retirados_gerais.extend(df_retirados.to_dict('records'))

    wb.remove(ws_modelo)

    if retirados_gerais:
        nome_retirados = 'Lançamentos retirados'
        if nome_retirados in wb.sheetnames:
            del wb[nome_retirados]
        ws_ret = wb.create_sheet(nome_retirados)
        cabecalhos_ret = cabecalhos + ['MOTIVO']
        ws_ret.append(cabecalhos_ret)
        for registro in retirados_gerais:
            ws_ret.append(preparar_linha_modelo(registro, cabecalhos_ret))

    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()

def processar_pdf_bradesco_mensal(reader, banco='BANCO BRADESCO'):
    """Lê extratos mensais Bradesco, inclusive PDFs rasterizados via OCR."""
    lancamentos = []
    data_atual = None
    partes_historico = []
    ultimo_saldo = None
    dentro_saldos_invest = False
    modo_ocr = False
    saldo_abertura = None
    indice_saldo_abertura = 0
    erro_ocr = ''

    regex_data = re.compile(r'^(\d{2}/\d{2}/\d{4})\s*[|—-]?\s*(.*)$')
    regex_moeda = re.compile(r'-?\d{1,3}(?:\.\d{3})*,\d{2}')
    ignorar_prefixos = (
        'extrato de:', 'agência | conta', 'agencia | conta', 'data lançamento',
        'data lancamento', 'folha ', 'extrato mensal / por período',
        'extrato mensal / por periodo', 'nome do usuário:', 'nome do usuario:',
        'data da operação:', 'data da operacao:', 'os dados acima têm como base',
        'os dados acima tem como base',
    )

    textos_paginas = [pagina.extract_text() or '' for pagina in reader.pages]

    # PDF-imagem: OCR somente quando não existe qualquer camada de texto.
    if not any(texto.strip() for texto in textos_paginas):
        modo_ocr = True
        try:
            import fitz
            import pytesseract
            from PIL import Image, ImageOps

            caminho_pdf = (
                getattr(reader, '_razync_source_path', None)
                or getattr(getattr(reader, 'stream', None), 'name', None)
            )
            if not caminho_pdf or not os.path.exists(caminho_pdf):
                erro_ocr = 'Arquivo temporário do PDF não ficou disponível para o OCR.'
                reader._razync_ocr_error = erro_ocr
            if caminho_pdf and os.path.exists(caminho_pdf):
                documento_ocr = fitz.open(caminho_pdf)
                textos_paginas = []
                for pagina_ocr in documento_ocr:
                    pix = pagina_ocr.get_pixmap(
                        matrix=fitz.Matrix(4.0, 4.0), alpha=False
                    )
                    imagem = Image.frombytes(
                        'RGB', [pix.width, pix.height], pix.samples
                    )
                    imagem = ImageOps.autocontrast(ImageOps.grayscale(imagem))
                    texto_ocr = pytesseract.image_to_string(
                        imagem,
                        lang='por',
                        config='--psm 6 -c preserve_interword_spaces=1'
                    )
                    textos_paginas.append(texto_ocr or '')
                documento_ocr.close()
        except Exception as erro:
            erro_ocr = str(erro)
            reader._razync_ocr_error = erro_ocr
            textos_paginas = textos_paginas or []

    reader._razync_ocr_executado = modo_ocr
    for texto in textos_paginas:
        for linha_bruta in texto.splitlines():
            linha = re.sub(r'\s+', ' ', linha_bruta).strip()
            if not linha:
                continue

            normalizada = normalizar_texto(linha)

            if normalizada.startswith('saldos invest facil'):
                dentro_saldos_invest = True
                partes_historico = []
                continue
            if normalizada.startswith('ultimos lancamentos'):
                dentro_saldos_invest = False
                partes_historico = []
                ultimo_saldo = None
                continue
            if normalizada.startswith(('data lancamento', 'data lançamento')):
                dentro_saldos_invest = False
                partes_historico = []
                continue
            if dentro_saldos_invest:
                continue
            if normalizada.startswith(ignorar_prefixos):
                continue
            if normalizada.startswith('nova geracao comercial') and 'cnpj:' in normalizada:
                continue
            if normalizada.startswith('total '):
                partes_historico = []
                continue

            match_data = regex_data.match(linha)
            if match_data:
                data_atual = match_data.group(1)
                linha = match_data.group(2).strip()
                normalizada = normalizar_texto(linha)
                if not linha:
                    continue

            if 'saldo anterior' in normalizada:
                moedas_saldo = regex_moeda.findall(linha)
                if moedas_saldo:
                    ultimo_saldo = limpar_valor_monetario(moedas_saldo[-1])
                    saldo_abertura = ultimo_saldo
                    indice_saldo_abertura = len(lancamentos)
                partes_historico = []
                continue

            if not data_atual:
                continue

            moedas = regex_moeda.findall(linha)
            if len(moedas) >= 2:
                valor_txt = moedas[-2]
                saldo_txt = moedas[-1]
                valor_impresso = limpar_valor_monetario(valor_txt)
                saldo_lido = limpar_valor_monetario(saldo_txt)
                valor = valor_impresso

                if ultimo_saldo is not None:
                    variacao = round(saldo_lido - ultimo_saldo, 2)
                    if modo_ocr:
                        # OCR pode perder o sinal do débito ou errar um dígito do saldo.
                        # A direção do saldo define o sinal; a magnitude impressa continua
                        # sendo usada quando a leitura do saldo não fecha exatamente.
                        sinal = -1 if variacao < 0 else 1
                        if abs(abs(variacao) - abs(valor_impresso)) <= max(
                            0.05, abs(valor_impresso) * 0.01
                        ):
                            valor = variacao
                            ultimo_saldo = saldo_lido
                        else:
                            valor = sinal * abs(valor_impresso)
                            ultimo_saldo = round(ultimo_saldo + valor, 2)
                    else:
                        if abs(abs(variacao) - abs(valor_impresso)) <= 0.02:
                            valor = variacao
                        ultimo_saldo = saldo_lido
                else:
                    ultimo_saldo = saldo_lido

                inicio_valor = linha.rfind(valor_txt)
                trecho_historico = linha[:inicio_valor].strip()
                historico = re.sub(
                    r'\s+', ' ',
                    ' '.join(
                        partes_historico
                        + ([trecho_historico] if trecho_historico else [])
                    )
                ).strip(' |—-')
                partes_historico = []

                hist_norm = normalizar_texto(historico)
                if not historico or hist_norm.startswith(('saldo ', 'total ')):
                    continue
                if abs(valor) < 0.005:
                    continue

                try:
                    data = datetime.strptime(data_atual, '%d/%m/%Y')
                except ValueError:
                    continue

                lancamentos.append({
                    'DESCRIÇÃO': banco,
                    'DATA': data,
                    'VALOR': round(valor, 2),
                    'DÉBITO': '',
                    'CRÉDITO': '',
                    'HISTÓRICO': historico,
                })
            else:
                partes_historico.append(linha)
                if len(partes_historico) > 8:
                    partes_historico = partes_historico[-8:]

    if saldo_abertura is not None and ultimo_saldo is not None:
        movimentos_validacao = [
            item.get('VALOR', 0.0) for item in lancamentos[indice_saldo_abertura:]
        ]
        reader._razync_balance_check = validar_fechamento_saldo(
            saldo_abertura, ultimo_saldo, movimentos_validacao
        )
    reader._razync_ocr_executado = modo_ocr
    if erro_ocr:
        reader._razync_ocr_error = erro_ocr
    return lancamentos

def processar_extrato_conferencia_empresa(file_bytes, filename, banco_forcado=None):
    """Lê a conferência pelo mesmo motor central usado em todo o Razync."""
    # Versão do parser para invalidar resultados antigos do cache quando a regra
    # de leitura do BB Autorizável mudar.
    _parser_conferencia_version = 'bb-rende-facil-v2'
    termos_saldo = [
        'saldo anterior', 'saldo aplic', 'saldo invest', 'saldo total disponivel',
        'saldo movimentacao conta', 'sdo aplic aut mais ap', 'saldo final',
        'saldo do dia', 'saldo total', 'saldo disponivel', 'saldo em conta',
    ]
    filtrados = []
    if banco_forcado == 'itau_hw88' and str(filename).lower().endswith('.pdf'):
        origem_extrato = processar_extrato_hw88(file_bytes).to_dict('records')
    elif banco_forcado == 'btg' and str(filename).lower().endswith('.pdf'):
        origem_extrato = processar_extrato_btg_vgv(file_bytes).to_dict('records')
    # O extrato BB Empresa 'Autorizável' possui linhas quebradas e pode colar
    # movimento e saldo. Usa leitor dedicado para não perder/duplicar valores.
    elif str(filename).lower().endswith('.pdf') and parece_extrato_bb_autorizavel(file_bytes):
        origem_extrato = processar_extrato_bb_autorizavel(file_bytes)
    else:
        origem_extrato = processar_extrato_unificado(file_bytes, filename) or []
    for item in origem_extrato:
        historico = normalizar_texto(texto_celula_seguro(item.get('HISTÓRICO', '')))
        if any(termo in historico for termo in termos_saldo):
            continue
        valor = limpar_valor_monetario(item.get('VALOR', 0))
        if abs(valor) < 0.005:
            continue
        filtrados.append(item)
    fechamento = request_state.get().get('ultimo_fechamento_extrato')
    if fechamento and fechamento.get('disponivel') and fechamento.get('ok') is False:
        record_warning(
            'O extrato foi lido, mas o fechamento matemático do saldo apresentou '
            f"diferença de {formatar_moeda(abs(fechamento.get('diferenca', 0)))}. "
            'Revise os lançamentos antes de concluir a conciliação.'
        )
    if not filtrados:
        erro_leitura = request_state.get().get('ultimo_erro_extrato', '')
        if erro_leitura:
            raise ValueError(erro_leitura)
    return filtrados

def conciliar_empresa_com_extrato(df_planilha, lancamentos_extrato, df_retirados=None):
    """Compara movimentos por dia e faz pareamento individual por data e centavos."""
    colunas_base = ['DESCRIÇÃO', 'DATA', 'VALOR', 'HISTÓRICO']

    def preparar_dataframe(dados):
        if isinstance(dados, pd.DataFrame):
            df = dados.copy()
        else:
            df = pd.DataFrame(dados or [])
        for coluna in colunas_base:
            if coluna not in df.columns:
                df[coluna] = '' if coluna != 'VALOR' else 0.0
        df['DESCRIÇÃO'] = df['DESCRIÇÃO'].fillna('').astype(str)
        df['DATA'] = pd.to_datetime(df['DATA'], dayfirst=True, errors='coerce').dt.normalize()
        df['VALOR'] = pd.to_numeric(df['VALOR'], errors='coerce').fillna(0.0).round(2)
        df['HISTÓRICO'] = df['HISTÓRICO'].fillna('').astype(str)
        df = df.dropna(subset=['DATA'])
        df = df[df['VALOR'].abs() >= 0.005].copy()
        df['_CENTAVOS'] = (df['VALOR'] * 100).round().astype(int)
        df['_BANCO'] = df['DESCRIÇÃO'].apply(
            lambda valor: re.sub(r'\s+', ' ', normalizar_texto(valor).replace('banco', '')).strip()
        )
        return df.reset_index(drop=True)

    df_modelo = preparar_dataframe(df_planilha)
    df_extrato = preparar_dataframe(lancamentos_extrato)
    df_retirados_ok = preparar_dataframe(df_retirados if df_retirados is not None else [])

    usar_banco_na_chave = df_modelo.loc[df_modelo['_BANCO'] != '', '_BANCO'].nunique() > 1
    for dataframe in [df_modelo, df_extrato, df_retirados_ok]:
        if usar_banco_na_chave:
            dataframe['_CHAVE'] = list(zip(
                dataframe['_BANCO'], dataframe['DATA'], dataframe['_CENTAVOS']
            ))
        else:
            dataframe['_CHAVE'] = list(zip(dataframe['DATA'], dataframe['_CENTAVOS']))

    # Estornos de baixa retirados de propósito não devem gerar falso alerta.
    indices_ignorados = set()
    if not df_retirados_ok.empty and not df_extrato.empty:
        quantidades_retiradas = df_retirados_ok['_CHAVE'].value_counts().to_dict()
        for chave, quantidade in quantidades_retiradas.items():
            candidatos = df_extrato.index[
                (df_extrato['_CHAVE'] == chave) &
                df_extrato['HISTÓRICO'].apply(identificar_estorno_de_baixa)
            ].tolist()
            indices_ignorados.update(candidatos[:int(quantidade)])

    df_ignorados = df_extrato.loc[sorted(indices_ignorados)].copy() if indices_ignorados else df_extrato.iloc[0:0].copy()
    df_extrato_comparavel = df_extrato.drop(index=list(indices_ignorados)).reset_index(drop=True)

    # Pareamento um a um: lançamentos repetidos são tratados individualmente.
    disponiveis_modelo = {}
    for indice, chave in enumerate(df_modelo['_CHAVE']):
        disponiveis_modelo.setdefault(chave, []).append(indice)

    indices_modelo_pareados = set()
    indices_extrato_sem_par = []
    for indice_extrato, chave in enumerate(df_extrato_comparavel['_CHAVE']):
        candidatos = disponiveis_modelo.get(chave, [])
        if candidatos:
            indices_modelo_pareados.add(candidatos.pop(0))
        else:
            indices_extrato_sem_par.append(indice_extrato)

    indices_modelo_sem_par = [
        indice for indice in range(len(df_modelo))
        if indice not in indices_modelo_pareados
    ]

    faltando_planilha = df_extrato_comparavel.loc[indices_extrato_sem_par, colunas_base].copy()
    a_mais_planilha = df_modelo.loc[indices_modelo_sem_par, colunas_base].copy()
    ignorados = df_ignorados[colunas_base].copy()

    def resumo_diario_por_natureza(df, prefixo):
        temp = df[['DATA', 'VALOR']].copy()
        temp[f'ENTRADAS {prefixo}'] = temp['VALOR'].where(temp['VALOR'] > 0, 0.0)
        temp[f'SAÍDAS {prefixo}'] = -temp['VALOR'].where(temp['VALOR'] < 0, 0.0)
        return temp.groupby('DATA', as_index=False)[[f'ENTRADAS {prefixo}', f'SAÍDAS {prefixo}']].sum()

    ext_dia = resumo_diario_por_natureza(df_extrato_comparavel, 'EXTRATO')
    plan_dia = resumo_diario_por_natureza(df_modelo, 'PLANILHA')
    diario = pd.merge(ext_dia, plan_dia, on='DATA', how='outer').fillna(0.0).sort_values('DATA')
    diario['DIF. ENTRADAS'] = (diario['ENTRADAS PLANILHA'] - diario['ENTRADAS EXTRATO']).round(2)
    diario['DIF. SAÍDAS'] = (diario['SAÍDAS PLANILHA'] - diario['SAÍDAS EXTRATO']).round(2)
    diario['STATUS ENTRADAS'] = diario['DIF. ENTRADAS'].apply(lambda v: '✅ Batendo' if abs(v) < 0.01 else '❌ Divergente')
    diario['STATUS SAÍDAS'] = diario['DIF. SAÍDAS'].apply(lambda v: '✅ Batendo' if abs(v) < 0.01 else '❌ Divergente')
    diario['STATUS'] = diario.apply(lambda r: '✅ Batendo' if abs(r['DIF. ENTRADAS']) < 0.01 and abs(r['DIF. SAÍDAS']) < 0.01 else '❌ Divergente', axis=1)

    return diario, faltando_planilha, a_mais_planilha, ignorados

_identificar_chave_banco_legado = identificar_chave_banco_empresa
_nome_banco_por_chave_legado = nome_banco_por_chave
_processar_extrato_conferencia_legado = processar_extrato_conferencia_empresa

def identificar_chave_banco_empresa(valor):
    texto = normalizar_texto(texto_celula_seguro(valor))
    if "caixa" in texto or "cef" in texto:
        return "caixa"
    if "inter" in texto:
        return "inter"
    if "safra" in texto:
        return "safra"
    return _identificar_chave_banco_legado(valor)

def nome_banco_por_chave(chave):
    if chave == "caixa":
        return "Caixa"
    if chave == "inter":
        return "Banco Inter"
    if chave == "safra":
        return "Safra"
    return _nome_banco_por_chave_legado(chave)

def processar_extrato_conferencia_empresa(file_bytes, filename, banco_forcado=None):
    if (
        request_state.get().get("empresa_organizador") == "crj_47"
        and banco_forcado in {None, "banco_brasil"}
    ):
        return _processar_bb_crj_47(file_bytes).to_dict("records")
    if (
        request_state.get().get("empresa_organizador") == "vital_safety_912"
        and banco_forcado in {None, "sicredi"}
    ):
        return _processar_sicredi_912(file_bytes).to_dict("records")
    if request_state.get().get("empresa_organizador") == "rm_postais_154":
        if banco_forcado == "bradesco":
            return _processar_bradesco_154(file_bytes).to_dict("records")
        if banco_forcado == "itau":
            return _processar_itau_154(file_bytes).to_dict("records")
    if request_state.get().get("empresa_organizador") == "kairos_1208":
        from razync.kairos_1208 import processar_extrato_1208

        banco_1208 = banco_forcado
        if banco_1208 not in {"itau", "safra", "bradesco"}:
            banco_1208 = identificar_chave_banco_empresa(filename)
        if banco_1208 in {"itau", "safra", "bradesco"}:
            return processar_extrato_1208(file_bytes, banco_1208).to_dict("records")
    if banco_forcado in {"itau_1208", "safra_1208", "bradesco_1208"}:
        from razync.kairos_1208 import processar_extrato_1208

        return processar_extrato_1208(
            file_bytes, banco_forcado.removesuffix("_1208")
        ).to_dict("records")
    if banco_forcado == "itau_1530":
        from razync.dias_pereira_1530 import (
            normalizar_modelo_itau_1530,
            processar_extrato_itau_xls_1530,
        )

        extensao = Path(str(filename or "")).suffix.lower()
        if extensao in {".xls", ".xlsx"}:
            return processar_extrato_itau_xls_1530(file_bytes).to_dict("records")
        registros = _processar_extrato_conferencia_legado(
            file_bytes, filename, "itau"
        )
        return normalizar_modelo_itau_1530(registros).to_dict("records")
    if banco_forcado in {"banco_brasil_625", "caixa_625", "sicredi_625"}:
        from razync.valean_625 import processar_extrato_625

        banco = banco_forcado.removesuffix("_625")
        return processar_extrato_625(file_bytes, banco).to_dict("records")
    if banco_forcado in {"inter", "inter_841"}:
        from razync.lucrativite_841 import processar_extrato_inter_conferencia_841

        return processar_extrato_inter_conferencia_841(
            file_bytes, filename
        ).to_dict("records")
    return _processar_extrato_conferencia_legado(
        file_bytes, filename, banco_forcado
    )

def _processar_bradesco_154(file_bytes):
    """Converte o Bradesco da empresa 154, limitado ao período principal do extrato."""
    reader = PdfReader(io.BytesIO(file_bytes))
    texto = "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    if not (
        "0004700-7" in texto
        or "R M SERVICOS POSTAIS" in texto.upper()
        or "68.370.568/0001-38" in texto
    ):
        raise ValueError("O PDF enviado não parece ser o Bradesco da empresa 154.")

    registros = processar_pdf_bradesco_mensal(reader, banco="BANCO BRADESCO")
    modelo = pd.DataFrame(registros)
    if modelo.empty:
        raise ValueError("Nenhum lançamento válido foi encontrado no extrato Bradesco.")

    periodo = re.search(
        r"Entre\s+(\d{2}/\d{2}/\d{4})\s+e\s+(\d{2}/\d{2}/\d{4})",
        texto,
        flags=re.I,
    )
    if periodo:
        inicio = pd.to_datetime(periodo.group(1), dayfirst=True, errors="coerce")
        fim = pd.to_datetime(periodo.group(2), dayfirst=True, errors="coerce")
    else:
        # Alguns PDFs Bradesco posicionam visualmente "Entre ... e ...", mas a
        # camada de texto joga as duas datas antes da palavra "Entre".
        cabecalho = texto[:1200]
        datas_cabecalho = re.findall(r"\d{2}/\d{2}/\d{4}", cabecalho)
        if len(datas_cabecalho) >= 2:
            inicio = pd.to_datetime(datas_cabecalho[0], dayfirst=True, errors="coerce")
            fim = pd.to_datetime(datas_cabecalho[1], dayfirst=True, errors="coerce")
        else:
            raise ValueError("Não foi possível identificar o período principal do extrato Bradesco.")

    modelo["DATA"] = pd.to_datetime(modelo["DATA"], dayfirst=True, errors="coerce")
    modelo["VALOR"] = pd.to_numeric(modelo["VALOR"], errors="coerce")
    modelo = modelo.dropna(subset=["DATA", "VALOR"]).copy()
    modelo = modelo[(modelo["DATA"] >= inicio) & (modelo["DATA"] <= fim)].copy()

    # Segurança adicional contra as seções auxiliares exibidas após o extrato mensal.
    historicos_norm = modelo["HISTÓRICO"].fillna("").astype(str).apply(normalizar_texto)
    modelo = modelo[
        ~historicos_norm.str.contains("saldo invest facil", regex=False)
        & ~historicos_norm.str.startswith("saldo ")
    ].copy()

    def _ajustar_154_bradesco(row):
        valor = float(row["VALOR"])
        historico = limpar_caracteres_ilegais(str(row.get("HISTÓRICO") or "")).strip()
        historico = re.sub(r"^(?:Pago|Recebido)\s*:\s*", "", historico, flags=re.I).strip()
        return pd.Series({
            "DESCRIÇÃO": "BANCO BRADESCO",
            "DATA": row["DATA"],
            "VALOR": round(valor, 2),
            "DÉBITO": "9" if valor > 0 else "",
            "CRÉDITO": "9" if valor < 0 else "",
            "HISTÓRICO": ("Recebido: " if valor > 0 else "Pago: ") + (historico or "MOVIMENTO BANCÁRIO"),
        })

    modelo = modelo.apply(_ajustar_154_bradesco, axis=1)
    modelo = modelo.sort_values("DATA", kind="stable").reset_index(drop=True)
    return modelo

def _processar_itau_154(file_bytes):
    """Converte o Itaú da empresa 154 para o Modelo Domínio, conta 508."""
    modelo = processar_extrato_itau_modelo(
        file_bytes,
        "508",
        ("R M SERVICOS POSTAIS", "68.370.568/0001-38", "0015961-9"),
        "empresa 154 - R.M. Serviços Postais",
    ).copy()

    # O leitor dedicado já ignora saldos. Mantém somente o período informado no PDF.
    reader = PdfReader(io.BytesIO(file_bytes))
    texto = "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    periodo = re.search(
        r"per[ií]odo:\s*(\d{2}/\d{2}/\d{4})\s+at[eé]\s+(\d{2}/\d{2}/\d{4})",
        texto,
        flags=re.I,
    )
    if periodo:
        inicio = pd.to_datetime(periodo.group(1), dayfirst=True, errors="coerce")
        fim = pd.to_datetime(periodo.group(2), dayfirst=True, errors="coerce")
        datas = pd.to_datetime(modelo["DATA"], dayfirst=True, errors="coerce")
        modelo = modelo[(datas >= inicio) & (datas <= fim)].copy()

    modelo = modelo.sort_values("DATA", kind="stable").reset_index(drop=True)
    return modelo

def _processar_sicredi_912(file_bytes):
    """Converte o extrato Sicredi da empresa 912 para o Modelo Domínio."""
    from razync.valean_625 import processar_sicredi_625

    modelo = processar_sicredi_625(file_bytes).copy()
    if modelo.empty:
        raise ValueError("Nenhum lançamento válido foi encontrado no extrato Sicredi.")

    # A empresa 912 usa a conta contábil 515.
    modelo["DÉBITO"] = modelo["VALOR"].apply(
        lambda valor: "515" if float(valor) > 0 else ""
    )
    modelo["CRÉDITO"] = modelo["VALOR"].apply(
        lambda valor: "515" if float(valor) < 0 else ""
    )

    # Segurança adicional: o extrato pode trazer uma seção de lançamentos futuros.
    # O parser Sicredi já exige movimento + saldo, mas filtramos qualquer data além
    # do período principal identificado no cabeçalho quando houver essa informação.
    reader = PdfReader(io.BytesIO(file_bytes))
    texto = "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    periodo = re.search(
        r"Per[ií]odo\s+de\s+(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})",
        texto,
        flags=re.I,
    )
    if periodo:
        inicio = pd.to_datetime(periodo.group(1), dayfirst=True, errors="coerce")
        fim = pd.to_datetime(periodo.group(2), dayfirst=True, errors="coerce")
        datas = pd.to_datetime(modelo["DATA"], dayfirst=True, errors="coerce")
        modelo = modelo[(datas >= inicio) & (datas <= fim)].copy()

    modelo = modelo.sort_values("DATA", kind="stable").reset_index(drop=True)
    return modelo

def _processar_bb_crj_47(file_bytes):
    """Converte o extrato BB da CRJ, descartando saldos intermediários e finais."""
    reader = PdfReader(io.BytesIO(file_bytes))
    linhas = []
    for pagina in reader.pages:
        linhas.extend((pagina.extract_text() or "").splitlines())

    regex_movimento = re.compile(
        r"^(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})\s*"
        r"\((?P<natureza>[+-])\)"
        r"(?P<data>\d{2}/\d{2}/\d{4})\s*(?P<resto>.*)$"
    )
    cabecalhos = (
        "Extrato de Conta Corrente", "Cliente", "Agência:", "Agencia:",
        "Lançamentos", "Lancamentos", "Dia Lote Documento Histórico Valor",
        "Dia Lote Documento Historico Valor",
    )

    registros_brutos = []
    atual = None
    for linha_original in linhas:
        linha = re.sub(r"\s+", " ", str(linha_original or "")).strip()
        if not linha:
            continue

        encontrado = regex_movimento.match(linha)
        if encontrado:
            if atual is not None:
                registros_brutos.append(atual)

            valor = limpar_valor_monetario(encontrado.group("valor"))
            if encontrado.group("natureza") == "-":
                valor = -abs(valor)
            else:
                valor = abs(valor)

            atual = {
                "DATA_TEXTO": encontrado.group("data"),
                "VALOR": round(float(valor), 2),
                "RESTO": encontrado.group("resto").strip(),
                "COMPLEMENTOS": [],
            }
            continue

        if atual is not None and not any(linha.startswith(cab) for cab in cabecalhos):
            atual["COMPLEMENTOS"].append(linha)

    if atual is not None:
        registros_brutos.append(atual)

    registros = []
    saldo_anterior = None
    saldo_final = None
    for item in registros_brutos:
        resto = str(item["RESTO"] or "").strip()
        resto_compacto = re.sub(r"\s+", "", resto).upper()
        texto_completo = re.sub(
            r"\s+", " ", " ".join([resto] + item["COMPLEMENTOS"])
        ).strip()
        texto_norm = normalizar_texto(texto_completo)

        if "saldo anterior" in texto_norm:
            saldo_anterior = abs(float(item["VALOR"]))
            continue
        if (
            item["DATA_TEXTO"] == "00/00/0000"
            or "saldo do dia" in texto_norm
            or resto_compacto == "SALDO"
        ):
            if resto_compacto == "SALDO":
                saldo_final = abs(float(item["VALOR"]))
            continue

        data = pd.to_datetime(item["DATA_TEXTO"], dayfirst=True, errors="coerce")
        if pd.isna(data):
            continue

        # Lote e documento aparecem antes do histórico na primeira linha.
        partes = resto.split()
        historico_primeira_linha = resto
        if len(partes) >= 2 and partes[0].isdigit():
            inicio_hist = 2
            historico_primeira_linha = " ".join(partes[inicio_hist:]).strip()

        historico = re.sub(
            r"\s+",
            " ",
            " ".join(
                parte for parte in [historico_primeira_linha] + item["COMPLEMENTOS"]
                if parte
            ),
        ).strip()
        if not historico:
            historico = "MOVIMENTO BANCÁRIO"

        valor = float(item["VALOR"])
        prefixo = "Recebido:" if valor > 0 else "Pago:"
        registros.append({
            "DESCRIÇÃO": "BANCO DO BRASIL",
            "DATA": data.to_pydatetime(),
            "VALOR": round(valor, 2),
            "DÉBITO": "8" if valor > 0 else "",
            "CRÉDITO": "8" if valor < 0 else "",
            "HISTÓRICO": f"{prefixo} {limpar_caracteres_ilegais(historico)}",
        })

    if not registros:
        raise ValueError("Nenhum lançamento válido foi encontrado no extrato do Banco do Brasil.")

    modelo = pd.DataFrame(
        registros,
        columns=["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"],
    ).sort_values("DATA", kind="stable").reset_index(drop=True)

    if saldo_anterior is not None and saldo_final is not None:
        movimento_liquido = round(float(modelo["VALOR"].sum()), 2)
        esperado = round(saldo_anterior + movimento_liquido, 2)
        if abs(esperado - saldo_final) > 0.02:
            raise ValueError(
                "Os lançamentos lidos não fecham com o saldo final do extrato. "
                f"Esperado {formatar_moeda(esperado)} e saldo final {formatar_moeda(saldo_final)}."
            )

    return modelo

def _processar_bradesco_964(file_bytes):
    """Converte o extrato mensal Bradesco da empresa 964 para o Modelo Domínio."""
    reader = PdfReader(io.BytesIO(file_bytes))
    registros = processar_pdf_bradesco_mensal(reader, banco="BANCO BRADESCO")
    if not registros:
        raise ValueError("Nenhum lançamento bancário foi encontrado no PDF do Bradesco.")

    modelo = pd.DataFrame(registros)
    colunas = ["DESCRIÇÃO", "DATA", "VALOR", "DÉBITO", "CRÉDITO", "HISTÓRICO"]
    for coluna in colunas:
        if coluna not in modelo.columns:
            modelo[coluna] = ""

    modelo["DATA"] = pd.to_datetime(modelo["DATA"], dayfirst=True, errors="coerce")
    modelo["VALOR"] = pd.to_numeric(modelo["VALOR"], errors="coerce")
    modelo = modelo.dropna(subset=["DATA", "VALOR"]).copy()
    modelo = modelo[modelo["VALOR"].abs() > 0.004].copy()

    def _historico_964(row):
        texto = limpar_caracteres_ilegais(str(row.get("HISTÓRICO") or "")).strip()
        texto = re.sub(r"^(?:Pago|Recebido)\s*:\s*", "", texto, flags=re.I).strip()
        prefixo = "Recebido:" if float(row["VALOR"]) > 0 else "Pago:"
        return f"{prefixo} {texto or 'MOVIMENTO BANCÁRIO'}"

    modelo["HISTÓRICO"] = modelo.apply(_historico_964, axis=1)
    modelo["DÉBITO"] = modelo["VALOR"].apply(lambda valor: "9" if float(valor) > 0 else "")
    modelo["CRÉDITO"] = modelo["VALOR"].apply(lambda valor: "9" if float(valor) < 0 else "")
    modelo = modelo[colunas].sort_values("DATA", kind="stable").reset_index(drop=True)
    return modelo

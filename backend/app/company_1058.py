"""Empresa 1058: relatório de favorecidos Itaú e extrato Caixa Gerenciador."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
import unicodedata

import pandas as pd
from pypdf import PdfReader

COLUNAS = ['DESCRIÇÃO', 'DATA', 'VALOR', 'DÉBITO', 'CRÉDITO', 'HISTÓRICO']
ROW = re.compile(r'^(\d{2}/\d{2}/\d{4})\s*(\d{6})\s+(.+?)\s+([\d.]+,\d{2})\s*([CD])\s+([\d.]+,\d{2})\s*([CD])$', re.I)
MONTHS = {'janeiro':1,'fevereiro':2,'marco':3,'abril':4,'maio':5,'junho':6,'julho':7,'agosto':8,'setembro':9,'outubro':10,'novembro':11,'dezembro':12}


def _norm(value):
    return ''.join(ch for ch in unicodedata.normalize('NFKD',str(value or '')) if not unicodedata.combining(ch)).casefold().strip()


def _cents(value):
    if isinstance(value, str):
        value=value.strip().replace('R$','').replace(' ','')
        value=value.replace('.','').replace(',','.') if ',' in value else value
    try:
        number=Decimal(str(value))
        if not number.is_finite():
            raise ValueError('Valor inválido')
        exact=number*100
        if exact != exact.to_integral_value():
            raise ValueError('Valores com mais de duas casas decimais.')
        return int(exact)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('Valor bancário inválido.') from exc


def _date(value):
    if isinstance(value, (int,float)) and not isinstance(value,bool):
        day=pd.to_datetime(value,origin='1899-12-30',unit='D',errors='coerce')
    else:
        day=pd.to_datetime(value,dayfirst=True,errors='coerce')
    if pd.isna(day):
        raise ValueError('Data inválida no relatório Itaú.')
    return pd.Timestamp(day).normalize()


def read_itau(content):
    if not content or len(content)>20*1024*1024:
        raise ValueError('Envie a planilha Itaú XLSX de até 20 MB.')
    try:
        book=pd.ExcelFile(BytesIO(content))
        if len(book.sheet_names)!=1:
            raise ValueError('A planilha Itaú deve ter uma única aba de lançamentos.')
        raw=pd.read_excel(book,sheet_name=0,header=None,dtype=object)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Não foi possível abrir a planilha Itaú.') from exc
    header_index=None
    for i in range(min(len(raw),30)):
        names=[_norm(v) for v in raw.iloc[i].tolist()]
        if all(label in names for label in ('data','tipo','favorecido','valor','descricao')):
            header_index=i
            break
    if header_index is None:
        raise ValueError('Cabeçalhos DATA, TIPO, FAVORECIDO, VALOR e DESCRIÇÃO não encontrados.')
    labels=[_norm(v) for v in raw.iloc[header_index].tolist()]
    cols={key:labels.index(key) for key in ('data','tipo','favorecido','valor','descricao')}
    rows=[]
    for index in range(header_index+1,len(raw)):
        row=raw.iloc[index]
        if all(pd.isna(row.iloc[k]) for k in cols.values()):
            continue
        date=_date(row.iloc[cols['data']])
        amount=_cents(row.iloc[cols['valor']])
        if amount<=0:
            raise ValueError(f'Valor não positivo no relatório Itaú, linha {index+1}.')
        typ=str(row.iloc[cols['tipo']] if pd.notna(row.iloc[cols['tipo']]) else '').strip()
        fav=str(row.iloc[cols['favorecido']] if pd.notna(row.iloc[cols['favorecido']]) else '').strip()
        desc=str(row.iloc[cols['descricao']] if pd.notna(row.iloc[cols['descricao']]) else '').strip()
        if not typ or not (fav or desc):
            raise ValueError(f'Histórico insuficiente na linha {index+1} da planilha Itaú.')
        # Relatório de operações com FAVORECIDO: "Crédito em conta" significa
        # transferência/pagamento ao favorecido, NÃO entrada na conta origem.
        history = ' - '.join(dict.fromkeys(filter(None,(desc,fav))))
        rows.append({'DESCRIÇÃO':'BANCO ITAÚ','DATA':date,'VALOR':-amount/100,
                     'DÉBITO':'','CRÉDITO':'514','HISTÓRICO':'Pago: '+history})
    if not rows:
        raise ValueError('Nenhum pagamento Itaú encontrado na planilha.')
    return pd.DataFrame(rows,columns=COLUNAS).sort_values('DATA',kind='stable').reset_index(drop=True)


def read_caixa(content):
    if not content.startswith(b'%PDF') or len(content)>25*1024*1024:
        raise ValueError('Envie um extrato PDF válido da Caixa (até 25 MB).')
    try:
        reader=PdfReader(BytesIO(content), strict=False)
        if not 1<=len(reader.pages)<=50:
            raise ValueError('PDF Caixa deve conter de 1 a 50 páginas.')
        text='\n'.join(page.extract_text() or '' for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Falha ao ler extrato da Caixa.') from exc
    compact=' '.join(text.split())
    if 'QUARTETO DE OBRAS LTDA' not in compact.upper() or not re.search(r'4115\s*\|\s*1292\s*\|\s*000578789424-0',compact):
        raise ValueError('Titular ou agência/conta Caixa não corresponde à empresa 1058.')
    month=re.search(r'M[eê]s\s*:\s*([A-Za-zçÇãÃ]+)\s*/\s*(20\d{2})',text,re.I)
    if not month:
        raise ValueError('Competência do extrato Caixa não identificada.')
    expected=(int(month.group(2)),MONTHS.get(_norm(month.group(1))))
    if expected[1] is None:
        raise ValueError('Mês não reconhecido no extrato Caixa.')
    movements=[]
    has_header=False
    for original in text.splitlines():
        line=' '.join(original.split())
        if 'Data Mov.' in line and 'Histórico' in line and 'Saldo' in line:
            has_header=True
            continue
        if not has_header:
            continue
        match=ROW.fullmatch(line)
        if match:
            day=datetime.strptime(match[1],'%d/%m/%Y')
            if (day.year,day.month)!=expected:
                raise ValueError('Lançamento fora da competência do extrato Caixa.')
            name=match[3].strip()
            value=_cents(match[4])*(1 if match[5].upper()=='C' else -1)
            balance=_cents(match[6])*(1 if match[7].upper()=='C' else -1)
            if _norm(name)=='saldo dia':
                if movements and movements[-1]['balance']!=balance:
                    raise ValueError('Saldo dia divergente no extrato Caixa.')
                continue
            if value==0:
                raise ValueError('Movimento com valor zero diferente de SALDO DIA.')
            movements.append({'date':pd.Timestamp(day),'value':value,'balance':balance,'history':name})
    if not has_header or not movements:
        raise ValueError('Nenhuma movimentação reconhecida no extrato Caixa.')
    opening=movements[0]['balance']-movements[0]['value']
    running=opening
    for item in movements:
        running+=item['value']
        if running!=item['balance']:
            raise ValueError('Saldo bancário Caixa divergente; confira o PDF.')
    return pd.DataFrame([{'DESCRIÇÃO':'BANCO CAIXA','DATA':x['date'],'VALOR':x['value']/100,
                         'DÉBITO':'504' if x['value']>0 else '',
                         'CRÉDITO':'504' if x['value']<0 else '',
                         'HISTÓRICO':('Recebido: ' if x['value']>0 else 'Pago: ')+x['history']}
                        for x in movements],columns=COLUNAS)



def read_itau_statement(content, filename):
    """Lê o EXTRATO real para conferência, separado do relatório de pagamentos."""
    from app import engine
    import io

    lower=str(filename or '').lower()
    if lower.endswith(('.xlsx','.xls')):
        # Planilha de favorecidos não pode ser usada como se fosse extrato.
        try:
            raw=pd.read_excel(BytesIO(content),header=None,nrows=30,dtype=object)
            names=[_norm(v) for values in raw.values for v in values if pd.notna(v)]
            if {'data','tipo','favorecido','valor','descricao'} <= set(names):
                raise ValueError('A planilha de favorecidos do Itaú não é um extrato bancário. Envie o extrato da conta para a conferência.')
        except ValueError:
            raise
        except Exception:
            pass
    if lower.endswith('.pdf'):
        if not content.startswith(b'%PDF'):
            raise ValueError('Envie um PDF válido do extrato Itaú.')
    if lower.endswith('.ofx'):
        text=content[:15000].decode('latin-1',errors='ignore')
        bankid=re.search(r'<BANKID>\s*(\d+)',text,re.I)
        if bankid and bankid.group(1).lstrip('0')!='341':
            raise ValueError('Este OFX não pertence ao Banco Itaú.')
    rows=engine.processar_extrato_conferencia_empresa(content,filename,'itau')
    frame=pd.DataFrame(rows)
    if frame.empty or not {'DATA','VALOR','HISTÓRICO','DESCRIÇÃO'} <= set(frame.columns):
        raise ValueError('Nenhum movimento bancário válido encontrado no extrato Itaú.')
    # Rejeitar leitor genérico que identificou outro banco ou origem desconhecida.
    banks=frame['DESCRIÇÃO'].fillna('').map(_norm)
    if not banks.map(lambda value: 'itau' in value).all():
        raise ValueError('O arquivo não foi identificado com segurança como extrato Itaú.')
    frame=frame.copy()
    frame['DATA']=pd.to_datetime(frame['DATA'],dayfirst=True,errors='coerce')
    frame['VALOR']=pd.to_numeric(frame['VALOR'],errors='coerce')
    if frame['DATA'].isna().any() or frame['VALOR'].isna().any():
        raise ValueError('Extrato Itaú contém data ou valor inválido.')
    frame=frame.loc[frame['VALOR'].abs()>=0.005].copy()
    if frame.empty:
        raise ValueError('Extrato Itaú sem movimentações.')
    frame['DÉBITO']=frame['VALOR'].map(lambda value:'514' if value>0 else '')
    frame['CRÉDITO']=frame['VALOR'].map(lambda value:'514' if value<0 else '')
    frame['HISTÓRICO']=[
        ('Recebido: ' if value>0 else 'Pago: ')+re.sub(r'^(?:Pago|Recebido)\s*:\s*','',str(history),flags=re.I).strip()
        for value,history in zip(frame['VALOR'],frame['HISTÓRICO'])
    ]
    return frame[COLUNAS].reset_index(drop=True)


def workflow_1058(roles,options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    frames={}
    for bank,label,parser,ext in (('itau','Itaú',read_itau,'.xlsx'),('caixa','Caixa',read_caixa,'.pdf')):
        uploads=roles.get(bank) or []
        if not uploads:
            continue
        periods=set()
        parts=[]
        for filename,content in uploads:
            if not filename.lower().endswith(ext):
                raise ValueError(f'Empresa 1058: arquivo {label} deve ter extensão {ext}.')
            frame=parser(content)
            months=set(frame['DATA'].dt.to_period('M'))
            if len(months)!=1 or months & periods:
                raise ValueError(f'Competência repetida ou inconsistente nos arquivos {label}.')
            periods.update(months)
            parts.append(frame)
        result=filter_frame(pd.concat(parts,ignore_index=True),options)
        if not result.empty:
            frames[label]=result.sort_values('DATA',kind='stable')
    if not frames:
        raise ValueError('Envie a planilha Itaú e/ou o extrato Caixa com lançamentos no período selecionado.')
    return gerar_modelo_abas(frames,date_format='dd/mm/yyyy'),'EMPRESA_1058_MODELO_DOMINIO.xlsx'

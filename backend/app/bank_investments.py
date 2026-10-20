"""TXT Domínio para zeramento diário após conferência com extrato concluída."""
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, JSONResponse
from app.registry import CAPABILITIES
from app.migration_services import reconcile

router = APIRouter(prefix="/api/v1/conferencia-extrato")
REDEMPTION = "RESGATE APLICAÇÃO FINANCEIRA CF EXTRATO"
INVESTMENT = "APLICAÇÃO FINANCEIRA CF EXTRATO"


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError()
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Valor monetário inválido na conferência.") from None


def opening_balance(value):
    if isinstance(value, str):
        value = value.strip() or "0"
        if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?", value):
            raise ValueError("Informe o saldo anterior em reais, como 1.234,56 ou -100,00.")
        value = value.replace(".", "").replace(",", ".")
    return money(value)


def account(value):
    value = str(value or "").strip()
    if not re.fullmatch(r"\d{1,15}", value) or int(value) == 0:
        raise ValueError("Informe contas contábeis numéricas válidas para o banco e a aplicação/resgate.")
    return value


def daily_entries(daily, bank_account, investment_account, opening=Decimal(0)):
    bank_account, investment_account = account(bank_account), account(investment_account)
    if int(bank_account) == int(investment_account):
        raise ValueError("A conta de aplicação/resgate deve ser diferente da conta do banco.")
    if daily.empty:
        raise ValueError("Não há dias conferidos para gerar o TXT.")
    frame = daily.copy()
    frame['DATA'] = pd.to_datetime(frame['DATA'], errors='coerce', dayfirst=True)
    if frame['DATA'].isna().any() or frame['DATA'].dt.normalize().duplicated().any():
        raise ValueError("Datas inválidas ou repetidas na conferência diária.")
    frame = frame.sort_values('DATA')
    result = []
    for index, (_, row) in enumerate(frame.iterrows()):
        incoming, outgoing = money(row['ENTRADAS PLANILHA']), money(row['SAÍDAS PLANILHA'])
        if min(incoming, outgoing) < 0:
            raise ValueError("Entradas e saídas diárias devem ser valores positivos.")
        if incoming != money(row['ENTRADAS EXTRATO']) or outgoing != money(row['SAÍDAS EXTRATO']):
            raise ValueError("Todos os saldos diários precisam estar batendo para gerar o TXT.")
        balance = incoming - outgoing + (money(opening) if index == 0 else Decimal(0))
        if balance == 0:
            continue
        redemption = balance < 0
        result.append({'DATA':row['DATA'].strftime('%d/%m/%Y'),
            'DÉBITO':bank_account if redemption else investment_account,
            'CRÉDITO':investment_account if redemption else bank_account,
            'VALOR':abs(balance), 'HISTÓRICO':REDEMPTION if redemption else INVESTMENT})
    return result


def prepare_entries(company_code, banks, files, model, options, settings):
    if (not isinstance(banks, list) or not banks or len(banks) != len(set(banks))
            or not isinstance(options, dict) or not isinstance(settings, dict)):
        raise ValueError("Configuração dos bancos inválida.")
    configured = CAPABILITIES.get(company_code, {}).get('banks', {})
    if any(not isinstance(bank, str) or bank not in configured for bank in banks):
        raise ValueError("Banco não disponível para esta empresa.")
    if any(bank not in banks for bank, _, _ in files):
        raise ValueError("Há extratos de bancos fora da seleção.")
    entries = []
    for bank in banks:
        config = settings.get(bank)
        if not isinstance(config, dict):
            raise ValueError("Informe as contas de todos os bancos selecionados.")
        bank_account = account(configured[bank] or config.get('conta_banco'))
        if configured[bank] and config.get('conta_banco') and int(account(config['conta_banco'])) != int(bank_account):
            raise ValueError("A conta do banco não corresponde ao cadastro da empresa.")
        investment_account = account(config.get('conta_aplicacao'))
        opening = opening_balance(config.get('saldo_anterior', '0'))
        statements = [(name, content) for code, name, content in files if code == bank]
        if not statements:
            raise ValueError("Envie o extrato de todos os bancos selecionados.")
        # O critério desta ferramenta é a igualdade diária de entradas e saídas,
        # validada novamente em daily_entries. Correspondência individual pode
        # divergir por agrupamentos sem alterar os totais conferidos do dia.
        _, sheets = reconcile(company_code, bank, model, statements, options)
        for entry in daily_entries(sheets.get('Conferência diária', pd.DataFrame()), bank_account, investment_account, opening):
            redemption = entry['HISTÓRICO'] == REDEMPTION
            entries.append(dict(entry, BANCO=bank, TIPO='Resgate' if redemption else 'Aplicação',
                SALDO_ANTES=-entry['VALOR'] if redemption else entry['VALOR'], SALDO_APOS=Decimal('0.00')))
    if not entries:
        raise ValueError("Os dias já estão zerados. Não há aplicações ou resgates a gerar.")
    entries.sort(key=lambda row: pd.to_datetime(row['DATA'], dayfirst=True))
    return entries


def serialize_txt(entries):
    # Mesmo formato do exportador Domínio existente. Históricos preservados literalmente,
    # sem prefixos Pago/Recebido; valores sempre positivos e natureza nas contas D/C.
    return ''.join(f"{row['DATA']};{row['DÉBITO']};{row['CRÉDITO']};{row['VALOR']:.2f};{row['HISTÓRICO']}\n" for row in entries).encode('utf-8')


def generate(company_code, banks, files, model, options, settings):
    return serialize_txt(prepare_entries(company_code,banks,files,model,options,settings))


@router.post('/{company_code}/aplicacoes-resgates/preview')
@router.post('/{company_code}/aplicacoes-resgates')
async def download_investments(request: Request, company_code: int, banks_json: str = Form(...), file_banks_json: str = Form(...),
    settings_json: str = Form(...), model_file: UploadFile = File(...), files: list[UploadFile] = File(...), options_json: str = Form('{}')):
    try:
        banks, file_banks, options, settings = (json.loads(value) for value in (banks_json,file_banks_json,options_json,settings_json))
        if not isinstance(file_banks,list) or len(file_banks) != len(files):
            raise ValueError("Os extratos não correspondem aos bancos selecionados.")
        prepared = [(bank, upload.filename or 'extrato', await upload.read()) for bank, upload in zip(file_banks,files)]
        entries = await run_in_threadpool(prepare_entries,company_code,banks,prepared,await model_file.read(),options,settings)
        content = serialize_txt(entries)
        if request.url.path.endswith('/preview'):
            rows = [{key:format(value,'.2f') if isinstance(value,Decimal) else value for key,value in row.items()} for row in entries]
            return JSONResponse({'rows':rows,'txt':content.decode('utf-8'), 'summary':{
                'lancamentos':len(rows), 'resgates':sum(row['TIPO']=='Resgate' for row in rows),
                'aplicacoes':sum(row['TIPO']=='Aplicação' for row in rows),
                'total_resgates':format(sum((row['VALOR'] for row in entries if row['TIPO']=='Resgate'),Decimal(0)),'.2f'),
                'total_aplicacoes':format(sum((row['VALOR'] for row in entries if row['TIPO']=='Aplicação'),Decimal(0)),'.2f')}},
                headers={'Cache-Control':'no-store'})
        return Response(content,media_type='text/plain; charset=utf-8',headers={
            'Content-Disposition':f'attachment; filename="RAZYNC_{company_code}_APLICACOES_RESGATES.txt"','Cache-Control':'no-store'})
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422,str(exc)) from exc

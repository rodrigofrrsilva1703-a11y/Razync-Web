"""Minimize document data at storage and external AI boundaries."""
import re
import unicodedata

_MARKERS = {'[LINK]', '[EMAIL]', '[CHAVE]', '[CNPJ]', '[CPF]', '[DADO BANCARIO]', '[TELEFONE]'}
_PATTERNS = (
    (r'https?://[^\s<>]+', '[LINK]'),
    (r'[\w.+-]+@[\w.-]+\.[a-z]{2,}', '[EMAIL]'),
    (r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', '[CHAVE]'),
    (r'\b\d{44,}\b', '[CHAVE]'),
    (r'\b(?:[a-z0-9]{2}\.[a-z0-9]{3}\.[a-z0-9]{3}/[a-z0-9]{4}-\d{2}|\d{2}[. ]?\d{3}[. ]?\d{3}[/ ]?\d{4}[- ]?\d{2})\b', '[CNPJ]'),
    (r'\bcnpj\s*[:=]?\s*[a-z0-9]{12}\d{2}\b', '[CNPJ]'),
    (r'\b\d{3}[. ]?\d{3}[. ]?\d{3}[- ]?\d{2}\b', '[CPF]'),
    (r'\b(?:ag[eê]ncia|ag\.?|conta(?:\s+(?:corrente|banc[aá]ria))?|chave\s+pix)\s*[:#=]?\s*\d[\d.-]*\b', '[DADO BANCÁRIO]'),
    (r'(?<!\w)(?:\+55\s*)?(?:\(\d{2}\)|\d{2}[ .-])\s*9?\d{4}[ .-]?\d{4}\b', '[TELEFONE]'),
)

def mask_identifiers(value):
    text = unicodedata.normalize('NFKC', str(value or ''))
    for pattern, replacement in _PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text

# Fixed vocabulary: unknown words (including names) and document numbers are
# not copied. This leaves operational clues without relying on name detection.
_TERMS = frozenset("""
de do da dos das em com abertura acumulador adiantamento ajuste aluguel analise aplicacao aporte
apuracao baixa bancario banco boleto cancelamento cartao cheque classificacao
classificar codigo compensacao competencia compra comprovante conciliacao
conferir conta contabil contabilizado contrapartida cobertura credito debito
deposito desconto devolucao diferenca divergencia documento documentos
duplicado duplicidade entrada entradas erro estorno excesso falta fatura
fechamento financeira fiscal folha fornecimento frete guia historico icms
imposto impostos inss irrf iss juros lancamento lancamentos liquido
liquidacao mercadoria multa nf nfe nfse nota notas pagamento pagto pago
parcela pendencia periodo pix prazo provisorio razao recebido recebimento
reclassificacao reembolso regularizacao remessa rendimento resgate retencao
saldo saida saidas servico servicos simples tarifa taxa ted titulo total
transferencia tributo valor valores venda vendas vencimento
confere nao sem parcial integral exata exato manual insuficiente recorrente
anterior posterior mensal diario duplicada omitido omitida falta mesma mesmo
como por que qual quais onde verificar verifique comparar compare corrigir
investigar explique resumo vinculo causa identificar localize localizar verificar
""".split())
_SAFE_REF = re.compile(r'(?:[A-Z]{1,3}-?\d{1,8}|\d{1,8}:(?:ENTRADAS?|SA[IÍ]DAS?))', re.I)
_DATE = re.compile(r'(?:\d{4}-\d{2}(?:-\d{2})?|\d{2}/\d{2}/\d{4}|\d{2}/\d{4})')
_MONEY = re.compile(r'-?(?:R\$\s*)?-?(?:\d{1,3}(?:\.\d{3}){1,5},\d{2}|\d{1,15}(?:[.,]\d{1,2})?)')
_CODE_KEYS = {'conta','contrapartida','acumulador','acumuladores','codigo','cfop','grupo','id','referencia','referencias','natureza'}
_PRIVATE_FIELDS = {
    'cpf', 'cnpj', 'cpf_cnpj', 'cnpj_cpf', 'email', 'telefone', 'celular',
    'chave_pix', 'conta_bancaria', 'agencia', 'numero_nota', 'chave_acesso',
    'chave_nfe', 'nome', 'fornecedor', 'favorecido', 'destinatario', 'emitente',
}
_NUMERIC_KEYS = {'valor','fiscal','contabil','debito','credito','total','diferenca','total_conta'}

def operation_clues(value, *, references=False):
    text = mask_identifiers(value)[:3000]
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    tokens = re.findall(r'\[[A-Z ]+\]|[A-Za-z]+-?\d*', text)
    kept = []
    for token in tokens:
        if token in _MARKERS or token.lower() in _TERMS:
            kept.append(token)
        elif references and re.fullmatch(r'[LACDFMN]-\d{1,6}|L\d{1,6}', token):
            kept.append(token)
    return ' '.join(dict.fromkeys(kept))[:220]

def provider_context(value, field=''):
    """Copy structured evidence; reduce every other string to known terms."""
    if isinstance(value, dict):
        return {key: provider_context(item, str(key).casefold()) for key, item in value.items()
                if re.fullmatch(r'[\w:-]{1,80}', str(key))
                and str(key).casefold() not in _PRIVATE_FIELDS
                and mask_identifiers(key) == str(key)}
    if isinstance(value, (list, tuple)):
        return [provider_context(item, field) for item in value]
    if not isinstance(value, str):
        return value
    if _DATE.fullmatch(value) or (value.lstrip('-').startswith('R$') and _MONEY.fullmatch(value)):
        return value
    if (field.endswith('_brl') or field in _NUMERIC_KEYS) and _MONEY.fullmatch(value):
        return value
    if field in _CODE_KEYS and (value == "RESUMO" or re.fullmatch(r'\d{1,8}', value) or _SAFE_REF.fullmatch(value)):
        return value
    return operation_clues(value, references=True)

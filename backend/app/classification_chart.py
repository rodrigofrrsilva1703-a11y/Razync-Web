"""Use prior installment evidence and the company's analytical chart of accounts."""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from app import engine


def load_company_chart(directory, company):
    path = Path(directory) / f'{int(company)}.json'
    try:
        chart = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    if not isinstance(chart, dict) or not all(
        isinstance(entry, dict) and isinstance(entry.get('analitica'), bool)
        and isinstance(entry.get('classificacao'), str) and isinstance(entry.get('nome'), str)
        for entry in chart.values()
    ):
        raise ValueError('O plano de contas cadastrado para esta empresa é inválido.')
    return chart


def _document_identity(history):
    name, observation = _party_and_observation(history)
    match = _INSTALLMENT_REFERENCE.fullmatch(observation)
    if not match or len(name.split()) < 2:
        return None
    return name, match[1], match[2]


def _transaction_day(value):
    if isinstance(value, date):
        return value.date() if isinstance(value, datetime) else value
    text = engine.texto_celula_seguro(value)
    for date_format in ('%d/%m/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def _month(value):
    day = _transaction_day(value)
    return day.strftime('%Y-%m') if day else ''


_GROUP_BY_NATURE = {'pago': '2.1.3.01.001', 'recebido': '1.1.2.01.001'}
_TITLE_REFERENCE = re.compile(r'(?:(?:nf[e]?|ped)\s*[:#-]?\s*)?\d{3,10}(?:\s*/\s*\d{1,2})?')
_INSTALLMENT_REFERENCE = re.compile(r'((?:ped)?\d{3,10})\s*/\s*(\d{1,2})')
_MONTH_PATTERN = re.compile(r'\d{4}-(?:0[1-9]|1[0-2])')
_SPECIAL_OPERATION = re.compile(
    r'\b(?:adiant\w*|adto|antecip\w*|reemb\w*|reem|devol\w*|estorn\w*|transf\w*|'
    r'tarif\w*|juros|multa|iof|aplicacao|resgate|folha|salario|imposto|tribut\w*)\b'
)
_APPROVAL_SPECIAL_OPERATION = re.compile(
    r'\b(?:ferias|rescis\w*|inss|fgts|irrf|pis|cofins|csll|icms|iss|gnre|'
    r'aluguel|frete|emprestim\w*|financiam\w*|rendiment\w*)\b'
)


def _party_and_observation(history):
    text = engine.normalizar_texto(engine.texto_celula_seguro(history))
    match = re.search(r'\bempresa\s*:\s*(.+?)(?:\s+obs\s*:\s*(.*))?$', text)
    if match:
        party, observation = match[1], (match[2] or '').strip()
    else:
        plain = re.fullmatch(r'(?:pago|recebido)\s*:\s*(.+)', text)
        if not plain:
            return '', ''
        body = plain[1].strip()
        suffix = re.fullmatch(r'(.+?)\s+((?:ped)?\d{3,10}\s*/\s*\d{1,2})', body)
        prefix = re.fullmatch(r'doc\.?\s*((?:ped)?\d{3,10}\s*/\s*\d{1,2})\s+-\s+(.+)', body)
        if suffix:
            party, observation = suffix.groups()
        elif prefix:
            observation, party = prefix.groups()
        else:
            return '', ''
    name = engine.extrair_nome_empresa_classificacao(party, legado=True)
    # Preserve identifiers; only normalize the formatting of an exact reference.
    return name, re.sub(r'\s*/\s*', '/', re.sub(r'\s+', ' ', observation))


def _canonical_party(value):
    text = engine.normalizar_texto(engine.texto_celula_seguro(value))
    text = re.sub(r'\bs[./]\s*a\b', ' sa ', text)
    text = re.sub(r'\b[a-z]*\d[a-z0-9]*\b', ' ', text)
    return engine.extrair_nome_empresa_classificacao(text, legado=True)


def _history_party(history):
    text = engine.normalizar_texto(engine.texto_celula_seguro(history))
    party = re.search(r'\bempresa\s*:\s*(.+?)(?:\s+obs\s*:|$)', text)
    if party:
        return _canonical_party(party[1])
    plain = re.fullmatch(r'(?:pago|recebido)\s*:\s*(.+)', text)
    if not plain:
        return ''
    body = re.sub(r'^doc\.?\s*[^ ]+\s+-\s+', '', plain[1])
    # O sufixo após a referência pertence à operação, não ao nome.
    body = re.split(r'\s+(?:(?:doc|nf[e]?|ped)\b|[a-z]*\d)', body, maxsplit=1)[0]
    return _canonical_party(body)


def remember_chart_approval(record):
    """Keep the name and period of a review explicitly taught to the base."""
    history = record.get('exemplo_historico') or ''
    normalized = engine.normalizar_texto(history)
    if _SPECIAL_OPERATION.search(normalized) or _APPROVAL_SPECIAL_OPERATION.search(normalized):
        return
    name = _history_party(history)
    if len(name.split()) >= 2:
        record['aprovacoes_nome'] = {name: sorted(
            period for period in record['periodos'] if _MONTH_PATTERN.fullmatch(period)
        )}


def chart_approvals(record):
    approvals = record.get('aprovacoes_nome')
    if not isinstance(approvals, dict):
        return {}
    return {
        name: periods
        for name, values in approvals.items()
        if isinstance(name, str) and len(name.split()) >= 2 and isinstance(values, list)
        if (periods := {p for p in values if isinstance(p, str) and _MONTH_PATTERN.fullmatch(p)
                       and p in record.get('periodos', [])})
    }


class ChartNameMatcher:
    """Cross-check the counterparty name against learned accounts and the chart."""

    def __init__(self, records, bank_accounts, chart):
        self.chart = chart
        self.plan_parties = defaultdict(dict)
        self.learned_parties = defaultdict(lambda: defaultdict(set))
        self.learned_periods = defaultdict(set)
        self.approved_periods = defaultdict(set)
        self.plan_terms = defaultdict(set)
        self.bank_codes = {str(code) for code in bank_accounts.values()}
        for account, entry in chart.items():
            if entry['analitica'] and entry['classificacao'] in _GROUP_BY_NATURE.values():
                name = _canonical_party(entry['nome'])
                if len(name.split()) >= 2:
                    group = entry['classificacao']
                    self.plan_parties[group][account] = name
                    for term in set(name.split()):
                        self.plan_terms[group, term].add(account)
        for record in records:
            bank = record.get('banco')
            bank_account = engine.texto_celula_seguro(bank_accounts.get(bank))
            debit = engine.texto_celula_seguro(record.get('debito'))
            credit = engine.texto_celula_seguro(record.get('credito'))
            if not bank_account or not debit or not credit or debit == credit:
                continue
            if credit == bank_account:
                nature, account = 'pago', debit
            elif debit == bank_account:
                nature, account = 'recebido', credit
            else:
                continue
            for name, periods in chart_approvals(record).items():
                self.learned_parties[bank, nature][name].add(account)
                key = (bank, nature, name, account)
                self.learned_periods[key].update(periods)
                self.approved_periods[key].update(periods)
            history = record.get('exemplo_historico')
            if _SPECIAL_OPERATION.search(engine.normalizar_texto(history or '')):
                continue
            name = _history_party(history)
            if len(name.split()) >= 2:
                self.learned_parties[bank, nature][name].add(account)
                key = (bank, nature, name, account)
                self.learned_periods[key].update(
                    str(period) for period in record.get('periodos', [])
                    if _MONTH_PATTERN.fullmatch(str(period))
                )

    def find(self, bank, nature, history, transaction_date):
        # Operações especiais seguem as regras já existentes.
        normalized = engine.normalizar_texto(history)
        if _SPECIAL_OPERATION.search(normalized):
            return None
        name = _history_party(history)
        if len(name.split()) < 2:
            return None
        group = _GROUP_BY_NATURE.get(nature)
        plan = self.plan_parties.get(group, {})
        accounts_with_shared_term = set().union(*(
            self.plan_terms.get((group, term), ()) for term in set(name.split())
        ))
        learned = {
            account for learned_name, accounts in self.learned_parties.get((bank, nature), {}).items()
            if engine.calcular_similaridade_nome_empresa(name, learned_name) >= .94
            for account in accounts
        }
        candidates = {
            account for account in accounts_with_shared_term
            if re.fullmatch(r'[1-9][0-9]{0,14}', account) and account not in self.bank_codes
            and engine.calcular_similaridade_nome_empresa(name, plan[account]) >= .94
        }
        if len(candidates) != 1 or learned != candidates:
            return None
        account = next(iter(candidates))
        month = _month(transaction_date)
        if not month:
            return None
        periods = self.learned_periods.get((bank, nature, name, account), ())
        if plan[account] == name and sum(p < month for p in periods) >= 2:
            return account, 'por_historico_confirmado_no_plano'
        approvals = self.approved_periods.get((bank, nature, name, account), ())
        if any(p < month for p in approvals) and not _APPROVAL_SPECIAL_OPERATION.search(normalized):
            return account, 'por_aprovacao_no_plano'
        return None


    def recent_suggestion(self, bank, nature, history, transaction_date):
        if _SPECIAL_OPERATION.search(engine.normalizar_texto(history)):
            return None
        name = _history_party(history)
        month = _month(transaction_date)
        if len(name.split()) < 2 or not month:
            return None
        by_period = defaultdict(set)
        for learned_name, codes in self.learned_parties.get((bank, nature), {}).items():
            if engine.calcular_similaridade_nome_empresa(name, learned_name) < .94:
                continue
            for code in codes:
                for period in self.learned_periods[bank, nature, learned_name, code]:
                    if period < month:
                        by_period[period].add(code)
        periods = sorted(by_period, reverse=True)[:3]
        if len(periods) != 3:
            return None
        candidates = set().union(*(by_period[period] for period in periods))
        if len(candidates) != 1:
            return None
        code = next(iter(candidates))
        plan_name = self.plan_parties.get(_GROUP_BY_NATURE.get(nature), {}).get(code, '')
        if code in self.bank_codes or not re.fullmatch(r'[1-9][0-9]{0,14}', code):
            return None
        if engine.calcular_similaridade_nome_empresa(name, plan_name) < .94:
            return None
        return {'conta': code, 'periodos': sorted(periods)}


def match_internal_transfers(sheets, bank_accounts, chart):
    """Recognize a unique opposite movement whose accounting entry confirms the pair."""
    eligible_banks = {}
    for bank, value in bank_accounts.items():
        account = engine.texto_celula_seguro(value)
        entry = chart.get(account)
        if entry and entry['analitica'] and entry['classificacao'].startswith('1.1.1.02.'):
            eligible_banks[bank] = account
    if len(eligible_banks) < 2:
        return {}

    entries = defaultdict(list)
    for ws, header, columns, sheet_bank in sheets:
        if not {'data', 'valor'} <= columns.keys():
            continue
        for row in range(header + 1, ws.max_row + 1):
            description = ws.cell(row, columns['descricao']).value if 'descricao' in columns else ''
            bank = engine.identificar_chave_banco_empresa(description) or sheet_bank
            account = eligible_banks.get(bank)
            day = _transaction_day(ws.cell(row, columns['data']).value)
            if not account or not day:
                continue
            amount = engine.limpar_valor_monetario(ws.cell(row, columns['valor']).value)
            try:
                cents = int(Decimal(str(amount)).quantize(Decimal('0.01')) * 100)
            except (InvalidOperation, ValueError, OverflowError):
                continue
            if not cents:
                continue
            history = engine.texto_celula_seguro(ws.cell(row, columns['historico']).value)
            is_transfer = bool(re.search(r'\b(?:transferencias?|transf|entre contas)\b', engine.normalizar_texto(history)))
            debit = ws.cell(row, columns['debito'])
            credit = ws.cell(row, columns['credito'])
            own, counterpart = (credit, debit) if cents < 0 else (debit, credit)
            entries[day, cents].append((account, own, counterpart, is_transfer))

    matches = {}
    for (day, cents), entries_on_side in entries.items():
        opposite = entries.get((day, -cents), ())
        if len(entries_on_side) != 1 or len(opposite) != 1:
            continue
        account, own, counterpart, marked = entries_on_side[0]
        other, other_own, other_counterpart, other_marked = opposite[0]
        if (
            account != other and marked and other_marked
            and not engine.texto_celula_seguro(counterpart.value)
            and engine.texto_celula_seguro(own.value) == account
            and engine.texto_celula_seguro(other_own.value) == other
            and engine.texto_celula_seguro(other_counterpart.value) == account
        ):
            matches[counterpart] = other
    return matches


def parse_chart_pdf(content, company_name):
    import fitz

    try:
        with fitz.open(stream=content, filetype='pdf') as pdf:
            pages = [page.get_text(sort=True) for page in pdf]
    except (ValueError, RuntimeError) as exc:
        raise ValueError('Não foi possível ler o PDF do plano de contas.') from exc
    pattern = re.compile(
        r'^[ \t]*(\d+)[ \t]+(S[ \t]+)?(\d+(?:\.\d+)*)[ \t]+(.+?)[ \t]{2,}(\d+)[ \t]*$',
        re.M,
    )
    chart = {}
    def registered_name(value):
        normalized = engine.normalizar_texto(value).strip()
        # O Domínio pode omitir a indicação de porte que consta no cadastro.
        return re.sub(r'\s+-\s+(?:me|epp)$', '', normalized)

    for page in pages:
        owner = re.search(r'Empresa:[ \t]*(.+?)[ \t]+Folha:', page)
        if not owner or registered_name(owner[1]) != registered_name(company_name):
            raise ValueError('O nome no plano de contas difere do cadastro desta empresa.')
        entries = pattern.findall(page)
        if not entries:
            raise ValueError('O plano precisa ser um relatório do Domínio com texto selecionável.')
        for code, synthetic, classification, name, _ in entries:
            if code in chart:
                raise ValueError('O PDF contém códigos repetidos. Exporte novamente o plano completo.')
            chart[code] = {'analitica': not synthetic, 'classificacao': classification, 'nome': name.strip()}
    if not chart:
        raise ValueError('Nenhuma conta foi localizada.')
    return chart


def save_company_chart(directory, company, chart):
    from tempfile import NamedTemporaryFile

    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(chart, stream, ensure_ascii=False)
            stream.flush()
            temp.replace(directory / f'{int(company)}.json')
        finally:
            temp.unlink(missing_ok=True)


def settled_titles_lookup(content, chart, bank_accounts):
    """Index a Domínio extract with an explicit account for each settled title."""
    import io
    from openpyxl import load_workbook

    if not chart:
        raise ValueError('Salve o plano de contas da empresa antes de usar títulos baixados.')
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError('Envie a planilha de títulos baixados no formato XLSX.') from exc

    required = {'contraparte', 'titulo', 'parcela', 'natureza', 'conta contabil'}
    titles = defaultdict(set)
    with_values = False
    try:
        for sheet in workbook:
            rows = sheet.iter_rows(values_only=True)
            header = None
            for row in rows:
                headings = [engine.normalizar_texto(engine.texto_celula_seguro(v)) for v in row]
                if required <= set(headings):
                    header = {name: headings.index(name) for name in required}
                    break
            if not header:
                continue
            for row in rows:
                values = {name: engine.texto_celula_seguro(row[index]) if index < len(row) else ''
                          for name, index in header.items()}
                name = engine.extrair_nome_empresa_classificacao(values['contraparte'], legado=True)
                nature = engine.normalizar_texto(values['natureza'])
                nature = {'pagamento': 'pago', 'saida': 'pago', 'recebimento': 'recebido', 'entrada': 'recebido'}.get(nature, nature)
                title, installment = values['titulo'], values['parcela']
                if len(name.split()) < 2 or nature not in _GROUP_BY_NATURE:
                    continue
                if not re.fullmatch(r'\d{3,10}', title) or not re.fullmatch(r'\d{1,2}', installment):
                    continue
                titles[nature, title, installment].add((name, values['conta contabil']))
                with_values = True
    finally:
        workbook.close()
    if not with_values:
        raise ValueError('Informe Contraparte, Título, Parcela, Natureza e Conta contábil em uma aba XLSX.')

    bank_codes = {str(code) for code in bank_accounts.values()}

    def find(_bank, nature, history, _date):
        doc = _document_identity(history)
        if not doc:
            return None
        name, title, installment = doc
        matches = {
            code for party, code in titles.get((nature, title, installment), ())
            if engine.calcular_similaridade_nome_empresa(name, party) >= .94
        }
        if len(matches) != 1:
            return None
        code = next(iter(matches))
        entry = chart.get(code)
        if not re.fullmatch(r'[1-9][0-9]{0,14}', code) or code in bank_codes:
            return None
        if not entry or not entry['analitica'] or entry['classificacao'] != _GROUP_BY_NATURE[nature]:
            return None
        if engine.calcular_similaridade_nome_empresa(name, entry['nome']) < .94:
            return None
        return code, 'por_titulo_baixado'

    return find

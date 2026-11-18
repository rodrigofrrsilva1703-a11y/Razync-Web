"""Optional Decision 1 pilot using aggregate evidence and temporary option IDs."""
import logging
import os

from app.ai_budget import request_slot

MODEL = 'gemini-decision-1'


def interpret(suggestions, key):
    groups = {}
    for suggestion in suggestions:
        group = suggestion['grupo']
        if suggestion['situacao'] != 'MANUAL' or group in groups:
            continue
        candidates = {}
        for evidence in suggestion['evidencias']:
            if evidence['mesmo_banco']:
                candidates.setdefault(evidence['conta'], []).append(evidence)
        if 2 <= len(candidates) <= 4:
            groups[group] = candidates
        if len(groups) == 8:
            break

    result = {
        'provedor': 'gemini', 'modelo': MODEL, 'estado': 'dispensada',
        'chamadas_nesta_execucao': 0, 'prioridades': [],
    }
    if not groups:
        return result

    questions, option_maps = {}, {}
    for group, candidates in groups.items():
        question = f'g{group}'
        criteria = {'revisar': 'Evidência insuficiente ou contas igualmente plausíveis.'}
        options = {}
        for index, (account, evidence) in enumerate(candidates.items(), 1):
            option = f'opcao_{index}'
            options[option] = account
            exact_periods = {p for e in evidence if e['exata'] or e.get('nome_exato') for p in e['periodos']}
            all_periods = {p for e in evidence for p in e['periodos']}
            criteria[option] = (
                f'{len(exact_periods)} períodos com assinatura ou nome coincidente e '
                f'{len(all_periods)} períodos ao considerar também similaridades.'
            )
        option_maps[question] = group, options
        questions[question] = {
            'type': 'choice',
            'instructions': (
                'Escolha uma opção somente se ela tiver assinatura ou nome coincidente em pelo menos '
                'dois períodos e evidência claramente superior a todas as demais. '
                'Em caso de dúvida escolha revisar.'
            ),
            'criteria': criteria,
        }

    context = 'Cada questão representa um lançamento contábil pendente independente.'
    try:
        result['chamadas_nesta_execucao'] = 1
        answers = request_choices(key, context, questions)
        selected = {}
        for question, (group, options) in option_maps.items():
            answer = answers[question]
            account = options.get(answer.choice)
            if account:
                exact_counts = {
                    candidate: len({p for e in evidence if e['exata'] or e.get('nome_exato') for p in e['periodos']})
                    for candidate, evidence in groups[group].items()
                }
                if exact_counts[account] >= 2 and exact_counts[account] > max(
                    count for candidate, count in exact_counts.items() if candidate != account
                ):
                    selected[group] = account
        for suggestion in suggestions:
            account = selected.get(suggestion['grupo'])
            if account:
                suggestion.update(
                    conta_sugerida=account, situacao='MODERADA',
                    justificativa='Gemini Decision 1 sugeriu a conta com maior evidência histórica. Confira antes de aprovar.',
                )
        return dict(
            result, estado='concluida', prioridades=[group for group in groups if group not in selected],
            motivo='Gemini Decision 1 avaliou os candidatos. Toda sugestão exige aprovação.',
        )
    except Exception as exc:
        logging.getLogger(__name__).warning('decision_pilot_failure type=%s', type(exc).__name__)
        return dict(result, estado='indisponivel', motivo='Gemini Decision 1 indisponível. A revisão local continua disponível.')


def configured_key():
    dedicated = os.getenv('GEMINI_DECISION_API_KEY', '').strip()
    if dedicated:
        return dedicated if os.getenv('GEMINI_DECISION_FREE_TIER_CONFIRMED') == '1' else ''
    if os.getenv('GEMINI_FREE_TIER_CONFIRMED') == '1':
        return os.getenv('GEMINI_API_KEY', '').strip()
    return ''


def request_choices(key, context, questions):
    from google import genai

    with request_slot('gemini', MODEL, {'contents': [context, questions]}) as usage:
        with genai.Client(api_key=key, http_options={'api_version': 'v1beta', 'timeout': 8000}) as client:
            response = client.decisions.create(model=MODEL, input=context, questions=questions)
        usage({})
    return response.answers


def classify_groups(key, groups):
    """Confirm candidates distinguished by locally extracted operation evidence."""
    options, questions = {}, {}
    for group, (operation, candidates) in enumerate(groups, 1):
        question = f'g{group}'
        criteria = {'revisar': 'As evidências não distinguem com segurança uma conta.'}
        options[question] = {}
        for index, (account, periods) in enumerate(sorted(candidates.items()), 1):
            option = f'opcao_{index}'
            options[question][option] = account, periods
            criteria[option] = f'{periods} período(s) com o mesmo fornecedor e tipo de operação.'
        questions[question] = {
            'type': 'choice',
            'instructions': (
                f'Tipo de operação identificado localmente: {operation}. '
                'Confirme apenas a opção com pelo menos dois períodos compatíveis e '
                'sem períodos compatíveis em outra opção. Se houver dúvida, escolha revisar.'
            ),
            'criteria': criteria,
        }
    try:
        answers = request_choices(key, 'Avalie cada lançamento de forma independente.', questions)
        accepted = {}
        for group, (question, candidates) in enumerate(options.items()):
            answer = answers.get(question)
            if answer is None or answer.choice not in candidates:
                continue
            account, periods = candidates[answer.choice]
            if periods >= 2 and all(not count for other, count in candidates.values() if other != account):
                if 0.95 <= (answer.confidence or 0) <= 1:
                    accepted[group] = account
        return accepted
    except Exception as exc:
        logging.getLogger(__name__).warning('classification_decision_failure type=%s', type(exc).__name__)
        return {}

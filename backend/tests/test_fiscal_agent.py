import unittest
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from app import fiscal_agent as agent


class DocumentaryAgentTests(unittest.TestCase):
    def setUp(self):
        agent._sessions.clear()
        self.scope = dict(conta='408', tipo='SAÍDAS', acumulador='', origem='documentos')
        self.report = dict(empresa=242, filial_aplicada='242', lancamentos=[
            dict(conta='408', filial='242', credito=3900, historico='VENDA CF NF 149599', data='13/08/2026'),
            dict(conta='470', filial='242', credito=300, historico='NF 149599', data='13/08/2026'),
            dict(conta='408', filial='1408', credito=999, historico='NF 149599', data='13/08/2026')])
        self.investigation = dict(resumo=dict(fiscal='100', contabil='4000', diferenca='3900'), hipoteses=[], limitacoes=[], composicao_diferenca={})
        self.docs = dict(documentos=[], comparacoes=[], razao_sem_vinculo=[dict(id='R-1')])
        self.token = agent.register(self.report, self.scope, self.docs, self.investigation)['session']

    def ask(self, question, ai=False):
        return agent.answer(SimpleNamespace(session=self.token, pergunta=question, usar_ia=ai))

    def test_default_search_isolates_account_and_branch(self):
        result = self.ask('Procure a nota 149599')
        self.assertEqual([r['referencia'] for r in result['evidencias']], ['R-1'])
        self.assertEqual(self.report['lancamentos'][0]['credito'], 3900)

    def test_other_accounts_require_explicit_note_and_never_include_other_branch(self):
        self.assertEqual(self.ask('Em outra conta?')['encontrados'], 0)
        result = self.ask('Procure a nota 149599 em outra conta')
        self.assertEqual([r['referencia'] for r in result['evidencias']], ['R-1', 'R-2'])

    def test_accumulator_scope_does_not_inherit_other_account_records(self):
        scope = dict(self.scope, acumulador='5405')
        docs = dict(self.docs, comparacoes=[dict(lancamentos=[dict(id='R-1')])])
        self.token = agent.register(self.report, scope, docs, self.investigation)['session']
        self.assertEqual(self.ask('Nota 149599 em outra conta')['encontrados'], 0)

    def test_pergunta_de_acompanhamento_reutiliza_tema_da_conta(self):
        primeiro = self.ask('Quais movimentos devo olhar primeiro?')
        self.assertEqual(primeiro['intencao'], 'movimentos')
        proxima = self.ask('E o que mais posso analisar?')
        self.assertEqual(proxima['intencao'], 'movimentos')
        self.assertTrue(proxima['comparacao'])
        self.assertEqual(self.ask('Quanto deu o fiscal?')['intencao'], 'totais')
        self.assertEqual(self.ask('E sobre isso?')['intencao'], 'totais')

    def test_ia_gratuita_pode_explicar_total_sem_registros_individuais(self):
        context = dict(self.investigation, resumo=dict(fiscal='5000',contabil='2900',diferenca='-2100'))
        self.token = agent.register(self.report, dict(self.scope, origem='resumo'), None, context)['session']
        with patch.object(agent, 'interpret', return_value=dict(
            explicacao='A diferença existe, mas faltam documentos.',
            proximos_passos=['Solicite o acompanhamento fiscal.'],
            referencias=['CONSULTA'], provedor='teste', modelo='gratuito')) as call:
            result = self.ask('Por que essa conta não fecha?', True)
            self.assertEqual(result['intencao'], 'diferenca')
            self.assertEqual(result['origem'], 'ia')
            self.assertEqual(result['encontrados'], 0)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[1][0]['referencia'], 'CONSULTA')

    def test_investigation_question_invokes_bounded_tool_agent(self):
        result_data = dict(explicacao='Diferença sob investigação documental.',
            proximos_passos=['Confira as notas desta competência.'],
            referencias=['RESUMO'], provedor='groq', modelo='gratuito',
            ferramentas_executadas=['obter_contexto_conta', 'consultar_indicios'],
            iteracoes=3, status_diagnostico='EVIDENCIA_PARCIAL')
        with patch('app.fiscal_agent_loop.investigate', return_value=result_data) as mocked:
            result = self.ask('Investigue a diferença desta conta.', True)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(result['origem'], 'ia')
        self.assertEqual(result['ferramentas_ia'], result_data['ferramentas_executadas'])
        self.assertEqual(result['diagnostico_ia'], 'EVIDENCIA_PARCIAL')

    def test_agent_fallback_for_model_without_tools_remains_free(self):
        from app.fiscal_agent_loop import UnsupportedTools
        with patch('app.fiscal_agent_loop.investigate', side_effect=UnsupportedTools('not supported')):
            with patch.object(agent, 'interpret', return_value=dict(
                explicacao='A diferença está confirmada pelos totais.',
                proximos_passos=['Confira os documentos.'], referencias=['CONSULTA'],
                provedor='groq', modelo='gratuito')) as fallback:
                result = self.ask('Investigue a diferença.', True)
        self.assertEqual(fallback.call_count, 1)
        self.assertEqual(result['origem'], 'ia')
        self.assertNotIn('ferramentas_ia', result)

    def test_invalid_tool_output_keeps_safe_local_answer(self):
        from app.fiscal_agent_loop import InvalidAgentReply
        with patch('app.fiscal_agent_loop.investigate', side_effect=InvalidAgentReply('invalid')):
            result = self.ask('Investigue a diferença.', True)
        self.assertEqual(result['origem'], 'local')
        self.assertIn('aviso_ia', result)
        self.assertEqual(result['comparacao']['diferenca'], '3900')

    def test_chat_aproveita_indicios_calculados_sem_provar_causa(self):
        investigation = dict(self.investigation, hipoteses=[{
            'id': 'H1', 'categoria': 'competencia',
            'titulo': 'Movimento em competência diferente',
            'explicacao': 'O período precisa ser conferido no relatório.',
            'grau': 'hipotese', 'referencias': ['R-1'],
            'falta_confirmar': 'Confirme o documento original e as datas.'
        }])
        self.token = agent.register(self.report, self.scope, self.docs, investigation)['session']
        response = self.ask('O que você encontrou nessa conta?')
        self.assertIn('Movimento em competência diferente', ' '.join(response['fatos']))
        self.assertIn('Confirme o documento original', ' '.join(response['pontos_confirmar']))
        self.assertEqual(response['origem'], 'local')
        with patch.object(agent, 'interpret', return_value=dict(
            explicacao='Verifique a data antes de decidir.',
            proximos_passos=[], referencias=['CONSULTA'], provedor='teste', modelo='teste')) as call:
            result = self.ask('Existe problema de competência nessa conta?', True)
            self.assertEqual(result['origem'], 'ia')
            context = call.call_args.args[1][0]
            self.assertEqual(context['indicios_calculados'][0]['id'], 'H1')
            self.assertNotIn('historico', json.dumps(context, ensure_ascii=False))

    def test_perguntas_abertas_mantem_contexto_da_conta_e_resumo(self):
        examples = {
            'Me ajuda a entender tudo que está acontecendo aqui?': 'geral',
            'O que você consegue analisar nesta conta?': 'geral',
            'Quanto deu o fiscal e quanto deu o razão?': 'totais',
            'Quais lançamentos devo olhar primeiro?': 'movimentos',
            'Existem registros de outra competência?': 'competencia',
            'Quais acumuladores estão nessa conta?': 'acumulador',
            'Tem alguma combinação de valores que explique?': 'combinacao',
        }
        for question, intent in examples.items():
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertEqual(result['intencao'], intent)
                self.assertEqual(result['comparacao']['diferenca'], '3900')
                self.assertNotIn('Nenhum registro encontrado', result['titulo'])
                self.assertTrue(result['proximos_passos'])
                self.assertEqual(result['recorte'], 'Conta 408 · SAÍDAS')

    def test_questions_about_one_note_and_duplicates_still_use_specific_search(self):
        self.prepare_note_pair()
        self.assertEqual(agent.query_plan('Qual a diferença da nota 149353?')['intent'], 'documento')
        self.assertEqual(agent.query_plan('A nota 149353 está duplicada?')['intent'], 'duplicidade')
        self.assertEqual(self.ask('A nota 149353 está duplicada?')['intencao'], 'duplicidade')

    def test_natural_question_why_account_does_not_match_uses_totals(self):
        """Reproduz a pergunta mostrada na conta 362 no chat."""
        questions = [
            'Por que essa conta não está batendo?',
            'Porque a conta 362 não está fechando?',
            'Por que o Razão não confere com o fiscal?',
            'Os valores não estão correspondendo, qual a causa?',
            'Qual é o problema da conta 362?',
            'Por que a conta não bate?',
            'Por que esta conta não está batendo em R$ 25.549,09?',
        ]
        for question in questions:
            with self.subTest(question=question):
                plan = agent.query_plan(question)
                self.assertEqual(plan['intent'], 'diferenca')
                self.assertIsNone(plan['valor'])
                result = self.ask(question)
                self.assertEqual(result['intencao'], 'diferenca')
                self.assertEqual(result['titulo'], 'Composição da diferença da conta')
                self.assertIsNotNone(result['comparacao'])
                self.assertIn('Razão está', result['explicacao'])
                self.assertNotIn('Nenhum registro encontrado', result['titulo'])

    def test_natural_difference_without_individual_fiscal_documents(self):
        scope = dict(self.scope, origem='resumo')
        self.token = agent.register(self.report, scope, None, self.investigation)['session']
        result = self.ask('Por que essa conta não está batendo?')
        self.assertEqual(result['intencao'], 'diferenca')
        self.assertIn('3.900,00', result['explicacao'])
        self.assertIn('acompanhamento fiscal', ' '.join(result['proximos_passos']))
        self.assertIn('documento fiscal', ' '.join(result['pontos_confirmar']))
        self.assertEqual(result['origem'], 'local')

    def test_explicit_note_and_amount_search_still_take_priority(self):
        self.assertEqual(agent.query_plan('Por que a nota 149599 não bate?')['intent'], 'documento')
        self.assertEqual(agent.query_plan('Procure o valor R$ 3.900,00')['intent'], 'valor')
        self.assertEqual(agent.query_plan('Procure o valor R$ 3.900,00')['valor'], '3900.00')

    def test_difference_question_with_amount_keeps_account_diagnostic(self):
        """Perguntar por que não fecha não deve virar busca de valor isolado."""
        investigation = dict(self.investigation, resumo=dict(fiscal='5100', contabil='3000', diferenca='-2100'))
        self.token = agent.register(self.report, dict(self.scope, origem='resumo'), None, investigation)['session']
        result = self.ask('Por que existe uma divergência de R$ 2.100,00 nesta conta?')
        self.assertEqual(result['intencao'], 'diferenca')
        self.assertEqual(result['comparacao']['diferenca'], '-2100')
        self.assertIn('R$ 2.100,00', result['explicacao'])
        self.assertIn('acompanhamento fiscal', ' '.join(result['proximos_passos']))
        self.assertIn('documento fiscal', ' '.join(result['pontos_confirmar']))
        self.assertEqual(result['encontrados'], 0)

    def test_explicit_value_search_is_still_available(self):
        self.assertEqual(agent.query_plan('Procure o valor R$ 3.900,00')['intent'], 'valor')
        self.assertEqual(self.ask('Procure o valor R$ 3.900,00')['encontrados'], 1)

    def test_equal_difference_amount_is_candidate_not_proof(self):
        self.token = agent.register(self.report, dict(self.scope, origem='resumo'), None, self.investigation)['session']
        result = self.ask('Explique a diferença de R$ 3.900,00')
        self.assertEqual(result['intencao'], 'diferenca')
        self.assertEqual(result['encontrados'], 1)
        self.assertIn('Coincidência', result['ferramenta'])
        self.assertIn('não prova', ' '.join(result['pontos_confirmar']))
        self.assertNotIn('causa comprovada', result['explicacao'])

    def test_unlinked_question_without_fiscal_documents_explains_limitation(self):
        self.token = agent.register(self.report, dict(self.scope, origem='resumo'), None, self.investigation)['session']
        result = self.ask('Quais movimentos estão sem vínculo?')
        self.assertEqual(result['encontrados'], 0)
        self.assertIn('detalhamento fiscal', result['titulo'])
        self.assertIn('não identificam', result['explicacao'])

    def test_same_question_reuses_answer_and_ai_is_opt_in(self):
        with patch.object(agent, 'interpret') as call:
            self.ask('Explique a diferença')
            self.assertTrue(self.ask('Explique a diferença')['cache_reutilizado'])
            call.assert_not_called()

    def prepare_note_pair(self, ambiguous=False):
        self.report['lancamentos'][0].update(credito=915,historico='VENDA CF NF 149353')
        docs=dict(documentos=[dict(id='S-1',nota='149353',serie='0',data='13/08/2026',valor=1095)],
            comparacoes=[dict(nota='149353',serie='0',data='13/08/2026',situacao='AMBIGUO' if ambiguous else 'VALOR_DIFERENTE',valor_fiscal=1095,valor_razao=915,diferenca=-180,
                linhas_fiscais=[dict(id='S-1')],lancamentos=[dict(id='R-1',conta='408')])],razao_sem_vinculo=[])
        self.token=agent.register(self.report,self.scope,docs,self.investigation)['session']

    def test_note_answer_uses_document_values_instead_of_account_totals(self):
        self.prepare_note_pair()
        result=self.ask('Compare a nota 149353')
        self.assertEqual(result['comparacao']['fiscal'],1095)
        self.assertEqual(result['comparacao']['diferenca'],'-180.00')
        self.assertIn('180,00',result['explicacao'])
        self.assertNotIn('3.900',result['explicacao'])
        self.assertTrue(result['acoes'])

    def test_missing_and_ambiguous_counterpart_never_become_zero(self):
        result=self.ask('Nota 149599')
        self.assertIsNone(result['comparacao'])
        self.assertIn('ausente não foi tratado como zero',result['explicacao'])
        self.prepare_note_pair(ambiguous=True)
        self.assertIsNone(self.ask('Compare a nota 149353')['comparacao'])

    def test_document_date_filter_keeps_the_linked_ledger_even_when_dates_differ(self):
        self.prepare_note_pair()
        record=agent._sessions[self.token]['data']['records'][0]
        record['data']='14/08/2026'
        result=self.ask('Compare nota 149353 série 0 de 13/08/2026')
        self.assertEqual({r['referencia'] for r in result['evidencias']},{'R-1','S-1'})
        self.assertEqual(result['comparacao']['diferenca'],'-180.00')

    def test_reference_and_negative_exact_amount_search(self):
        self.assertEqual(self.ask('Mostre R-1')['encontrados'],1)
        self.report['lancamentos'][0]['credito']=-3900
        self.token=agent.register(self.report,self.scope,self.docs,self.investigation)['session']
        self.assertEqual(self.ask('Procure valor -3.900,00')['encontrados'],1)

    def test_duplicate_check_does_not_confuse_counterpart_or_installment(self):
        self.prepare_note_pair()
        self.assertIn('Sem repetição',self.ask('Existe duplicidade na nota 149353?')['titulo'])
        self.report['lancamentos'].append(dict(self.report['lancamentos'][0],credito=200))
        self.token=agent.register(self.report,self.scope,self.docs,self.investigation)['session']
        self.assertIn('Sem repetição',self.ask('Nota 149353 duplicada?')['titulo'])
        self.report['lancamentos'].append(dict(self.report['lancamentos'][0]))
        self.token=agent.register(self.report,self.scope,self.docs,self.investigation)['session']
        result=self.ask('Nota 149353 duplicada?')
        self.assertIn('Possível repetição',result['titulo'])
        self.assertEqual(result['encontrados'],2)
        self.assertIsNone(result['comparacao'])

    def test_followup_and_cached_note_restore_the_correct_subject(self):
        self.ask('Nota 149599')
        self.ask('Nota 999999')
        self.assertTrue(self.ask('Nota 149599')['cache_reutilizado'])
        result=self.ask('E em outra conta?')
        self.assertEqual(result['encontrados'],2)
        self.assertEqual(result['nota_contexto'],'149599')

    def test_other_account_search_distinguishes_only_current_account_from_other_accounts(self):
        self.assertIn('470',self.ask('Nota 149599 em outra conta')['explicacao'])
        self.prepare_note_pair()
        result=self.ask('Nota 149353 em outras contas')
        self.assertIn('somente na conta 408',result['explicacao'])
        self.assertIsNone(result['comparacao'])
        self.assertIn('SAÍDAS',result['recorte'])

    def test_natural_next_step_keeps_note_but_explicit_account_question_resets_scope(self):
        self.prepare_note_pair()
        self.ask('Compare a nota 149353')
        result=self.ask('Como posso resolver?')
        self.assertEqual(result['nota_contexto'],'149353')
        self.assertEqual(result['comparacao']['diferenca'],'-180.00')
        result=self.ask('O que conferir primeiro na conta inteira?')
        self.assertEqual(result['intencao'],'diferenca')
        self.assertTrue(result['comparacao']['rotulo'].startswith('Conta'))

    def test_note_ai_context_excludes_account_summary_and_cannot_replace_local_facts(self):
        self.prepare_note_pair()
        with patch.object(agent,'interpret',return_value=dict(explicacao='Confira as parcelas.',proximos_passos=[],referencias=['S-1'],provedor='teste',modelo='teste')) as call:
            result=self.ask('Compare a nota 149353',True)
            self.assertIn('180,00',result['explicacao'])
            self.assertEqual(result['interpretacao_ia'],'Confira as parcelas.')
            self.assertNotIn('3.900',json.dumps(call.call_args.args[1],ensure_ascii=False))
            self.assertEqual(result['comparacao']['diferenca'],'-180.00')

    def test_amount_search_does_not_create_link_and_followup_keeps_document(self):
        result = self.ask('Procure o valor R$ 3.900,00')
        self.assertEqual(result['encontrados'], 1)
        self.ask('Procure a nota 149599')
        self.assertEqual(self.ask('E essa nota?')['encontrados'], 1)

    def test_document_status_comes_from_comparisons_not_raw_document_defaults(self):
        docs = dict(self.docs, documentos=[dict(id='S-1',nota='12',valor=100,situacao='LIDO'),dict(id='S-2',nota='13',valor=120,situacao='LIDO')],
            comparacoes=[dict(situacao='CONCILIADO',linhas_fiscais=[dict(id='S-1')]),dict(situacao='VALOR_DIFERENTE',linhas_fiscais=[dict(id='S-2')])])
        self.token=agent.register(self.report,self.scope,docs,self.investigation)['session']
        result=self.ask('Explique as pendências')
        self.assertNotIn('S-1',[r['referencia'] for r in result['evidencias']])
        self.assertIn('S-2',[r['referencia'] for r in result['evidencias']])
        self.assertEqual([r['referencia'] for r in self.ask('Quais estão sem vínculo?')['evidencias']],['R-1'])

    def test_unclassified_raw_lines_are_not_reported_as_confirmed_pending(self):
        docs = dict(self.docs, documentos=[dict(id='S-1',nota='12',valor=100,situacao='LIDO')])
        self.token=agent.register(self.report,self.scope,docs,self.investigation)['session']
        self.assertEqual([r['referencia'] for r in self.ask('Explique a diferença')['evidencias']],['R-1'])

    def test_external_context_does_not_include_histories(self):
        with patch.object(agent, 'interpret', return_value=dict(explicacao='Confira o documento.', proximos_passos=[], referencias=['R-1'], provedor='teste', modelo='teste')) as call:
            result = self.ask('Nota 149599', True)
            self.assertEqual(result['origem'], 'ia')
            self.assertTrue(all('historico' not in fact for fact in call.call_args.args[1][1:]))
            self.assertNotIn('empresa_nome', call.call_args.args[1][0])

    def test_provider_request_headers_and_brazilian_amount_validation(self):
        @contextmanager
        def slot(*args):
            yield lambda raw: None
        response = dict(choices=[dict(finish_reason='stop', message=dict(content=json.dumps(dict(
            explicacao='Confira R$ 3.698,89 em RESUMO e R$ 3.900,00 em R-902.', proximos_passos=['Confira R-902.'], referencias=['RESUMO','R-902']))))])
        modules = {'app.fiscal_hybrid_ai': SimpleNamespace(choose_provider=lambda: ('groq','openai/gpt-oss-120b','test-key')),
            'app.ai_budget': SimpleNamespace(request_slot=slot), 'app.groq_fiscal': SimpleNamespace(API_URL='https://example.test/ai')}
        with patch.dict('sys.modules', modules), patch.object(agent.urllib.request,'urlopen') as send:
            send.return_value.__enter__.return_value.read.return_value=json.dumps(response).encode()
            result=agent.interpret('Explique a diferença', [dict(referencia='RESUMO',diferenca='3698.89'),dict(referencia='R-902',valor=3900.0)])
            self.assertEqual(result['referencias'],['RESUMO','R-902'])
            self.assertEqual(send.call_args.args[0].get_header('User-agent'),'Razync-Web/1.0')
            agent.interpret('CPF 123.456.789-09 CNPJ 12.345.678/0001-99 e-mail teste@example.com telefone +55 (11) 98765-4321', [
                dict(referencia='RESUMO', diferenca='3698.89'),dict(referencia='R-902',valor=3900.0)])
            external_body = send.call_args.args[0].data.decode()
            for secret in ('123.456.789-09', '12.345.678/0001-99', 'teste@example.com', '+55 (11) 98765-4321'):
                self.assertNotIn(secret, external_body)
            self.assertIn('[DOCUMENTO]', external_body)
            self.assertIn('[EMAIL]', external_body)
            self.assertIn('[TELEFONE]', external_body)
            response['choices'][0]['message']['content']=json.dumps(dict(explicacao='Diferença de R$ 8.888,88.',proximos_passos=[],referencias=['RESUMO']))
            send.return_value.__enter__.return_value.read.return_value=json.dumps(response).encode()
            with self.assertRaisesRegex(ValueError,'Número não confirmado'):
                agent.interpret('Explique',[dict(referencia='RESUMO',diferenca='3698.89')])

    def test_failure_retains_local_evidence_without_fake_ai_attribution(self):
        with patch.object(agent, 'interpret', side_effect=ValueError('invalid')):
            result = self.ask('Nota 149599', True)
            self.assertEqual(result['origem'], 'local')
            self.assertEqual(result['encontrados'], 1)
            self.assertIn('aviso_ia', result)

    def test_expired_unknown_and_busy_sessions_are_rejected(self):
        agent._sessions[self.token]['busy'] = True
        with self.assertRaises(agent.AgentError) as err:
            self.ask('Nota 149599')
        self.assertEqual(err.exception.status_code, 409)
        agent._sessions[self.token]['expires'] = 0
        with self.assertRaises(agent.AgentError) as err:
            self.ask('Nota 149599')
        self.assertEqual(err.exception.status_code, 410)

    def test_twenty_question_limit_and_missing_document_are_explicit(self):
        self.assertIn('não comprova', self.ask('Nota 999999')['explicacao'])
        agent._sessions[self.token]['count'] = 20
        with self.assertRaises(agent.AgentError) as err:
            self.ask('Outra pergunta')
        self.assertEqual(err.exception.status_code, 429)


if __name__ == '__main__':
    unittest.main()

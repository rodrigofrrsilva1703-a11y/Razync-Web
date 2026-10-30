import unittest
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

    def test_same_question_reuses_answer_and_ai_is_opt_in(self):
        with patch.object(agent, 'interpret') as call:
            self.ask('Explique a diferença')
            self.assertTrue(self.ask('Explique a diferença')['cache_reutilizado'])
            call.assert_not_called()

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

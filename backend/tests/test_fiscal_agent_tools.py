"""Regressões do agente de ferramentas, sem APIs externas e sem escrita."""
import json
import unittest
from unittest.mock import patch

from app import fiscal_agent_tools as tools
from app import fiscal_agent_loop as agent


class FiscalToolsTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "scope": {"conta": "408", "tipo": "SAÍDAS", "acumulador": "", "origem": "resumo"},
            "resumo": {"fiscal": "5000.00", "contabil": "4500.00", "diferenca": "-500.00"},
            "records": [
                {"referencia": "R-1", "origem": "Razão", "conta": "408", "data": "10/08/2026",
                 "valor": "300.00", "historico": "NF 123 Parceiro confidencial"},
                {"referencia": "R-2", "origem": "Razão", "conta": "408", "data": "11/08/2026",
                 "valor": "200.00", "historico": "Transferencia"},
                {"referencia": "R-3", "origem": "Razão", "conta": "999", "data": "12/08/2026",
                 "valor": "500.00", "historico": "Conta que nao pertence a selecao"},
                {"referencia": "D-1", "origem": "Fiscal", "conta": "408", "data": "10/08/2026",
                 "valor": "300.00", "nota": "123", "historico": "Cliente sigiloso"},
            ],
            "pending": ["R-1"], "unlinked": ["R-1"], "tem_documentos": True,
            "comparacoes": [{"nota": "123", "situacao": "VALOR_DIFERENTE",
                             "diferenca": "25.00", "referencias": ["R-1", "D-1"],
                             "completo": True, "mesma_conta": True}],
            "hipoteses": [{"id": "H1", "categoria": "competencia", "titulo": "Data diferente",
                           "grau": "hipotese", "referencias": ["R-1"],
                           "falta_confirmar": "Documento original"}],
            "limites": ["Competencia adjacente nao enviada"],
            "composicao": {"itens": []},
        }

    def test_context_and_scope(self):
        result = tools.execute(self.data, "obter_contexto_conta", {})
        self.assertEqual(result["diferenca_razao_menos_fiscal"], "-R$ 500,00")
        self.assertEqual(result["registros_razao"], 2)
        with self.assertRaises(tools.ToolInputError):
            tools.execute(self.data, "obter_contexto_conta", {"empresa": "1408"})
        with self.assertRaises(tools.ToolInputError):
            tools.execute(self.data, "buscar_movimentos_razao", {"natureza": "Tudo"})
        with self.assertRaises(tools.ToolInputError):
            tools.execute(self.data, "executar_python", {})

    def test_documentary_requires_actual_documents(self):
        result = tools.execute(self.data, "cruzar_documentos_fiscais_razao", {})
        self.assertEqual(result["total_pendencias"], 1)
        self.assertEqual(result["pendencias"][0]["referencias"], ["R-1", "D-1"])
        self.data["tem_documentos"] = False
        result = tools.execute(self.data, "cruzar_documentos_fiscais_razao", {})
        self.assertEqual(result["situacao"], "REQUER_ANEXO_FISCAL")

    def test_movement_response_never_sends_raw_history_or_other_account(self):
        result = tools.execute(self.data, "buscar_movimentos_razao", {"natureza": "Razão"})
        self.assertEqual(result["encontrados"], 2)
        output = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("confidencial", output)
        self.assertNotIn("Conta que nao pertence", output)
        self.assertNotIn("R-3", output)
        self.assertEqual(result["movimentos"][0]["referencia"], "R-1")

    def test_integer_cents_subset_and_double_are_not_proof(self):
        result = tools.execute(self.data, "testar_hipotese_matematica",
                               {"tipo_teste": "COMBINACAO_SUBCONJUNTO", "referencias": ["R-1", "R-2"]})
        self.assertEqual(result["combinacoes"], [["R-1", "R-2"]])
        self.assertFalse(result["provado"])
        result = tools.execute(self.data, "testar_hipotese_matematica",
                               {"tipo_teste": "SOMA_DIRETA", "referencias": ["R-1", "R-2"]})
        self.assertEqual(result["soma"], "R$ 500,00")
        self.assertTrue(result["fecha"])
        with self.assertRaises(tools.ToolInputError):
            tools.execute(self.data, "testar_hipotese_matematica",
                          {"tipo_teste": "SOMA_DIRETA", "referencias": ["R-3"]})

    def test_bounded_tool_schemas(self):
        self.assertEqual(len(tools.openai_tools()), 6)
        self.assertEqual(len(tools.gemini_declarations()), 6)
        self.assertTrue(all(x["function"]["parameters"]["additionalProperties"] is False
                            for x in tools.openai_tools()))

    def test_agent_iterates_using_verified_tools(self):
        requests = []
        def invoke(option, messages):
            requests.append(messages)
            if len(requests) == 1:
                return "", [{"id": "call-1", "type": "function",
                             "function": {"name": "buscar_movimentos_razao",
                                          "arguments": '{"natureza":"Razão"}'}}]
            if len(requests) == 2:
                self.assertEqual(messages[-1]["role"], "tool")
                return "", [{"id": "call-2", "type": "function",
                             "function": {"name": "testar_hipotese_matematica",
                                          "arguments": '{"tipo_teste":"COMBINACAO_SUBCONJUNTO","referencias":["R-1","R-2"]}'}}]
            return json.dumps({"explicacao": "O total pode ser explicado por uma combinação de R$ 500,00; isso não confirma erro.",
                               "proximos_passos": ["Verifique as notas originais."],
                               "referencias": ["RESUMO", "R-1", "R-2"]}, ensure_ascii=False), []
        with patch.object(agent, "_invoke", side_effect=invoke):
            result = agent.investigate("Investigue a diferença", self.data,
                                       option=("groq", "modelo-free", "chave-ficticia"))
        self.assertEqual(result["ferramentas_executadas"],
                         ["buscar_movimentos_razao", "testar_hipotese_matematica"])
        self.assertEqual(result["iteracoes"], 3)
        self.assertEqual(result["status_diagnostico"], "EVIDENCIA_PARCIAL")
        self.assertEqual([x["situacao"] for x in result["passos_agente"]], ["concluido", "concluido"])
        self.assertIn("movimento(s)", result["passos_agente"][0]["resumo"])
        self.assertIn("combinação", result["passos_agente"][1]["resumo"])
        self.assertNotIn("confidencial", json.dumps(result["passos_agente"], ensure_ascii=False))
        self.assertEqual(len(requests), 3)

    def test_agent_step_with_missing_fiscal_document_is_not_marked_complete(self):
        self.data["tem_documentos"] = False
        result = agent._step_summary(
            "cruzar_documentos_fiscais_razao",
            tools.execute(self.data, "cruzar_documentos_fiscais_razao", {}))
        self.assertEqual(result["situacao"], "dados_insuficientes")
        self.assertIn("não anexado", result["resumo"])
        invalid = agent._step_summary("buscar_movimentos_razao", {"erro": "consulta recusada"})
        self.assertEqual(invalid["situacao"], "nao_executado")

    def test_agent_rejects_fabricated_refs(self):
        with patch.object(agent, "_invoke", return_value=(json.dumps({
            "explicacao": "Lancamento inventado.", "proximos_passos": [],
            "referencias": ["R-1000"]}), [])):
            with self.assertRaises(agent.InvalidAgentReply):
                agent.investigate("Analise tudo", self.data,
                                  option=("gemini", "free", "ficticia"))

    def test_full_question_is_sanitized_before_model(self):
        message = agent._sanitize("CPF 123.456.789-09 CNPJ 12.345.678/0001-99 e teste@example.com")
        self.assertNotIn("123.456.789-09", message)
        self.assertNotIn("12.345.678/0001-99", message)
        self.assertNotIn("teste@example.com", message)


if __name__ == "__main__":
    unittest.main()

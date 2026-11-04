import ast
import io
import json
from pathlib import Path
import unittest
import urllib.error


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'app'/'classification_agent_ai.py'
        tree=ast.parse(path.read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_http_diagnostic')
        scope={'urllib':urllib,'json':json}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
        self.diagnose=scope['_http_diagnostic']

    def test_distinguishes_key_network_model_and_quota_without_returning_raw_text(self):
        cases=[(401,'{"error":{"code":"invalid_api_key","message":"secret-key-example"}}','chave_invalida'),
               (403,'<html>Cloudflare access denied secret-key-example</html>','bloqueio_de_rede'),
               (404,'{"error":{"message":"model not found for API version secret-key-example"}}','modelo_indisponivel'),
               (429,'{"error":{"code":"RESOURCE_EXHAUSTED","message":"secret-key-example"}}','cota_excedida'),
               (403,'{"error":{"code":"PERMISSION_DENIED"}}','permissao_negada'),
               (400,'{"error":{"code":"INVALID_ARGUMENT"}}','parametro_invalido')]
        for status,body,category in cases:
            with self.subTest(category=category):
                result=self.diagnose(urllib.error.HTTPError('https://example.test',status,'denied',{},io.BytesIO(body.encode())))
                self.assertEqual(result['http_status'],status)
                self.assertEqual(result['erro_provedor'],category)
                self.assertNotIn('secret-key-example',json.dumps(result))

    def test_unknown_response_still_does_not_escape_into_diagnostics(self):
        result=self.diagnose(urllib.error.HTTPError('https://example.test',503,'denied',{},io.BytesIO(b'private-content')))
        self.assertEqual(result['erro_provedor'],'sem_categoria_conhecida')
        self.assertNotIn('private-content',json.dumps(result))

    def test_local_refusal_has_a_distinct_origin(self):
        class Refusal(Exception):status_code=429
        result=self.diagnose(Refusal())
        self.assertEqual(result,{'http_status':429,'origem_erro':'limite_local','erro_provedor':'limite_local'})

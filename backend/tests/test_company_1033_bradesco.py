"""Regressões do Bradesco 1033 (amostra sintética; nenhum documento real no Git)."""
import unittest
from unittest.mock import patch

from app.bradesco_1033 import read_statement


def line(y, *items):
    return [{'top':float(y),'x0':float(x),'text':text} for x,text in items]


class FakePage:
    def __init__(self, valid=True):
        self.valid = valid

    def extract_text(self):
        account = '0106702-8' if self.valid else '99999-9'
        return ('Extrato de: Ag: 1432 | CC: '+account+' | Entre 01/08/2026 e 31/08/2026\n'
                'Data Lançamento Dcto. Crédito (R$) Débito (R$) Saldo (R$)')

    def extract_words(self, **kwargs):
        return sum([
            line(220,(44,'Data'),(104,'Lançamento'),(519,'Saldo')),
            line(240,(41,'31/07/2026'),(101,'SALDO'),(130,'ANTERIOR'),(544,'42,88')),
            line(251,(101,'TRANSF'),(135,'AUTORIZ'),(175,'ENTRE'),(220,'AGS')),
            line(255,(41,'13/08/2026'),(266,'1432197'),(364,'183,60'),(540,'226,48')),
            line(260,(101,'DESTINATARIO'),(184,'EXEMPLO')),
            line(270,(41,'14/08/2026'),(101,'RENTAB.INVEST'),(164,'FACILCRED*'),(266,'272783'),(373,'0,01'),(540,'226,49')),
            line(280,(101,'TARIFA'),(145,'BANCARIA')),
            line(285,(266,'30826'),(449,'-183,60'),(544,'42,89')),
            line(289,(101,'CestaEmpresarial2')),
            line(299,(101,'BLOQUEIO-ORDEM'),(174,'JUDICIAL')),
            line(304,(41,'18/08/2026'),(266,'39240'),(458,'-1,00'),(544,'41,89')),
            line(308,(101,'OFICIO'),(129,'20260000000000-00001')),
            line(320,(41,'Total'),(364,'183,61'),(449,'-184,60'),(544,'41,89')),
        ], [])


class FakeDocument:
    def __init__(self, valid=True):
        self.pages = [FakePage(valid)]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class Bradesco1033Tests(unittest.TestCase):
    @patch('app.bradesco_1033.pdfplumber.open', return_value=FakeDocument())
    def test_four_movements_and_statement_balances(self, _):
        frame = read_statement(b'%PDF synthetic')
        self.assertEqual(frame['VALOR'].tolist(), [183.60, 0.01, -183.60, -1.00])
        self.assertEqual(frame['DÉBITO'].tolist(), ['9','9','',''])
        self.assertEqual(frame['CRÉDITO'].tolist(), ['','','9','9'])
        self.assertEqual(frame['DATA'].dt.strftime('%d/%m/%Y').tolist(),
                         ['13/08/2026','14/08/2026','14/08/2026','18/08/2026'])
        self.assertIn('TARIFA BANCARIA', frame['HISTÓRICO'].iloc[2])
        self.assertIn('OFICIO', frame['HISTÓRICO'].iloc[3])

    @patch('app.bradesco_1033.pdfplumber.open', return_value=FakeDocument(False))
    def test_wrong_account_rejected(self, _):
        with self.assertRaisesRegex(ValueError, 'conta bancária'):
            read_statement(b'%PDF synthetic')

    def test_workflow_routing(self):
        from app.migration_services import _workflow
        with patch('app.bradesco_1033.workflow_1033', return_value=(b'xlsx','ok.xlsx')) as processor:
            result = _workflow(1033, {'extrato': []}, {})
        self.assertEqual(result, (b'xlsx','ok.xlsx'))
        processor.assert_called_once()


if __name__ == '__main__':
    unittest.main()

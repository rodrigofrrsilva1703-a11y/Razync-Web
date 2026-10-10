import os
import sys
from pathlib import Path
import pytest
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'legacy'))
sys.path.insert(0, str(ROOT))
os.environ['RAZYNC_DB_PATH'] = str(ROOT / 'tests' / '.test-data.db')

@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    from app import classification_service, tasks, groq_fiscal, fiscal_ai
    # Testes de adaptadores usam respostas sintéticas sem consumir cotas reais.
    # O controle compartilhado é exercitado separadamente em test_ai_budget.
    @contextmanager
    def synthetic_slot(*args):
        yield lambda raw: None
    monkeypatch.setattr(groq_fiscal, "request_slot", synthetic_slot)
    monkeypatch.setattr(fiscal_ai, "request_slot", synthetic_slot)
    monkeypatch.setattr(groq_fiscal, "_quota_cooldowns", {})
    monkeypatch.setattr(classification_service, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setattr(tasks, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.chdir(ROOT)

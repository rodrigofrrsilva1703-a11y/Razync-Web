import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'legacy'))
sys.path.insert(0, str(ROOT))
os.environ['RAZYNC_DB_PATH'] = str(ROOT / 'tests' / '.test-data.db')

@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    from app import classification_service, tasks
    monkeypatch.setattr(classification_service, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setattr(tasks, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.chdir(ROOT)

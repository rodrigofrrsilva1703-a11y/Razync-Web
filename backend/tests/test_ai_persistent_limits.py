import json
import os
import sqlite3
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from app import ai_budget, ai_result_cache


def test_cache_criptografado_no_volume_existente(monkeypatch, tmp_path):
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    monkeypatch.setenv("RAZYNC_AI_CACHE_KEY", Fernet.generate_key().decode("ascii"))
    digest = ai_result_cache.stable_digest(json.dumps({"empresa": "XYZ", "conta": "501"}))
    assert isinstance(digest, str) and len(digest) == 64
    result = {"analises": [{"conta": "501", "explicacao": "Sigilo empresarial fictício",
                            "auditoria": {"situacao": "conferencia_assistida"}}]}
    assert ai_result_cache.write(digest, result) is True
    assert ai_result_cache.read(digest) == result
    raw = (tmp_path / "razync_ai_cache.sqlite3").read_bytes()
    assert b"Sigilo empresarial" not in raw
    # Dígitos curtos podem ocorrer por acaso no HMAC ou no ciphertext.
    # Verifica o campo completo e comprova que o payload é um token Fernet.
    assert b'"conta": "501"' not in raw
    with sqlite3.connect(tmp_path / "razync_ai_cache.sqlite3") as connection:
        ciphertext = connection.execute("SELECT ciphertext FROM encrypted_ai_cache WHERE id=?", (digest,)).fetchone()[0]
    assert json.loads(Fernet(os.environ["RAZYNC_AI_CACHE_KEY"].encode("ascii")).decrypt(ciphertext)) == result
    assert ai_result_cache.stable_digest(json.dumps({"empresa": "XYZ", "conta": "501"})) == digest


def test_cache_sem_chave_nao_persiste_dados(monkeypatch, tmp_path):
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    monkeypatch.delenv("RAZYNC_AI_CACHE_KEY", raising=False)
    assert ai_result_cache.stable_digest("teste") is None
    assert ai_result_cache.write("teste", {"analises": []}) is False
    assert not (tmp_path / "razync_ai_cache.sqlite3").exists()


def test_openrouter_orcamento_diario_sobrevive_novo_processo(monkeypatch, tmp_path):
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    for _ in range(ai_budget._OPENROUTER_DAILY_CAP):
        ai_budget._reserve_daily_free_openrouter("2026-10-13", observed=0)
    with pytest.raises(HTTPException) as error:
        ai_budget._reserve_daily_free_openrouter("2026-10-13", observed=0)
    assert error.value.status_code == 429
    # Um novo dia não herda cotas indevidamente.
    ai_budget._reserve_daily_free_openrouter("2026-10-14", observed=0)


def test_orcamento_fail_closed_quando_volume_indisponivel(monkeypatch, tmp_path):
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path / "not-mounted"))
    with pytest.raises(HTTPException) as error:
        ai_budget._reserve_daily_free_openrouter("2026-10-13", observed=0)
    assert error.value.status_code == 503

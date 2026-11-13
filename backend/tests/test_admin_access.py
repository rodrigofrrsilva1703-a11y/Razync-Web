import pytest
from fastapi import HTTPException
from app.migration_routes import require_admin


def test_dedicated_password_keeps_existing_api_token_working(monkeypatch):
    monkeypatch.setenv('CLASSIFICATION_ADMIN_PASSWORD', 'dedicated-test-only')
    monkeypatch.setenv('RAZYNC_ACCESS_TOKEN', 'old-test-only')
    require_admin('Bearer dedicated-test-only')
    require_admin('Bearer old-test-only')


@pytest.mark.parametrize('supplied', ['Bearer incorrect', 'Bearer senha-çã', '', 'Bearer '])
def test_wrong_passwords_fail_as_unauthorized(monkeypatch, supplied):
    monkeypatch.setenv('CLASSIFICATION_ADMIN_PASSWORD', 'test-only')
    with pytest.raises(HTTPException) as error:
        require_admin(supplied)
    assert error.value.status_code == 401


def test_legacy_config_fallback_remains_supported(monkeypatch):
    monkeypatch.delenv('CLASSIFICATION_ADMIN_PASSWORD', raising=False)
    monkeypatch.setenv('RAZYNC_ACCESS_TOKEN', 'fallback-test-only')
    require_admin('Bearer fallback-test-only')

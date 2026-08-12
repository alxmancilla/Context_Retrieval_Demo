from types import SimpleNamespace

import pytest

from core.security import credentials_match, resolve_access_context
from core.settings import configured_app_env, configured_auth_mode, get_settings


def _settings(**overrides):
    values = {
        "realm_id": "realm-a",
        "user_id": "local-user",
        "access_principals": ("role:platform-engineer",),
        "auth_mode": "disabled",
        "auth_username": None,
        "auth_password": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_local_access_context_is_scoped_and_adds_user_principal():
    context = resolve_access_context(_settings())
    assert context.realm_id == "realm-a"
    assert context.user_id == "local-user"
    assert context.principals == ("role:platform-engineer", "user:local-user")


def test_authenticated_access_context_uses_trusted_identity_metadata():
    context = resolve_access_context(
        _settings(), identifier="alice",
        metadata={"realm_id": "realm-b", "principals": ["role:security"]},
    )
    assert context.realm_id == "realm-b"
    assert context.user_id == "alice"
    assert context.principals == ("role:security", "user:alice")


def test_access_context_rejects_non_string_or_operator_principals():
    with pytest.raises(ValueError, match="principal"):
        resolve_access_context(_settings(), metadata={"principals": [{"$ne": None}]})


def test_password_credentials_are_compared_only_in_password_mode():
    password_settings = _settings(
        auth_mode="password", auth_username="alice", auth_password="correct-horse"
    )
    assert credentials_match(password_settings, "alice", "correct-horse")
    assert not credentials_match(password_settings, "alice", "wrong")
    assert not credentials_match(_settings(), "alice", "correct-horse")


def test_runtime_profile_rejects_disabled_auth_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="AUTH_MODE must be enabled"):
        get_settings()
    get_settings.cache_clear()


def test_runtime_profile_values_are_strict(monkeypatch):
    monkeypatch.setenv("APP_ENV", "preview")
    with pytest.raises(ValueError, match="APP_ENV"):
        configured_app_env()
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("AUTH_MODE", "none")
    with pytest.raises(ValueError, match="AUTH_MODE"):
        configured_auth_mode()
from types import SimpleNamespace

import pytest

from core.security import (
    credentials_match,
    resolve_access_context,
    resolve_oauth_access_context,
    validate_agent_scope,
)
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


def test_agent_scope_fails_closed_without_principals():
    with pytest.raises(ValueError, match="required"):
        validate_agent_scope("realm", "user", None)


def test_production_identity_requires_trusted_claims():
    with pytest.raises(ValueError, match="Production identity"):
        resolve_access_context(_settings(app_env="production"), identifier="alice", metadata={})


def test_oauth_context_requires_allowed_provider_and_maps_groups():
    settings = _settings(
        oauth_allowed_providers=("azure-ad",), oauth_realm_claim="tenant",
        oauth_principals_claim="groups", oauth_group_prefix="group:",
    )
    access = resolve_oauth_access_context(
        settings, "azure-ad", "alice", {"tenant": "realm-a", "groups": ["security"]}
    )
    assert access.principals == ("group:security", "user:alice")
    with pytest.raises(ValueError, match="not allowed"):
        resolve_oauth_access_context(
            settings, "github", "alice", {"tenant": "realm-a", "groups": []}
        )


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
    with pytest.raises(ValueError, match="AUTH_MODE must be 'oauth'"):
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


def test_password_mode_rejects_weak_chainlit_signing_secret(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "password")
    monkeypatch.setenv("CHAINLIT_AUTH_SECRET", "change-me")
    monkeypatch.setenv("AUTH_USERNAME", "alice")
    monkeypatch.setenv("AUTH_PASSWORD", "correct-horse")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="CHAINLIT_AUTH_SECRET"):
        get_settings()
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SOURCE_TOP_K", "0"),
        ("SOURCE_RETRIEVAL_MODE", "score"),
        ("SOURCE_ROUTING_MODE", "planner"),
        ("MEMORY_TOP_K", "21"),
        ("MEMORY_MIN_IMPORTANCE", "1.1"),
        ("MEMORY_SIMILARITY_THRESHOLD", "0.49"),
        ("RECENT_CONTEXT_MESSAGES", "1"),
        ("RECENT_CONTEXT_MAX_CHARS", "499"),
        ("CONVERSATION_SUMMARY_MAX_CHARS", "10001"),
        ("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "0"),
        ("MONGODB_CONNECT_TIMEOUT_MS", "120001"),
        ("MONGODB_SOCKET_TIMEOUT_MS", "999"),
        ("MONGODB_MAX_POOL_SIZE", "0"),
        ("MONGODB_WAIT_QUEUE_TIMEOUT_MS", "99"),
        ("OPENAI_TIMEOUT_SECONDS", "0"),
        ("OPENAI_MAX_RETRIES", "6"),
    ],
)
def test_runtime_rejects_unbounded_retrieval_and_timeout_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    with pytest.raises(ValueError, match=name):
        get_settings()
    get_settings.cache_clear()


def test_production_rejects_non_https_grove_endpoint(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oauth")
    monkeypatch.setenv("CHAINLIT_AUTH_SECRET", "a-secure-random-signing-secret-value")
    monkeypatch.setenv("OAUTH_ALLOWED_PROVIDERS", "azure-ad")
    monkeypatch.setenv("GROVE_BASE_URL", "http://grove.example/v1")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="GROVE_BASE_URL must use HTTPS"):
        get_settings()
    get_settings.cache_clear()


def test_runtime_rejects_unknown_chat_provider(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="CHAT_PROVIDER"):
        get_settings()
    get_settings.cache_clear()


def test_openai_chat_provider_does_not_require_grove_key(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "redacted")
    monkeypatch.setenv("GROVE_API_KEY", "")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.chat_provider == "openai"
    assert settings.openai_api_key == "redacted"
    get_settings.cache_clear()


def test_production_rejects_non_https_openai_endpoint(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oauth")
    monkeypatch.setenv("CHAINLIT_AUTH_SECRET", "a-secure-random-signing-secret-value")
    monkeypatch.setenv("OAUTH_ALLOWED_PROVIDERS", "azure-ad")
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "redacted")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://api.openai.example/v1")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="OPENAI_BASE_URL must use HTTPS"):
        get_settings()
    get_settings.cache_clear()


def test_pool_minimum_cannot_exceed_maximum(monkeypatch):
    monkeypatch.setenv("MONGODB_MIN_POOL_SIZE", "20")
    monkeypatch.setenv("MONGODB_MAX_POOL_SIZE", "10")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="MIN_POOL_SIZE"):
        get_settings()
    get_settings.cache_clear()


def test_validation_action_is_strictly_validated(monkeypatch):
    monkeypatch.setenv("MONGODB_VALIDATION_ACTION", "ignore")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="VALIDATION_ACTION"):
        get_settings()
    get_settings.cache_clear()
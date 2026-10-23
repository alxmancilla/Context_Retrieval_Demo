import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv

from core.reconciliation import ReconciliationWeights
from core.source_agents import RetrievalMode


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def configured_auth_mode() -> str:
    load_dotenv()
    mode = os.getenv("AUTH_MODE", "disabled").strip().lower()
    if mode not in {"disabled", "password", "oauth"}:
        raise ValueError("AUTH_MODE must be 'disabled', 'password', or 'oauth'")
    return mode


def configured_app_env() -> str:
    load_dotenv()
    app_env = os.getenv("APP_ENV", "local").strip().lower()
    if app_env not in {"local", "production"}:
        raise ValueError("APP_ENV must be 'local' or 'production'")
    return app_env


def _csv(name: str, default: str) -> tuple[str, ...]:
    values = tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())
    if not values:
        raise ValueError(f"{name} must contain at least one value")
    return values


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _strong_secret(name: str, minimum_length: int = 32) -> str:
    value = _required(name)
    placeholders = ("<", "change-me", "changeme", "replace-me", "example")
    if len(value) < minimum_length or any(marker in value.lower() for marker in placeholders):
        raise ValueError(f"{name} must be a non-placeholder secret of at least {minimum_length} characters")
    return value


def _provider_url(name: str, default: str, app_env: str) -> str:
    value = os.getenv(name, default).rstrip("/")
    parsed = urlparse(value)
    if not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")
    if app_env == "production" and parsed.scheme != "https":
        raise ValueError(f"{name} must use HTTPS when APP_ENV=production")
    return value


def _log_level() -> str:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL is invalid")
    return level


def _nonempty(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _retrieval_mode() -> RetrievalMode:
    mode = os.getenv("SOURCE_RETRIEVAL_MODE", "hybrid").strip().lower()
    if mode not in {"hybrid", "vector", "lexical"}:
        raise ValueError("SOURCE_RETRIEVAL_MODE must be 'hybrid', 'vector', or 'lexical'")
    return mode  # type: ignore[return-value]


def configured_reconciliation_weights() -> ReconciliationWeights:
    return ReconciliationWeights(
        vector=_bounded_float("RECONCILIATION_VECTOR_WEIGHT", 0.55, 0.0, 1.0),
        authority=_bounded_float("RECONCILIATION_AUTHORITY_WEIGHT", 0.30, 0.0, 1.0),
        freshness=_bounded_float("RECONCILIATION_FRESHNESS_WEIGHT", 0.15, 0.0, 1.0),
    )


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongodb_db: str
    mongodb_server_selection_timeout_ms: int
    mongodb_connect_timeout_ms: int
    mongodb_socket_timeout_ms: int
    mongodb_max_pool_size: int
    mongodb_min_pool_size: int
    mongodb_wait_queue_timeout_ms: int
    mongodb_validation_action: str
    grove_api_key: str
    grove_base_url: str
    grove_model: str
    realm_id: str
    user_id: str
    agent_id: str
    source_top_k: int
    source_retrieval_mode: RetrievalMode
    memory_top_k: int
    access_principals: tuple[str, ...]
    auth_mode: str
    auth_username: str | None
    auth_password: str | None
    oauth_allowed_providers: tuple[str, ...]
    oauth_realm_claim: str
    oauth_principals_claim: str
    oauth_group_prefix: str
    app_env: str
    grove_timeout_seconds: float
    grove_max_retries: int
    voyage_api_key: str | None
    voyage_rerank_model: str
    voyage_rerank_timeout_seconds: float
    voyage_rerank_max_retries: int
    log_level: str
    memory_retention_days: int
    memory_max_per_user: int
    memory_min_importance: float
    memory_similarity_threshold: float
    memory_embedding_profile: str
    prompt_version: str
    agent_version: str
    recent_context_messages: int
    recent_context_max_chars: int
    conversation_summary_max_chars: int
    checkpoint_retention_days: int
    reconciliation_weights: ReconciliationWeights


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    auth_mode = configured_auth_mode()
    app_env = configured_app_env()
    if app_env == "production" and auth_mode != "oauth":
        raise ValueError("AUTH_MODE must be 'oauth' when APP_ENV=production")
    if auth_mode in {"password", "oauth"}:
        _strong_secret("CHAINLIT_AUTH_SECRET")
    if auth_mode == "password":
        auth_username, auth_password = _required("AUTH_USERNAME"), _required("AUTH_PASSWORD")
    else:
        auth_username, auth_password = None, None
    if auth_mode == "oauth":
        oauth_allowed_providers = _csv("OAUTH_ALLOWED_PROVIDERS", "")
    else:
        oauth_allowed_providers = ()
    max_pool_size = _bounded_int("MONGODB_MAX_POOL_SIZE", 50, 1, 500)
    min_pool_size = _bounded_int("MONGODB_MIN_POOL_SIZE", 0, 0, 100)
    if min_pool_size > max_pool_size:
        raise ValueError("MONGODB_MIN_POOL_SIZE cannot exceed MONGODB_MAX_POOL_SIZE")
    validation_action = os.getenv(
        "MONGODB_VALIDATION_ACTION", "error" if app_env == "production" else "warn"
    ).strip().lower()
    if validation_action not in {"warn", "error"}:
        raise ValueError("MONGODB_VALIDATION_ACTION must be 'warn' or 'error'")
    return Settings(
        mongodb_uri=_required("MONGODB_URI"),
        mongodb_db=os.getenv("MONGODB_DB", "cmm_context_demo"),
        mongodb_server_selection_timeout_ms=_bounded_int(
            "MONGODB_SERVER_SELECTION_TIMEOUT_MS", 5000, 100, 120_000
        ),
        mongodb_connect_timeout_ms=_bounded_int(
            "MONGODB_CONNECT_TIMEOUT_MS", 10_000, 100, 120_000
        ),
        mongodb_socket_timeout_ms=_bounded_int(
            "MONGODB_SOCKET_TIMEOUT_MS", 60_000, 1000, 300_000
        ),
        mongodb_max_pool_size=max_pool_size,
        mongodb_min_pool_size=min_pool_size,
        mongodb_wait_queue_timeout_ms=_bounded_int(
            "MONGODB_WAIT_QUEUE_TIMEOUT_MS", 5000, 100, 120_000
        ),
        mongodb_validation_action=validation_action,
        grove_api_key=_required("GROVE_API_KEY"),
        grove_base_url=_provider_url(
            "GROVE_BASE_URL",
            "https://grove-gateway-prod.azure-api.net/"
            "grove-foundry-prod/openai/v1",
            app_env,
        ),
        grove_model=os.getenv("GROVE_MODEL", "gpt-5.6-sol"),
        realm_id=os.getenv("REALM_ID", "cmm-demo"),
        user_id=os.getenv("USER_ID", "demo-user"),
        agent_id=os.getenv("AGENT_ID", "cmm-context-assistant"),
        source_top_k=_bounded_int("SOURCE_TOP_K", 5, 1, 50),
        source_retrieval_mode=_retrieval_mode(),
        memory_top_k=_bounded_int("MEMORY_TOP_K", 3, 1, 20),
        access_principals=_csv("ACCESS_PRINCIPALS", "role:platform-engineer"),
        auth_mode=auth_mode,
        auth_username=auth_username,
        auth_password=auth_password,
        oauth_allowed_providers=oauth_allowed_providers,
        oauth_realm_claim=os.getenv("OAUTH_REALM_CLAIM", "realm_id"),
        oauth_principals_claim=os.getenv("OAUTH_PRINCIPALS_CLAIM", "groups"),
        oauth_group_prefix=os.getenv("OAUTH_GROUP_PREFIX", "group:"),
        app_env=app_env,
        grove_timeout_seconds=_bounded_float("GROVE_TIMEOUT_SECONDS", 60.0, 1.0, 300.0),
        grove_max_retries=_bounded_int("GROVE_MAX_RETRIES", 2, 0, 5),
        voyage_api_key=os.getenv("VOYAGE_API_KEY") or None,
        voyage_rerank_model=os.getenv("VOYAGE_RERANK_MODEL", "rerank-3"),
        voyage_rerank_timeout_seconds=_bounded_float(
            "VOYAGE_RERANK_TIMEOUT_SECONDS", 15.0, 1.0, 60.0
        ),
        voyage_rerank_max_retries=_bounded_int("VOYAGE_RERANK_MAX_RETRIES", 2, 0, 5),
        log_level=_log_level(),
        memory_retention_days=_bounded_int("MEMORY_RETENTION_DAYS", 30, 1, 365),
        memory_max_per_user=_bounded_int("MEMORY_MAX_PER_USER", 100, 1, 1000),
        memory_min_importance=_bounded_float(
            "MEMORY_MIN_IMPORTANCE", 0.65, 0.0, 1.0
        ),
        memory_similarity_threshold=_bounded_float(
            "MEMORY_SIMILARITY_THRESHOLD", 0.92, 0.5, 1.0
        ),
        memory_embedding_profile=_nonempty(
            "MEMORY_EMBEDDING_PROFILE", "voyage-4:auto-embed:v1"
        ),
        prompt_version=_nonempty("PROMPT_VERSION", "answer-v2"),
        agent_version=_nonempty("AGENT_VERSION", "memory-v2"),
        recent_context_messages=_bounded_int("RECENT_CONTEXT_MESSAGES", 6, 2, 20),
        recent_context_max_chars=_bounded_int(
            "RECENT_CONTEXT_MAX_CHARS", 4000, 500, 20_000
        ),
        conversation_summary_max_chars=_bounded_int(
            "CONVERSATION_SUMMARY_MAX_CHARS", 1500, 500, 10_000
        ),
        checkpoint_retention_days=_bounded_int(
            "CHECKPOINT_RETENTION_DAYS", 7, 1, 90
        ),
        reconciliation_weights=configured_reconciliation_weights(),
    )

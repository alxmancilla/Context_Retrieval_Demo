import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

from core.reconciliation import ReconciliationWeights


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def configured_auth_mode() -> str:
    load_dotenv()
    mode = os.getenv("AUTH_MODE", "disabled").strip().lower()
    if mode not in {"disabled", "password"}:
        raise ValueError("AUTH_MODE must be 'disabled' or 'password'")
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


def _log_level() -> str:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL is invalid")
    return level


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
    grove_api_key: str
    grove_base_url: str
    grove_model: str
    realm_id: str
    user_id: str
    agent_id: str
    source_top_k: int
    memory_top_k: int
    access_principals: tuple[str, ...]
    auth_mode: str
    auth_username: str | None
    auth_password: str | None
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
    checkpoint_retention_days: int
    reconciliation_weights: ReconciliationWeights


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    auth_mode = configured_auth_mode()
    app_env = configured_app_env()
    if app_env == "production" and auth_mode == "disabled":
        raise ValueError("AUTH_MODE must be enabled when APP_ENV=production")
    if auth_mode == "password":
        _required("CHAINLIT_AUTH_SECRET")
        auth_username, auth_password = _required("AUTH_USERNAME"), _required("AUTH_PASSWORD")
    else:
        auth_username, auth_password = None, None
    return Settings(
        mongodb_uri=_required("MONGODB_URI"),
        mongodb_db=os.getenv("MONGODB_DB", "cmm_context_demo"),
        mongodb_server_selection_timeout_ms=int(
            os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000")
        ),
        mongodb_connect_timeout_ms=int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "10000")),
        mongodb_socket_timeout_ms=int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "60000")),
        grove_api_key=_required("GROVE_API_KEY"),
        grove_base_url=os.getenv(
            "GROVE_BASE_URL",
            "https://grove-gateway-prod.azure-api.net/"
            "grove-foundry-prod/openai/v1",
        ),
        grove_model=os.getenv("GROVE_MODEL", "gpt-5.6-sol"),
        realm_id=os.getenv("REALM_ID", "cmm-demo"),
        user_id=os.getenv("USER_ID", "demo-user"),
        agent_id=os.getenv("AGENT_ID", "cmm-context-assistant"),
        source_top_k=int(os.getenv("SOURCE_TOP_K", "5")),
        memory_top_k=int(os.getenv("MEMORY_TOP_K", "3")),
        access_principals=_csv("ACCESS_PRINCIPALS", "role:platform-engineer"),
        auth_mode=auth_mode,
        auth_username=auth_username,
        auth_password=auth_password,
        app_env=app_env,
        grove_timeout_seconds=_bounded_float("GROVE_TIMEOUT_SECONDS", 60.0, 1.0, 300.0),
        grove_max_retries=_bounded_int("GROVE_MAX_RETRIES", 2, 0, 5),
        voyage_api_key=os.getenv("VOYAGE_API_KEY") or None,
        voyage_rerank_model=os.getenv("VOYAGE_RERANK_MODEL", "rerank-2.5"),
        voyage_rerank_timeout_seconds=_bounded_float(
            "VOYAGE_RERANK_TIMEOUT_SECONDS", 15.0, 1.0, 60.0
        ),
        voyage_rerank_max_retries=_bounded_int("VOYAGE_RERANK_MAX_RETRIES", 2, 0, 5),
        log_level=_log_level(),
        memory_retention_days=_bounded_int("MEMORY_RETENTION_DAYS", 30, 1, 365),
        memory_max_per_user=_bounded_int("MEMORY_MAX_PER_USER", 100, 1, 1000),
        checkpoint_retention_days=_bounded_int(
            "CHECKPOINT_RETENTION_DAYS", 7, 1, 90
        ),
        reconciliation_weights=configured_reconciliation_weights(),
    )

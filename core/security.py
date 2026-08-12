import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from core.settings import Settings

IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


@dataclass(frozen=True)
class AccessContext:
    realm_id: str
    user_id: str
    principals: tuple[str, ...]


def _validated(value: str, label: str) -> str:
    if not isinstance(value, str) or not IDENTITY_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def normalize_principals(values: Iterable[str]) -> tuple[str, ...]:
    principals = tuple(dict.fromkeys(_validated(value, "principal") for value in values))
    if not principals or len(principals) > 32:
        raise ValueError("Access principals must contain between 1 and 32 values")
    return principals


def resolve_access_context(
    settings: Settings, *, identifier: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AccessContext:
    claims = metadata or {}
    realm_id = _validated(str(claims.get("realm_id", settings.realm_id)), "realm_id")
    user_id = _validated(str(claims.get("user_id", identifier or settings.user_id)), "user_id")
    raw_principals = claims.get("principals", settings.access_principals)
    if not isinstance(raw_principals, (list, tuple)):
        raise ValueError("User principals must be a list of strings")
    principals = normalize_principals((*raw_principals, f"user:{user_id}"))
    return AccessContext(realm_id=realm_id, user_id=user_id, principals=principals)


def credentials_match(settings: Settings, username: str, password: str) -> bool:
    if settings.auth_mode != "password" or not settings.auth_username or not settings.auth_password:
        return False
    return secrets.compare_digest(username, settings.auth_username) and secrets.compare_digest(
        password, settings.auth_password
    )
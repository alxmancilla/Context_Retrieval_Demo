from pymongo.database import Database

from core.memory_policy import MEMORY_SCHEMA_VERSION, MEMORY_TYPES
from core.schemas import (
    ALL_SOURCES,
    CLAIM_ASSERTIONS_COLLECTION,
    GOVERNANCE_COLLECTION,
    THREAD_OWNERSHIP_COLLECTION,
)


def _string() -> dict:
    return {"bsonType": "string", "minLength": 1}


def source_validator() -> dict:
    return {"$jsonSchema": {
        "bsonType": "object",
        "required": [
            "artifact_id", "realm_id", "source", "title", "content", "url",
            "updated_at", "access_principals", "claims", "metadata", "governance",
        ],
        "properties": {
            "artifact_id": _string(), "realm_id": _string(), "title": _string(),
            "content": _string(), "url": _string(), "updated_at": {"bsonType": "date"},
            "source": {"enum": list(ALL_SOURCES)},
            "access_principals": {
                "bsonType": "array", "minItems": 1, "maxItems": 64,
                "uniqueItems": True, "items": _string(),
            },
            "claims": {"bsonType": "object"},
            "metadata": {"bsonType": "object"},
            "governance": {"bsonType": "object"},
        },
    }}


def governance_validator() -> dict:
    return {"$jsonSchema": {
        "bsonType": "object",
        "required": [
            "realm_id", "artifact_id", "source", "document_type", "lifecycle_status",
            "policy_version", "updated_at", "synthetic",
        ],
        "properties": {
            "realm_id": _string(), "artifact_id": _string(),
            "source": {"enum": list(ALL_SOURCES)},
            "document_type": _string(), "lifecycle_status": _string(),
            "policy_version": _string(), "updated_at": {"bsonType": "date"},
            "synthetic": {"bsonType": "bool"},
            "authority_override": {
                "bsonType": ["double", "int", "long", "decimal", "null"],
                "minimum": 0, "maximum": 1,
            },
        },
    }}


def claim_assertion_validator() -> dict:
    return {"$jsonSchema": {
        "bsonType": "object",
        "required": [
            "assertion_id", "realm_id", "source", "artifact_id", "claim_key", "claim_value",
            "updated_at", "access_principals", "synthetic",
        ],
        "properties": {
            "assertion_id": _string(), "realm_id": _string(), "artifact_id": _string(),
            "source": {"enum": list(ALL_SOURCES)},
            "claim_key": _string(), "claim_value": _string(),
            "updated_at": {"bsonType": "date"}, "synthetic": {"bsonType": "bool"},
            "access_principals": {
                "bsonType": "array", "minItems": 1, "maxItems": 64,
                "uniqueItems": True, "items": _string(),
            },
        },
    }}


def memory_validator() -> dict:
    return {"$jsonSchema": {
        "bsonType": "object",
        "required": [
            "memory_id", "realm_id", "user_id", "content", "content_hash",
            "summary", "memory_type", "importance", "created_at", "updated_at",
            "valid_from", "valid_until", "expires_at", "tombstoned",
            "reinforcement_count", "revision", "provenance", "embedding_profile",
            "prompt_version", "agent_version", "schema_version",
        ],
        "properties": {
            "memory_id": _string(), "realm_id": _string(), "user_id": _string(),
            "content": _string(), "summary": _string(), "content_hash": _string(),
            "memory_type": {"enum": list(MEMORY_TYPES)},
            "importance": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"}, "expires_at": {"bsonType": "date"},
            "valid_from": {"bsonType": "date"}, "valid_until": {"bsonType": "date"},
            "tombstoned": {"bsonType": "bool"},
            "reinforcement_count": {"bsonType": ["int", "long"], "minimum": 1},
            "revision": {"bsonType": ["int", "long"], "minimum": 1},
            "embedding_profile": _string(), "prompt_version": _string(),
            "agent_version": _string(),
            "schema_version": {"enum": [MEMORY_SCHEMA_VERSION]},
            "provenance": {
                "bsonType": "object",
                "required": ["correlation_id", "source_turn_id", "node", "reason"],
                "properties": {
                    "correlation_id": _string(), "source_turn_id": _string(),
                    "node": _string(), "reason": _string(),
                },
            },
        },
    }}


def registry_validator() -> dict:
    return {"$jsonSchema": {
        "bsonType": "object",
        "required": ["realm_id", "source", "authority", "freshness_half_life_days"],
        "properties": {
            "realm_id": _string(), "source": {"enum": list(ALL_SOURCES)},
            "authority": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
            "freshness_half_life_days": {"bsonType": ["int", "long"], "minimum": 1},
        },
    }}


def thread_validator() -> dict:
    return {"$jsonSchema": {
        "bsonType": "object",
        "required": ["thread_id", "realm_id", "user_id", "created_at", "expires_at"],
        "properties": {
            "thread_id": _string(), "realm_id": _string(), "user_id": _string(),
            "created_at": {"bsonType": "date"}, "expires_at": {"bsonType": "date"},
        },
    }}


def ensure_validator(
    db: Database, collection_name: str, validator: dict, validation_action: str,
) -> None:
    if validation_action not in {"warn", "error"}:
        raise ValueError("validation_action must be 'warn' or 'error'")
    level = "moderate" if validation_action == "warn" else "strict"
    command = {
        "collMod": collection_name, "validator": validator,
        "validationLevel": level, "validationAction": validation_action,
    }
    db.command(command)


VALIDATORS = {
    GOVERNANCE_COLLECTION: governance_validator,
    CLAIM_ASSERTIONS_COLLECTION: claim_assertion_validator,
    THREAD_OWNERSHIP_COLLECTION: thread_validator,
    "memories": memory_validator,
    "sources": registry_validator,
}
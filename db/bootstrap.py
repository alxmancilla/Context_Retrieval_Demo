import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import ReplaceOne, SearchIndexModel

from core.memory import MEMORY_VECTOR_INDEX
from core.memory_policy import MEMORY_SCHEMA_VERSION
from core.pool_metrics import PoolMetrics
from core.schemas import (
    ALL_SOURCES,
    CLAIM_ASSERTIONS_COLLECTION,
    GOVERNANCE_COLLECTION,
    THREAD_OWNERSHIP_COLLECTION,
)
from core.source_agents import SOURCE_LEXICAL_INDEX, SOURCE_VECTOR_INDEX
from data.seed_data import all_artifacts
from db.schema import VALIDATORS, ensure_validator, source_validator

SOURCE_CONFIGS = {
    "github": (1.00, 365), "sharepoint": (0.85, 365), "jira": (0.78, 270),
    "confluence": (0.65, 180), "teams": (0.35, 60),
}
MEMORY_ID_INDEX = "memory_id_unique"
LEGACY_SOURCE_VECTOR_INDEX = "content_vector"
LEGACY_SOURCE_LEXICAL_INDEX = "content_lexical_acl"


class SearchIndexTypeMismatch(RuntimeError):
    pass


def _auto_embed_definition(filters: list[str]) -> dict:
    fields = [{"type": "autoEmbed", "path": "content", "modality": "text",
               "model": "voyage-4"}]
    fields.extend({"type": "filter", "path": path} for path in filters)
    return {"fields": fields}


def _lexical_definition() -> dict:
    return {
        "mappings": {
            "dynamic": False,
            "fields": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "artifact_id": {"type": "string"},
                "realm_id": {"type": "token"},
                "access_principals": {"type": "token"},
            },
        }
    }


def _normalized_search_definition(definition: dict) -> tuple[tuple[tuple[str, object], ...], ...]:
    relevant = ("type", "path", "modality", "model")
    fields = [
        tuple(sorted((key, field[key]) for key in relevant if key in field))
        for field in definition.get("fields", [])
    ]
    return tuple(sorted(fields, key=str))


def _ensure_auto_embed_index(collection, name: str, filters: list[str]) -> str:
    desired = _auto_embed_definition(filters)
    indexes = list(collection.list_search_indexes(name))
    if indexes:
        current = indexes[0]
        index_type = current.get("type")
        if index_type and index_type != "vectorSearch":
            raise SearchIndexTypeMismatch(
                f"Search index {name} has type {index_type}; expected vectorSearch"
            )
        definition = current.get("latestDefinition") or current.get("definition") or {}
        if _normalized_search_definition(definition) == _normalized_search_definition(desired):
            return "unchanged"
        collection.update_search_index(name, desired)
        return "updated"
    model = SearchIndexModel(
        definition=desired, name=name, type="vectorSearch"
    )
    collection.create_search_index(model=model)
    return "created"


def _ensure_lexical_index(collection, name: str = SOURCE_LEXICAL_INDEX) -> str:
    desired = _lexical_definition()
    indexes = list(collection.list_search_indexes(name))
    if indexes:
        current = indexes[0]
        index_type = current.get("type")
        if index_type and index_type != "search":
            raise SearchIndexTypeMismatch(
                f"Search index {name} has type {index_type}; expected search"
            )
        definition = current.get("latestDefinition") or current.get("definition") or {}
        if definition.get("mappings") == desired["mappings"]:
            return "unchanged"
        collection.update_search_index(name, desired)
        return "updated"
    collection.create_search_index(SearchIndexModel(definition=desired, name=name, type="search"))
    return "created"


def _remove_legacy_source_indexes(collection) -> int:
    removed = 0
    for name in (LEGACY_SOURCE_VECTOR_INDEX, LEGACY_SOURCE_LEXICAL_INDEX):
        if list(collection.list_search_indexes(name)):
            collection.drop_search_index(name)
            removed += 1
    return removed


def _ensure_memory_indexes(collection: Collection) -> None:
    collection.create_index(
        [("realm_id", ASCENDING), ("user_id", ASCENDING),
         ("content_hash", ASCENDING), ("tombstoned", ASCENDING)]
    )
    collection.create_index(
        "memory_id", unique=True, name=MEMORY_ID_INDEX,
        partialFilterExpression={"memory_id": {"$type": "string"}},
    )
    collection.create_index("expires_at", expireAfterSeconds=0, name="memory_expiry_ttl")
    collection.create_index(
        [("realm_id", ASCENDING), ("user_id", ASCENDING),
         ("tombstoned", ASCENDING), ("updated_at", ASCENDING)],
        name="memory_active_pruning",
    )


def _migrate_memories(
    collection, now: datetime, retention_days: int, embedding_profile: str,
    prompt_version: str, agent_version: str,
) -> int:
    expires_at = now + timedelta(days=retention_days)
    result = collection.update_many(
        {"schema_version": {"$ne": MEMORY_SCHEMA_VERSION}},
        [{"$set": {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "memory_type": {"$ifNull": ["$memory_type", "legacy_context"]},
            "summary": {"$ifNull": [
                "$summary", {"$substrCP": [{"$ifNull": ["$content", ""]}, 0, 500]},
            ]},
            "importance": {"$ifNull": ["$importance", 0.4]},
            "created_at": {"$ifNull": ["$created_at", now]},
            "updated_at": {"$ifNull": ["$updated_at", now]},
            "expires_at": {"$ifNull": ["$expires_at", expires_at]},
            "valid_from": {"$ifNull": ["$valid_from", {"$ifNull": ["$created_at", now]}]},
            "valid_until": {"$ifNull": [
                "$valid_until", {"$ifNull": ["$expires_at", expires_at]},
            ]},
            "tombstoned": {"$ifNull": ["$tombstoned", False]},
            "reinforcement_count": {"$ifNull": ["$reinforcement_count", 1]},
            "revision": {"$ifNull": ["$revision", 1]},
            "embedding_profile": {"$ifNull": ["$embedding_profile", embedding_profile]},
            "prompt_version": {"$ifNull": ["$prompt_version", prompt_version]},
            "agent_version": {"$ifNull": ["$agent_version", agent_version]},
            "provenance": {"$ifNull": ["$provenance", {
                "correlation_id": {"$ifNull": ["$correlation_id", "legacy-migration"]},
                "source_turn_id": {"$ifNull": ["$correlation_id", "legacy-migration"]},
                "node": {"$ifNull": ["$node", "memory_migration"]},
                "reason": "legacy_memory_migration",
            }]},
        }}],
    )
    return result.modified_count


def _registry_document(source: str, realm_id: str) -> dict:
    authority, half_life = SOURCE_CONFIGS[source]
    return {
        "realm_id": realm_id, "source": source, "authority": authority,
        "freshness_half_life_days": half_life,
        "collection": source,
        "transport": "in-process-mcp-style",
        "tool": {
            "name": f"search_{source}",
            "description": f"Search the simulated {source} enterprise island",
            "inputSchema": {"type": "object", "properties": {
                "query": {"type": "string"}}, "required": ["query"]},
        },
    }


def _governance_documents(artifacts: list[dict], now: datetime) -> list[dict]:
    rows = []
    for artifact in artifacts:
        governance = artifact.get("governance", {})
        rows.append({
            "realm_id": artifact["realm_id"],
            "artifact_id": artifact["artifact_id"],
            "source": artifact["source"],
            "document_type": governance.get("document_type", "reference"),
            "lifecycle_status": governance.get("lifecycle_status", "active"),
            "authority_override": governance.get("authority_override"),
            "policy_version": "synthetic-v1",
            "updated_at": now,
            "synthetic": True,
        })
    return rows


def _claim_assertion_documents(artifacts: list[dict]) -> list[dict]:
    return [
        {
            "assertion_id": (
                f"{artifact['realm_id']}:{artifact['source']}:"
                f"{artifact['artifact_id']}:{claim}"
            ),
            "realm_id": artifact["realm_id"],
            "source": artifact["source"],
            "artifact_id": artifact["artifact_id"],
            "claim_key": claim,
            "claim_value": str(value),
            "updated_at": artifact["updated_at"],
            "access_principals": artifact["access_principals"],
            "synthetic": True,
        }
        for artifact in artifacts
        for claim, value in artifact.get("claims", {}).items()
    ]


def _ensure_governance_indexes(collection: Collection) -> None:
    collection.create_index(
        [("realm_id", ASCENDING), ("artifact_id", ASCENDING)],
        unique=True, name="governance_artifact_unique",
    )


def _ensure_claim_indexes(collection: Collection) -> None:
    collection.create_index(
        [("realm_id", ASCENDING), ("source", ASCENDING),
         ("artifact_id", ASCENDING), ("claim_key", ASCENDING)],
        unique=True, name="claim_artifact_key_unique",
    )
    collection.create_index(
        [("realm_id", ASCENDING), ("source", ASCENDING),
         ("claim_key", ASCENDING), ("access_principals", ASCENDING),
         ("claim_value", ASCENDING), ("updated_at", DESCENDING)],
        name="claim_contradiction_lookup",
    )


def _ensure_thread_indexes(collection: Collection) -> None:
    collection.create_index("thread_id", unique=True, name="thread_id_unique")
    collection.create_index(
        [("realm_id", ASCENDING), ("user_id", ASCENDING), ("thread_id", ASCENDING)],
        name="thread_owner_lookup",
    )
    collection.create_index("expires_at", expireAfterSeconds=0, name="thread_expiry_ttl")


def bootstrap(
    db: Database, realm_id: str, *, memory_retention_days: int = 30,
    checkpoint_retention_days: int = 7,
    validation_action: str = "warn",
    memory_embedding_profile: str = "voyage-4:auto-embed:v1",
    prompt_version: str = "answer-v2", agent_version: str = "memory-v2",
) -> dict:
    artifacts = all_artifacts(realm_id)
    counts = Counter(row["source"] for row in artifacts)
    index_actions: Counter[str] = Counter()
    removed = 0
    now = datetime.now(UTC)
    for source in ALL_SOURCES:
        collection = db[source]
        collection.create_index([("realm_id", ASCENDING), ("artifact_id", ASCENDING)], unique=True)
        source_rows = [row for row in artifacts if row["source"] == source]
        active_ids = [row["artifact_id"] for row in source_rows]
        removed += collection.delete_many({
            "realm_id": realm_id,
            "metadata.synthetic": True,
            "artifact_id": {"$nin": active_ids},
        }).deleted_count
        collection.bulk_write([
            ReplaceOne(
                {"realm_id": realm_id, "artifact_id": row["artifact_id"]}, row, upsert=True
            )
            for row in source_rows
        ], ordered=False)
        index_actions[_ensure_auto_embed_index(
            collection, SOURCE_VECTOR_INDEX, ["realm_id", "access_principals"]
        )] += 1
        index_actions[_ensure_lexical_index(collection)] += 1
        index_actions["legacy_removed"] += _remove_legacy_source_indexes(collection)
        db.sources.replace_one(
            {"realm_id": realm_id, "source": source},
            _registry_document(source, realm_id), upsert=True,
        )
    db.sources.create_index([("realm_id", ASCENDING), ("source", ASCENDING)], unique=True)

    governance_rows = _governance_documents(artifacts, now)
    governance = db[GOVERNANCE_COLLECTION]
    _ensure_governance_indexes(governance)
    governance.delete_many({
        "realm_id": realm_id, "synthetic": True,
        "artifact_id": {"$nin": [row["artifact_id"] for row in governance_rows]},
    })
    governance.bulk_write([
        ReplaceOne(
            {"realm_id": realm_id, "artifact_id": row["artifact_id"]}, row, upsert=True
        )
        for row in governance_rows
    ], ordered=False)

    claim_rows = _claim_assertion_documents(artifacts)
    claims = db[CLAIM_ASSERTIONS_COLLECTION]
    _ensure_claim_indexes(claims)
    claims.delete_many({
        "realm_id": realm_id, "synthetic": True,
        "assertion_id": {"$nin": [row["assertion_id"] for row in claim_rows]},
    })
    claims.bulk_write([
        ReplaceOne({"assertion_id": row["assertion_id"]}, row, upsert=True)
        for row in claim_rows
    ], ordered=False)

    db.memories.update_many(
        {"expires_at": {"$exists": False}},
        {"$set": {"expires_at": now + timedelta(days=memory_retention_days)}},
    )
    db.memories.update_many(
        {"tombstoned": {"$exists": False}}, {"$set": {"tombstoned": False}},
    )
    memory_documents_migrated = _migrate_memories(
        db.memories, now, memory_retention_days, memory_embedding_profile,
        prompt_version, agent_version,
    )
    _ensure_memory_indexes(db.memories)
    index_actions[_ensure_auto_embed_index(
        db.memories, MEMORY_VECTOR_INDEX,
        [
            "realm_id", "user_id", "tombstoned", "expires_at", "valid_from",
            "valid_until", "memory_type", "schema_version",
        ],
    )] += 1
    _ensure_thread_indexes(db[THREAD_OWNERSHIP_COLLECTION])
    checkpoint_backfilled = 0
    for name in ("checkpoints", "checkpoint_writes"):
        result = db[name].update_many(
            {"created_at": {"$exists": False}}, {"$set": {"created_at": now}}
        )
        checkpoint_backfilled += result.modified_count
    for source in ALL_SOURCES:
        ensure_validator(db, source, source_validator(), validation_action)
    for collection_name, validator_factory in VALIDATORS.items():
        ensure_validator(db, collection_name, validator_factory(), validation_action)
    return {
        "artifacts": sum(counts.values()), "per_source": dict(counts),
        "governance_policies": len(governance_rows),
        "claim_assertions": len(claim_rows),
        "obsolete_synthetic_artifacts_removed": removed,
        "checkpoint_documents_backfilled": checkpoint_backfilled,
        "memory_documents_migrated": memory_documents_migrated,
        "checkpoint_retention_days": checkpoint_retention_days,
        "validation_action": validation_action,
        "search_index_actions": dict(index_actions),
    }


def search_index_statuses(db: Database) -> dict[str, str]:
    targets: list[tuple[str, Collection, str]] = [
        (f"{source}:vector", db[source], SOURCE_VECTOR_INDEX) for source in ALL_SOURCES
    ]
    targets.extend(
        (f"{source}:lexical", db[source], SOURCE_LEXICAL_INDEX) for source in ALL_SOURCES
    )
    targets.append(("memories", db.memories, MEMORY_VECTOR_INDEX))
    statuses: dict[str, str] = {}
    for label, collection, name in targets:
        indexes = list(collection.list_search_indexes(name))
        if indexes:
            statuses[label] = str(indexes[0].get("status", "UNKNOWN"))
    return statuses


def wait_for_indexes(db: Database, timeout_seconds: int = 180) -> dict[str, str]:
    expected = len(ALL_SOURCES) * 2 + 1
    deadline = time.time() + timeout_seconds
    statuses: dict[str, str] = {}
    while time.time() < deadline:
        statuses = search_index_statuses(db)
        if len(statuses) == expected and all(value == "READY" for value in statuses.values()):
            return statuses
        time.sleep(5)
    raise TimeoutError(f"Search indexes did not become READY: {statuses}")


def connect(
    uri: str,
    database: str,
    *,
    server_selection_timeout_ms: int = 5000,
    connect_timeout_ms: int = 10000,
    socket_timeout_ms: int = 60000,
    max_pool_size: int = 50,
    min_pool_size: int = 0,
    wait_queue_timeout_ms: int = 5000,
    pool_metrics: PoolMetrics | None = None,
) -> tuple[MongoClient, Database]:
    """Create one reusable client for the low-concurrency demo process."""
    client_options: dict[str, Any] = {}
    if pool_metrics is not None:
        client_options["event_listeners"] = [pool_metrics]
    client: MongoClient = MongoClient(
        uri,
        appname="cmm-context-platform-demo",
        serverSelectionTimeoutMS=server_selection_timeout_ms,
        connectTimeoutMS=connect_timeout_ms,
        socketTimeoutMS=socket_timeout_ms,
        maxPoolSize=max_pool_size,
        minPoolSize=min_pool_size,
        waitQueueTimeoutMS=wait_queue_timeout_ms,
        **client_options,
    )
    client.admin.command("ping")
    return client, client[database]

import time
from collections import Counter
from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

from core.memory import MEMORY_VECTOR_INDEX
from core.schemas import ALL_SOURCES
from core.source_agents import SOURCE_VECTOR_INDEX
from data.seed_data import all_artifacts

SOURCE_CONFIGS = {
    "github": (1.00, 365), "sharepoint": (0.85, 365), "jira": (0.78, 270),
    "confluence": (0.65, 180), "teams": (0.35, 60),
}
MEMORY_ID_INDEX = "memory_id_unique"


class SearchIndexTypeMismatch(RuntimeError):
    pass


def _auto_embed_definition(filters: list[str]) -> dict:
    fields = [{"type": "autoEmbed", "path": "content", "modality": "text",
               "model": "voyage-4"}]
    fields.extend({"type": "filter", "path": path} for path in filters)
    return {"fields": fields}


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


def bootstrap(
    db: Database, realm_id: str, *, memory_retention_days: int = 30,
    checkpoint_retention_days: int = 7,
) -> dict:
    artifacts = all_artifacts(realm_id)
    counts = Counter(row["source"] for row in artifacts)
    index_actions: Counter[str] = Counter()
    removed = 0
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
        for row in source_rows:
            collection.replace_one(
                {"realm_id": realm_id, "artifact_id": row["artifact_id"]}, row, upsert=True
            )
        index_actions[_ensure_auto_embed_index(
            collection, SOURCE_VECTOR_INDEX, ["realm_id", "access_principals"]
        )] += 1
        db.sources.replace_one(
            {"realm_id": realm_id, "source": source},
            _registry_document(source, realm_id), upsert=True,
        )
    db.sources.create_index([("realm_id", ASCENDING), ("source", ASCENDING)], unique=True)
    now = datetime.now(UTC)
    db.memories.update_many(
        {"expires_at": {"$exists": False}},
        {"$set": {"expires_at": now + timedelta(days=memory_retention_days)}},
    )
    db.memories.update_many(
        {"tombstoned": {"$exists": False}}, {"$set": {"tombstoned": False}},
    )
    _ensure_memory_indexes(db.memories)
    index_actions[_ensure_auto_embed_index(
        db.memories, MEMORY_VECTOR_INDEX,
        ["realm_id", "user_id", "tombstoned", "expires_at"],
    )] += 1
    checkpoint_backfilled = 0
    for name in ("checkpoints", "checkpoint_writes"):
        result = db[name].update_many(
            {"created_at": {"$exists": False}}, {"$set": {"created_at": now}}
        )
        checkpoint_backfilled += result.modified_count
    return {
        "artifacts": sum(counts.values()), "per_source": dict(counts),
        "obsolete_synthetic_artifacts_removed": removed,
        "checkpoint_documents_backfilled": checkpoint_backfilled,
        "checkpoint_retention_days": checkpoint_retention_days,
        "search_index_actions": dict(index_actions),
    }


def wait_for_indexes(db: Database, timeout_seconds: int = 180) -> dict[str, str]:
    targets: list[tuple[str, Collection, str]] = [
        (source, db[source], SOURCE_VECTOR_INDEX) for source in ALL_SOURCES
    ]
    targets.append(("memories", db.memories, MEMORY_VECTOR_INDEX))
    deadline = time.time() + timeout_seconds
    statuses: dict[str, str] = {}
    while time.time() < deadline:
        for label, collection, name in targets:
            indexes = list(collection.list_search_indexes(name))
            if indexes:
                status = indexes[0]
                statuses[label] = str(status.get("status", "UNKNOWN"))
        if len(statuses) == len(targets) and all(value == "READY" for value in statuses.values()):
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
) -> tuple[MongoClient, Database]:
    """Create one reusable client for the low-concurrency demo process."""
    client: MongoClient = MongoClient(
        uri,
        appname="cmm-context-platform-demo",
        serverSelectionTimeoutMS=server_selection_timeout_ms,
        connectTimeoutMS=connect_timeout_ms,
        socketTimeoutMS=socket_timeout_ms,
    )
    client.admin.command("ping")
    return client, client[database]

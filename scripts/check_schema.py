"""Validate governed schema/index invariants without printing document content."""

from core.memory_policy import MEMORY_SCHEMA_VERSION
from core.schemas import (
    ALL_SOURCES,
    CLAIM_ASSERTIONS_COLLECTION,
    GOVERNANCE_COLLECTION,
    THREAD_OWNERSHIP_COLLECTION,
)
from core.settings import get_settings
from core.source_agents import SOURCE_LEXICAL_INDEX, SOURCE_VECTOR_INDEX
from data.seed_data import all_artifacts
from db.bootstrap import connect, search_index_statuses


def main() -> None:
    settings = get_settings()
    client, db = connect(
        settings.mongodb_uri, settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
        max_pool_size=settings.mongodb_max_pool_size,
        min_pool_size=settings.mongodb_min_pool_size,
        wait_queue_timeout_ms=settings.mongodb_wait_queue_timeout_ms,
    )
    try:
        expected_artifacts = all_artifacts(settings.realm_id)
        expected_claims = sum(len(row["claims"]) for row in expected_artifacts)
        counts = {
            "artifacts": sum(
                db[source].count_documents({"realm_id": settings.realm_id})
                for source in ALL_SOURCES
            ),
            "governance": db[GOVERNANCE_COLLECTION].count_documents({
                "realm_id": settings.realm_id
            }),
            "claims": db[CLAIM_ASSERTIONS_COLLECTION].count_documents({
                "realm_id": settings.realm_id
            }),
        }
        validated_collections = [
            *ALL_SOURCES, "sources", "memories", GOVERNANCE_COLLECTION,
            CLAIM_ASSERTIONS_COLLECTION, THREAD_OWNERSHIP_COLLECTION,
        ]
        validator_count = sum(
            bool(list(db.list_collections(filter={"name": name}))[0]
                 .get("options", {}).get("validator"))
            for name in validated_collections
        )
        statuses = search_index_statuses(db)
        source_search_indexes = {
            source: {index["name"] for index in db[source].list_search_indexes()}
            for source in ALL_SOURCES
        }
        claim_indexes = {index["name"] for index in db[CLAIM_ASSERTIONS_COLLECTION].list_indexes()}
        memory_indexes = {index["name"] for index in db.memories.list_indexes()}
        invalid_memory_v2 = db.memories.count_documents({"$or": [
            {"schema_version": {"$ne": MEMORY_SCHEMA_VERSION}},
            {"memory_type": {"$exists": False}},
            {"provenance": {"$exists": False}},
            {"valid_until": {"$exists": False}},
        ]})
        checks = {
            "counts": counts == {
                "artifacts": len(expected_artifacts),
                "governance": len(expected_artifacts),
                "claims": expected_claims,
            },
            "validators": validator_count == len(validated_collections),
            "search_indexes": len(statuses) == 11 and set(statuses.values()) == {"READY"},
            "source_search_index_names": all(
                names == {SOURCE_VECTOR_INDEX, SOURCE_LEXICAL_INDEX}
                for names in source_search_indexes.values()
            ),
            "claim_indexes": {
                "claim_artifact_key_unique", "claim_contradiction_lookup"
            } <= claim_indexes,
            "memory_indexes": {
                "memory_id_unique", "memory_active_pruning", "memory_expiry_ttl"
            } <= memory_indexes,
            "memory_v2": invalid_memory_v2 == 0,
        }
        print({"counts": counts, "validators": validator_count,
               "search_indexes_ready": len(statuses),
               "invalid_memory_v2": invalid_memory_v2, "checks": checks})
        if not all(checks.values()):
            raise SystemExit("Schema diagnostic failed")
    finally:
        client.close()


if __name__ == "__main__":
    main()
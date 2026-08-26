import os

import pytest

from core.memory import MEMORY_VECTOR_INDEX
from core.memory_policy import MEMORY_SCHEMA_VERSION
from core.schemas import CLAIM_ASSERTIONS_COLLECTION, GOVERNANCE_COLLECTION
from core.settings import get_settings
from core.source_agents import SourceAgent
from db.bootstrap import connect, search_index_statuses

pytestmark = [
    pytest.mark.integration,
    pytest.mark.atlas_live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_INTEGRATION") != "1",
        reason="set RUN_LIVE_INTEGRATION=1",
    ),
]


def test_atlas_indexes_acl_and_retention_are_live():
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
        statuses = search_index_statuses(db)
        memory_index = list(db.memories.list_search_indexes(MEMORY_VECTOR_INDEX))[0]
        memory_filter_paths = {
            field["path"] for field in memory_index["latestDefinition"]["fields"]
            if field.get("type") == "filter"
        }
        agent = SourceAgent(db.github, "github", 5, db[CLAIM_ASSERTIONS_COLLECTION])
        allowed = agent.search("PHI logging", settings.realm_id, ["role:security"])
        denied = agent.search("PHI logging", settings.realm_id, ["role:unknown"])
        memory_ttl = [
            index.get("expireAfterSeconds") for index in db.memories.list_indexes()
            if "expireAfterSeconds" in index
        ]
        assert set(statuses.values()) == {"READY"}
        assert len(statuses) == 11
        assert {
            "realm_id", "user_id", "memory_type", "valid_from", "valid_until",
            "schema_version", "tombstoned", "expires_at",
        } <= memory_filter_paths
        assert db.memories.count_documents({
            "schema_version": {"$ne": MEMORY_SCHEMA_VERSION}
        }) == 0
        assert db[GOVERNANCE_COLLECTION].count_documents({
            "realm_id": settings.realm_id
        }) == 800
        assert allowed
        assert denied == []
        assert 0 in memory_ttl
    finally:
        client.close()
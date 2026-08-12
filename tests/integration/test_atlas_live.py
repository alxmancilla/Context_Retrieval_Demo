import os

import pytest

from core.memory import MEMORY_VECTOR_INDEX
from core.schemas import ALL_SOURCES
from core.settings import get_settings
from core.source_agents import SOURCE_VECTOR_INDEX, SourceAgent
from db.bootstrap import connect

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
    )
    try:
        statuses = {
            source: list(db[source].list_search_indexes(SOURCE_VECTOR_INDEX))[0]["status"]
            for source in ALL_SOURCES
        }
        statuses["memories"] = list(
            db.memories.list_search_indexes(MEMORY_VECTOR_INDEX)
        )[0]["status"]
        agent = SourceAgent(db.github, "github", 5)
        allowed = agent.search("PHI logging", settings.realm_id, ["role:security"])
        denied = agent.search("PHI logging", settings.realm_id, ["role:unknown"])
        memory_ttl = [
            index.get("expireAfterSeconds") for index in db.memories.list_indexes()
            if "expireAfterSeconds" in index
        ]
        assert set(statuses.values()) == {"READY"}
        assert allowed
        assert denied == []
        assert 0 in memory_ttl
    finally:
        client.close()
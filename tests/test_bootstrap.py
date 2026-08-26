from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from db.bootstrap import (
    LEGACY_SOURCE_LEXICAL_INDEX,
    LEGACY_SOURCE_VECTOR_INDEX,
    MEMORY_ID_INDEX,
    SearchIndexTypeMismatch,
    _auto_embed_definition,
    _ensure_auto_embed_index,
    _ensure_lexical_index,
    _ensure_memory_indexes,
    _lexical_definition,
    _migrate_memories,
    _remove_legacy_source_indexes,
    wait_for_indexes,
)
from db.schema import ensure_validator, memory_validator, source_validator


class FakeSearchCollection:
    def __init__(self, index=None):
        self.index = index
        self.created = []
        self.updated = []

    def list_search_indexes(self, _name):
        return [self.index] if self.index else []

    def create_search_index(self, model):
        self.created.append(model)

    def update_search_index(self, name, definition):
        self.updated.append((name, definition))


def test_auto_embed_index_is_unchanged_when_definition_matches():
    definition = _auto_embed_definition(["realm_id", "access_principals"])
    collection = FakeSearchCollection({
        "name": "vector", "type": "vectorSearch", "latestDefinition": definition,
    })
    assert _ensure_auto_embed_index(
        collection, "vector", ["realm_id", "access_principals"]
    ) == "unchanged"
    assert collection.updated == []


def test_auto_embed_index_definition_drift_updates_in_place():
    collection = FakeSearchCollection({
        "name": "vector", "type": "vectorSearch",
        "latestDefinition": _auto_embed_definition(["realm_id"]),
    })
    assert _ensure_auto_embed_index(
        collection, "vector", ["realm_id", "access_principals"]
    ) == "updated"
    assert collection.updated == [
        ("vector", _auto_embed_definition(["realm_id", "access_principals"]))
    ]


def test_auto_embed_index_rejects_incompatible_type():
    collection = FakeSearchCollection({
        "name": "vector", "type": "search", "latestDefinition": {"mappings": {}},
    })
    with pytest.raises(SearchIndexTypeMismatch, match="expected vectorSearch"):
        _ensure_auto_embed_index(collection, "vector", ["realm_id"])


def test_lexical_index_is_convergent_and_explicitly_mapped():
    definition = _lexical_definition()
    collection = FakeSearchCollection({
        "name": "lexical", "type": "search", "latestDefinition": definition,
    })
    assert _ensure_lexical_index(collection, "lexical") == "unchanged"
    assert definition["mappings"]["dynamic"] is False
    assert definition["mappings"]["fields"]["realm_id"] == {"type": "token"}


def test_obsolete_source_indexes_are_removed_during_migration():
    class LegacyCollection:
        def __init__(self):
            self.dropped = []

        def list_search_indexes(self, name):
            legacy = {LEGACY_SOURCE_VECTOR_INDEX, LEGACY_SOURCE_LEXICAL_INDEX}
            return [{"name": name}] if name in legacy else []

        def drop_search_index(self, name):
            self.dropped.append(name)

    collection = LegacyCollection()
    assert _remove_legacy_source_indexes(collection) == 2
    assert collection.dropped == [
        LEGACY_SOURCE_VECTOR_INDEX, LEGACY_SOURCE_LEXICAL_INDEX,
    ]


def test_memory_identity_index_is_unique_and_partial():
    calls = []
    collection = SimpleNamespace(create_index=lambda *args, **kwargs: calls.append((args, kwargs)))
    _ensure_memory_indexes(collection)
    memory_call = next(call for call in calls if call[1].get("name") == MEMORY_ID_INDEX)
    assert memory_call[0] == ("memory_id",)
    assert memory_call[1]["unique"] is True
    assert memory_call[1]["partialFilterExpression"] == {
        "memory_id": {"$type": "string"}
    }
    assert any(call[1].get("name") == "memory_active_pruning" for call in calls)


def test_memory_v2_migration_backfills_governance_and_version_fields():
    class Collection:
        def update_many(self, query, pipeline):
            self.query = query
            self.pipeline = pipeline
            return SimpleNamespace(modified_count=3)

    collection = Collection()
    count = _migrate_memories(
        collection, datetime.now(UTC), 30, "embed-v1", "prompt-v2", "agent-v2",
    )
    fields = collection.pipeline[0]["$set"]
    assert count == 3
    assert collection.query == {"schema_version": {"$ne": 2}}
    assert fields["memory_type"] == {"$ifNull": ["$memory_type", "legacy_context"]}
    assert fields["embedding_profile"] == {"$ifNull": ["$embedding_profile", "embed-v1"]}
    assert "provenance" in fields


def test_memory_validator_requires_governed_memory_v2_fields():
    schema = memory_validator()["$jsonSchema"]
    assert {
        "memory_type", "summary", "importance", "valid_from", "valid_until",
        "provenance", "embedding_profile", "prompt_version", "agent_version",
        "schema_version",
    } <= set(schema["required"])
    assert schema["properties"]["schema_version"] == {"enum": [2]}


def test_schema_validation_rolls_out_moderate_warn_before_strict_error():
    class Database:
        def command(self, command):
            self.command_value = command

    database = Database()
    ensure_validator(database, "github", source_validator(), "warn")
    assert database.command_value["validationLevel"] == "moderate"
    assert database.command_value["validationAction"] == "warn"
    ensure_validator(database, "github", source_validator(), "error")
    assert database.command_value["validationLevel"] == "strict"


def test_wait_for_indexes_raises_when_readiness_deadline_expires():
    class Database:
        memories = object()

        def __getitem__(self, _name):
            return object()

    with pytest.raises(TimeoutError, match="did not become READY"):
        wait_for_indexes(Database(), timeout_seconds=0)
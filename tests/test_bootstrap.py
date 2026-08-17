from types import SimpleNamespace

import pytest

from db.bootstrap import (
    MEMORY_ID_INDEX,
    SearchIndexTypeMismatch,
    _auto_embed_definition,
    _ensure_auto_embed_index,
    _ensure_memory_indexes,
    wait_for_indexes,
)


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


def test_wait_for_indexes_raises_when_readiness_deadline_expires():
    class Database:
        memories = object()

        def __getitem__(self, _name):
            return object()

    with pytest.raises(TimeoutError, match="did not become READY"):
        wait_for_indexes(Database(), timeout_seconds=0)
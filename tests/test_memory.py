from types import SimpleNamespace

from core.memory import MEMORY_VECTOR_INDEX, SemanticMemory, redact_memory_text


class FakeCursor(list):
    def sort(self, *_args):
        return self

    def skip(self, amount):
        return FakeCursor(self[amount:])


class FakeCollection:
    def __init__(self, overflow=None):
        self.pipeline = None
        self.updates = []
        self.bulk_updates = []
        self.overflow = overflow or []

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return []

    def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))

    def find(self, *_args):
        return FakeCursor(self.overflow)

    def update_many(self, query, update):
        self.bulk_updates.append((query, update))
        return SimpleNamespace(modified_count=4)


def test_memory_redacts_common_sensitive_values_before_persistence():
    content = (
        "Email jane@example.com SSN 123-45-6789 phone 212-555-0199 "
        "MRN: AB-12345 token=secret-value"
    )
    redacted = redact_memory_text(content)
    assert "jane@example.com" not in redacted
    assert "123-45-6789" not in redacted
    assert "212-555-0199" not in redacted
    assert "AB-12345" not in redacted
    assert "secret-value" not in redacted
    assert {"[EMAIL]", "[SSN]", "[PHONE]", "[PATIENT_ID]", "[SECRET]"} <= set(redacted.split())


def test_memory_save_is_deduplicated_expiring_and_bounded():
    collection = FakeCollection(overflow=[{"_id": "old"}, {"_id": "older"}])
    memory = SemanticMemory(collection, retention_days=30, max_per_user=1)
    memory.save("Question from jane@example.com", "realm", "user", "corr-1")
    memory.save("Question from jane@example.com", "realm", "user", "corr-2")

    first_query, first_update, upsert = collection.updates[0]
    assert upsert is True
    assert first_query == collection.updates[1][0]
    assert first_update["$set"]["content"] == "Question from [EMAIL]"
    assert first_update["$set"]["expires_at"] > first_update["$set"]["updated_at"]
    assert collection.bulk_updates[0][0] == {"_id": {"$in": ["older"]}}
    assert collection.bulk_updates[0][1]["$set"]["tombstoned"] is True


def test_memory_search_enforces_scope_tombstone_and_expiry():
    collection = FakeCollection()
    SemanticMemory(collection, top_k=3).search("prior answer", "realm", "user")
    vector = collection.pipeline[0]["$vectorSearch"]
    assert vector["index"] == MEMORY_VECTOR_INDEX
    assert {"tombstoned": False} in vector["filter"]["$and"]
    assert any("expires_at" in condition for condition in vector["filter"]["$and"])


def test_user_memory_deletion_tombstones_and_expires_content():
    collection = FakeCollection()
    count = SemanticMemory(collection).delete_user("realm", "user")
    assert count == 4
    query, update = collection.bulk_updates[0]
    assert query == {"realm_id": "realm", "user_id": "user", "tombstoned": False}
    assert update["$set"]["content"] == "[deleted]"
    assert update["$set"]["tombstoned"] is True
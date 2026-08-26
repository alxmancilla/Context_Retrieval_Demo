from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from agent.nodes import AgentNodes
from core.memory import MEMORY_VECTOR_INDEX, SemanticMemory, redact_memory_text
from core.memory_metrics import MemoryMetrics
from core.memory_policy import MEMORY_SCHEMA_VERSION, decide_memory_write


class FakeCursor(list):
    def sort(self, *_args):
        return self

    def skip(self, amount):
        return FakeCursor(self[amount:])


class FakeCollection:
    def __init__(self, overflow=None, aggregate_rows=None):
        self.pipeline = None
        self.updates = []
        self.bulk_updates = []
        self.overflow = overflow or []
        self.aggregate_rows = aggregate_rows or []
        self.memory_ids = set()

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return self.aggregate_rows

    def find_one(self, query, *_args):
        return ({"_id": "existing", "tombstoned": False}
                if query.get("memory_id") in self.memory_ids else None)

    def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        if upsert and "memory_id" in query:
            self.memory_ids.add(query["memory_id"])

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
    decision = decide_memory_write(
        "My preference is email jane@example.com", "Understood.", [],
    )
    assert memory.save(decision, "realm", "user", "corr-1", "turn-1") == "created"
    assert memory.save(decision, "realm", "user", "corr-2", "turn-2") == "reinforced"

    first_query, first_update, upsert = collection.updates[0]
    assert upsert is True
    assert first_query == collection.updates[1][0]
    assert first_update["$set"]["content"] == "My preference is email [EMAIL]"
    assert first_update["$set"]["expires_at"] > first_update["$set"]["updated_at"]
    assert first_update["$set"]["schema_version"] == MEMORY_SCHEMA_VERSION
    assert first_update["$setOnInsert"]["memory_type"] == "user_preference"
    assert first_update["$setOnInsert"]["provenance"]["source_turn_id"] == "turn-1"
    assert collection.bulk_updates[0][0] == {"_id": {"$in": ["older"]}}
    assert collection.bulk_updates[0][1]["$set"]["tombstoned"] is True


def test_memory_search_enforces_scope_tombstone_and_expiry():
    collection = FakeCollection()
    SemanticMemory(collection, top_k=3).search("prior answer", "realm", "user")
    vector = collection.pipeline[0]["$vectorSearch"]
    assert vector["index"] == MEMORY_VECTOR_INDEX
    assert {"tombstoned": False} in vector["filter"]["$and"]
    assert any("expires_at" in condition for condition in vector["filter"]["$and"])
    assert {"schema_version": MEMORY_SCHEMA_VERSION} in vector["filter"]["$and"]
    assert any("memory_type" in condition for condition in vector["filter"]["$and"])


def test_selective_memory_policy_rejects_enterprise_qa_and_accepts_preferences():
    rejected = decide_memory_write("What is the Rx policy?", "OAuth 2 is current.", [])
    degraded = decide_memory_write("I prefer tables", "Okay", ["source_degraded"])
    accepted = decide_memory_write("I prefer concise tables", "Understood.", [])
    assert rejected.reason == "enterprise_qa_not_durable"
    assert degraded.reason == "turn_degraded"
    assert accepted.accepted is True
    assert accepted.memory_type == "user_preference"
    assert accepted.importance == 0.85


def test_near_duplicate_memory_is_merged_without_changing_identity_content():
    collection = FakeCollection(aggregate_rows=[{"memory_id": "existing", "score": 0.97}])
    memory = SemanticMemory(collection)
    decision = decide_memory_write("My preference is short answers", "Understood.", [])
    assert memory.save(decision, "realm", "user", "corr", "turn") == "merged"
    query, update, upsert = collection.updates[0]
    assert query == {"memory_id": "existing"}
    assert upsert is False
    assert "content" not in update["$set"]
    assert update["$inc"] == {"reinforcement_count": 1, "revision": 1}


def test_deleted_memory_identity_is_not_resurrected():
    collection = FakeCollection()
    collection.find_one = lambda *_args: {"_id": "deleted", "tombstoned": True}
    memory = SemanticMemory(collection)
    decision = decide_memory_write("I prefer short answers", "Understood.", [])
    assert memory.save(decision, "realm", "user", "corr", "turn") == "suppressed_deleted"
    assert collection.updates == []
    assert memory.metrics.snapshot()["suppressed_deleted"] == 1


def test_agent_node_writes_only_selected_memory_and_reports_decision():
    class Memory:
        def __init__(self):
            self.metrics = MemoryMetrics()
            self.saved = []

        def save(self, decision, *_args):
            self.saved.append(decision)
            return "created"

    nodes = object.__new__(AgentNodes)
    nodes.memory = Memory()
    base = {
        "answer": "Understood.", "realm_id": "realm", "user_id": "user",
        "correlation_id": "corr", "degraded": [],
    }
    rejected = nodes.save_memory({**base, "query": "What is the current Rx policy?"})
    accepted = nodes.save_memory({**base, "query": "I prefer concise tables"})
    assert rejected["memory_write"]["accepted"] is False
    assert nodes.memory.saved[0].memory_type == "user_preference"
    assert accepted["memory_write"]["outcome"] == "created"


def test_compaction_node_returns_remove_messages_and_summary():
    nodes = object.__new__(AgentNodes)
    nodes.memory = SimpleNamespace(metrics=MemoryMetrics())
    messages = [
        HumanMessage(content=f"q{index}", id=f"h{index}")
        if index % 2 == 0 else AIMessage(content=f"a{index}", id=f"a{index}")
        for index in range(8)
    ]
    result = nodes.compact_conversation({"messages": messages})
    assert result["conversation_summary"]
    assert len(result["messages"]) == 2


def test_user_memory_deletion_tombstones_and_expires_content():
    collection = FakeCollection()
    count = SemanticMemory(collection).delete_user("realm", "user")
    assert count == 4
    query, update = collection.bulk_updates[0]
    assert query == {"realm_id": "realm", "user_id": "user", "tombstoned": False}
    assert update["$set"]["content"] == "[deleted]"
    assert update["$set"]["summary"] == "[deleted]"
    assert update["$set"]["tombstoned"] is True


def test_memory_metrics_are_content_free_and_track_decisions():
    collection = FakeCollection()
    memory = SemanticMemory(collection)
    memory.metrics.record_decision(False)
    memory.metrics.record_context(2, 120, 1)
    snapshot = memory.metrics.snapshot()
    assert snapshot["write_candidates"] == 1
    assert snapshot["write_rejected"] == 1
    assert snapshot["context_messages"] == 2
    assert snapshot["context_chars"] == 120
    assert snapshot["context_compacted"] == 1
    assert "content" not in snapshot
import hashlib
import re
from datetime import UTC, datetime, timedelta

from pymongo.collection import Collection

from core.memory_metrics import MemoryMetrics
from core.memory_policy import (
    MEMORY_SCHEMA_VERSION,
    MEMORY_TYPES,
    MemoryType,
    MemoryWriteDecision,
)

MEMORY_VECTOR_INDEX = "memory_vector_retained"
REDACTIONS = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[EMAIL]"),
    (re.compile(r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\+?1[-. ]?)?\(?[0-9]{3}\)?[-. ][0-9]{3}[-. ][0-9]{4}\b"), "[PHONE]"),
    (re.compile(r"\b(?:mrn|member id|patient id)\s*[:#=-]?\s*[A-Z0-9-]{4,}\b", re.IGNORECASE), "[PATIENT_ID]"),
    (re.compile(r"\b(?:api[_ -]?key|password|token)\s*[:=]\s*\S+", re.IGNORECASE), "[SECRET]"),
)


def redact_memory_text(content: str) -> str:
    redacted = content
    for pattern, replacement in REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted[:5000]


class SemanticMemory:
    """User-scoped, bounded context memory; never factual authority."""

    def __init__(
        self, collection: Collection, top_k: int = 3,
        retention_days: int = 30, max_per_user: int = 100,
        similarity_threshold: float = 0.92,
        embedding_profile: str = "voyage-4:auto-embed:v1",
        prompt_version: str = "answer-v2",
        agent_version: str = "memory-v2",
        metrics: MemoryMetrics | None = None,
    ) -> None:
        self.collection = collection
        self.top_k = top_k
        self.retention_days = retention_days
        self.max_per_user = max_per_user
        self.similarity_threshold = similarity_threshold
        self.embedding_profile = embedding_profile
        self.prompt_version = prompt_version
        self.agent_version = agent_version
        self.metrics = metrics or MemoryMetrics()

    def search(
        self, query: str, realm_id: str, user_id: str,
        memory_types: list[MemoryType] | None = None,
    ) -> list[dict]:
        now = datetime.now(UTC)
        selected_types = memory_types or list(MEMORY_TYPES)
        pipeline = [
            {"$vectorSearch": {
                "index": MEMORY_VECTOR_INDEX, "path": "content", "query": query,
                "numCandidates": max(20, self.top_k * 10), "limit": self.top_k,
                "filter": {"$and": [
                    {"realm_id": realm_id}, {"user_id": user_id},
                    {"tombstoned": False}, {"expires_at": {"$gt": now}},
                    {"valid_from": {"$lte": now}}, {"valid_until": {"$gt": now}},
                    {"schema_version": MEMORY_SCHEMA_VERSION},
                    {"memory_type": {"$in": selected_types}},
                ]},
            }},
            {"$project": {"_id": 0, "memory_id": 1, "memory_type": 1,
                           "content": 1, "summary": 1, "importance": 1,
                           "created_at": 1, "provenance": 1,
                           "score": {"$meta": "vectorSearchScore"}}},
        ]
        rows = list(self.collection.aggregate(pipeline))
        self.metrics.record_retrieval(len(rows))
        return rows

    def _find_similar(
        self, content: str, realm_id: str, user_id: str, memory_type: MemoryType,
    ) -> dict | None:
        pipeline = [
            {"$vectorSearch": {
                "index": MEMORY_VECTOR_INDEX, "path": "content", "query": content,
                "numCandidates": 20, "limit": 1,
                "filter": {"$and": [
                    {"realm_id": realm_id}, {"user_id": user_id},
                    {"memory_type": memory_type}, {"tombstoned": False},
                    {"schema_version": MEMORY_SCHEMA_VERSION},
                ]},
            }},
            {"$project": {"_id": 0, "memory_id": 1,
                           "score": {"$meta": "vectorSearchScore"}}},
        ]
        rows = list(self.collection.aggregate(pipeline))
        return rows[0] if rows and rows[0].get("score", 0.0) >= self.similarity_threshold else None

    def save(
        self, decision: MemoryWriteDecision, realm_id: str, user_id: str,
        correlation_id: str, source_turn_id: str,
    ) -> str:
        if not decision.accepted or decision.memory_type is None:
            raise ValueError("Only accepted memory decisions can be persisted")
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=self.retention_days)
        safe_content = redact_memory_text(decision.content)
        safe_summary = redact_memory_text(decision.summary)[:500]
        content_hash = hashlib.sha256(safe_content.encode()).hexdigest()
        memory_id = hashlib.sha256(
            f"{realm_id}\0{user_id}\0{content_hash}".encode()
        ).hexdigest()
        provenance = {
            "correlation_id": correlation_id, "source_turn_id": source_turn_id,
            "node": "save_memory", "reason": decision.reason,
        }
        common_set = {
            "content": safe_content, "summary": safe_summary,
            "content_hash": content_hash, "updated_at": now,
            "expires_at": expires_at, "valid_until": expires_at,
            "tombstoned": False, "deleted_at": None,
            "embedding_profile": self.embedding_profile,
            "prompt_version": self.prompt_version, "agent_version": self.agent_version,
            "schema_version": MEMORY_SCHEMA_VERSION,
        }
        existing = self.collection.find_one(
            {"memory_id": memory_id}, {"_id": 1, "tombstoned": 1},
        )
        if existing and existing.get("tombstoned") is True:
            self.metrics.record_outcome("suppressed_deleted")
            return "suppressed_deleted"
        if existing:
            self.collection.update_one(
                {"memory_id": memory_id},
                {"$set": {**common_set, "last_reinforced_by": provenance},
                 "$max": {"importance": decision.importance},
                 "$inc": {"reinforcement_count": 1, "revision": 1}},
            )
            self.metrics.record_outcome("reinforced")
            return "reinforced"

        similar = self._find_similar(
            safe_content, realm_id, user_id, decision.memory_type,
        )
        if similar:
            merge_set = {
                key: value for key, value in common_set.items()
                if key not in {"content", "summary", "content_hash"}
            }
            self.collection.update_one(
                {"memory_id": similar["memory_id"]},
                {"$set": {**merge_set, "last_reinforced_by": provenance},
                 "$max": {"importance": decision.importance},
                 "$inc": {"reinforcement_count": 1, "revision": 1}},
            )
            self.metrics.record_outcome("merged")
            return "merged"

        self.collection.update_one(
            {"memory_id": memory_id},
            {
                "$set": common_set,
                "$setOnInsert": {
                    "memory_id": memory_id, "realm_id": realm_id, "user_id": user_id,
                    "memory_type": decision.memory_type, "importance": decision.importance,
                    "created_at": now, "valid_from": now,
                    "reinforcement_count": 1, "revision": 1,
                    "provenance": provenance,
                },
            },
            upsert=True,
        )
        self.metrics.record_outcome("created")
        overflow = list(
            self.collection.find(
                {"realm_id": realm_id, "user_id": user_id, "tombstoned": False},
                {"_id": 1},
            ).sort("updated_at", -1).skip(self.max_per_user)
        )
        if overflow:
            self.collection.update_many(
                {"_id": {"$in": [row["_id"] for row in overflow]}},
                {"$set": {
                    "content": "[deleted]", "summary": "[deleted]",
                    "content_hash": hashlib.sha256(b"[deleted]").hexdigest(),
                    "tombstoned": True, "deleted_at": now, "updated_at": now,
                    "expires_at": now, "valid_until": now,
                }},
            )
        return "created"

    def delete_user(self, realm_id: str, user_id: str) -> int:
        now = datetime.now(UTC)
        result = self.collection.update_many(
            {"realm_id": realm_id, "user_id": user_id, "tombstoned": False},
            {"$set": {
                "content": "[deleted]", "summary": "[deleted]",
                "content_hash": hashlib.sha256(b"[deleted]").hexdigest(),
                "tombstoned": True, "deleted_at": now, "updated_at": now,
                "expires_at": now, "valid_until": now,
            }},
        )
        return result.modified_count

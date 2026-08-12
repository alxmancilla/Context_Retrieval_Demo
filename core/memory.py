import hashlib
import re
from datetime import UTC, datetime, timedelta

from pymongo.collection import Collection

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
    ) -> None:
        self.collection = collection
        self.top_k = top_k
        self.retention_days = retention_days
        self.max_per_user = max_per_user

    def search(self, query: str, realm_id: str, user_id: str) -> list[dict]:
        now = datetime.now(UTC)
        pipeline = [
            {"$vectorSearch": {
                "index": MEMORY_VECTOR_INDEX, "path": "content", "query": query,
                "numCandidates": max(20, self.top_k * 10), "limit": self.top_k,
                "filter": {"$and": [
                    {"realm_id": realm_id}, {"user_id": user_id},
                    {"tombstoned": False}, {"expires_at": {"$gt": now}},
                ]},
            }},
            {"$project": {"_id": 0, "content": 1, "created_at": 1,
                           "score": {"$meta": "vectorSearchScore"}}},
        ]
        return list(self.collection.aggregate(pipeline))

    def save(self, content: str, realm_id: str, user_id: str, correlation_id: str) -> None:
        now = datetime.now(UTC)
        safe_content = redact_memory_text(content)
        content_hash = hashlib.sha256(safe_content.encode()).hexdigest()
        memory_id = hashlib.sha256(
            f"{realm_id}\0{user_id}\0{content_hash}".encode()
        ).hexdigest()
        self.collection.update_one(
            {"memory_id": memory_id},
            {
                "$set": {
                    "content": safe_content, "content_hash": content_hash,
                    "updated_at": now, "expires_at": now + timedelta(days=self.retention_days),
                    "tombstoned": False, "deleted_at": None,
                },
                "$setOnInsert": {
                    "memory_id": memory_id, "realm_id": realm_id, "user_id": user_id,
                    "correlation_id": correlation_id, "node": "save_memory",
                    "created_at": now,
                },
            },
            upsert=True,
        )
        overflow = list(
            self.collection.find(
                {"realm_id": realm_id, "user_id": user_id, "tombstoned": False},
                {"_id": 1},
            ).sort("updated_at", -1).skip(self.max_per_user)
        )
        if overflow:
            self.collection.update_many(
                {"_id": {"$in": [row["_id"] for row in overflow]}},
                {"$set": {"content": "[deleted]", "tombstoned": True,
                          "deleted_at": now, "expires_at": now}},
            )

    def delete_user(self, realm_id: str, user_id: str) -> int:
        now = datetime.now(UTC)
        result = self.collection.update_many(
            {"realm_id": realm_id, "user_id": user_id, "tombstoned": False},
            {"$set": {"content": "[deleted]", "tombstoned": True,
                      "deleted_at": now, "expires_at": now}},
        )
        return result.modified_count

from typing import Any

from pymongo.collection import Collection
from pymongo.errors import OperationFailure

from core.schemas import SourceHit, SourceName

SOURCE_VECTOR_INDEX = "content_vector_acl"
CONTRADICTION_PROBE_SCAN_LIMIT = 10
CONTRADICTION_ALTERNATE_VALUE_LIMIT = 3


class SearchIndexNotReady(RuntimeError):
    pass


class SourceAgent:
    """Thin, MCP-shaped source specialist backed by one MongoDB collection."""

    def __init__(self, collection: Collection, source: SourceName, top_k: int) -> None:
        self.collection = collection
        self.source = source
        self.top_k = top_k

    @property
    def tool_descriptor(self) -> dict[str, Any]:
        return {
            "name": f"search_{self.source}",
            "description": f"Semantic search over the simulated {self.source} island",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }

    def search(self, query: str, realm_id: str, access_principals: list[str]) -> list[dict]:
        if not access_principals:
            raise ValueError("At least one access principal is required")
        pipeline = [
            {
                "$vectorSearch": {
                    "index": SOURCE_VECTOR_INDEX,
                    "path": "content",
                    "query": query,
                    "numCandidates": max(self.top_k * 10, 20),
                    "limit": self.top_k,
                    "filter": {
                        "$and": [
                            {"realm_id": realm_id},
                            {"access_principals": {"$in": access_principals}},
                        ]
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "artifact_id": 1,
                    "source": 1,
                    "title": 1,
                    "content": 1,
                    "url": 1,
                    "updated_at": 1,
                    "claims": {"$ifNull": ["$claims", {}]},
                    "metadata": {"$ifNull": ["$metadata", {}]},
                    "governance": {"$ifNull": ["$governance", {}]},
                    "vector_score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        try:
            rows = self.collection.aggregate(pipeline)
            validated = [SourceHit.model_validate(row).model_dump() for row in rows]
            return self._with_contradiction_candidates(
                validated, realm_id, access_principals
            )
        except OperationFailure as exc:
            detail = str(exc).lower()
            unavailable = ("not ready", "not found", "not available")
            if "index" in detail and any(marker in detail for marker in unavailable):
                raise SearchIndexNotReady(SOURCE_VECTOR_INDEX) from None
            raise

    def _with_contradiction_candidates(
        self, rows: list[dict], realm_id: str, access_principals: list[str]
    ) -> list[dict]:
        if not rows or not hasattr(self.collection, "find"):
            return rows
        values_by_claim: dict[str, set[str]] = {}
        for row in rows:
            for claim, value in row.get("claims", {}).items():
                if claim.replace("_", "").isalnum():
                    values_by_claim.setdefault(claim, set()).add(str(value))
        existing_ids = {row["artifact_id"] for row in rows}
        expanded = list(rows)
        projection = {
            "_id": 0, "artifact_id": 1, "source": 1, "title": 1, "content": 1,
            "url": 1, "updated_at": 1, "claims": 1, "metadata": 1, "governance": 1,
        }
        for claim, observed_values in values_by_claim.items():
            cursor = self.collection.find(
                {"$and": [
                    {"realm_id": realm_id},
                    {"access_principals": {"$in": access_principals}},
                    {f"claims.{claim}": {"$exists": True, "$nin": list(observed_values)}},
                ]},
                projection,
            ).sort("updated_at", -1).limit(CONTRADICTION_PROBE_SCAN_LIMIT)
            added_values: set[str] = set()
            for candidate in cursor:
                if candidate["artifact_id"] in existing_ids:
                    continue
                alternate_value = str(candidate.get("claims", {}).get(claim, ""))
                if not alternate_value or alternate_value in added_values:
                    continue
                metadata = dict(candidate.get("metadata", {}))
                metadata["retrieval_reason"] = "contradiction_probe"
                candidate["metadata"] = metadata
                candidate["vector_score"] = 0.0
                expanded.append(SourceHit.model_validate(candidate).model_dump())
                existing_ids.add(candidate["artifact_id"])
                added_values.add(alternate_value)
                if len(added_values) >= CONTRADICTION_ALTERNATE_VALUE_LIMIT:
                    break
        return expanded

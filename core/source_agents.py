from collections.abc import Iterable
from typing import Any, Literal

from pymongo.collection import Collection
from pymongo.errors import OperationFailure

from core.schemas import SourceHit, SourceName

SOURCE_VECTOR_INDEX = "content_vector_acl"
SOURCE_LEXICAL_INDEX = "content_lexical"
CONTRADICTION_PROBE_SCAN_LIMIT = 10
CONTRADICTION_ALTERNATE_VALUE_LIMIT = 3
RetrievalMode = Literal["hybrid", "vector", "lexical"]


class SearchIndexNotReady(RuntimeError):
    pass


class SourceAgent:
    """Thin, MCP-shaped source specialist backed by one MongoDB collection."""

    def __init__(
        self, collection: Collection, source: SourceName, top_k: int,
        claim_collection: Collection | None = None,
        retrieval_mode: RetrievalMode = "hybrid",
    ) -> None:
        self.collection = collection
        self.source = source
        self.top_k = top_k
        self.claim_collection = claim_collection
        self.retrieval_mode = retrieval_mode

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
        pipeline = {
            "hybrid": self._hybrid_pipeline,
            "vector": self._vector_pipeline,
            "lexical": self._lexical_pipeline,
        }[self.retrieval_mode]
        try:
            rows = list(self.collection.aggregate(pipeline(query, realm_id, access_principals)))
        except OperationFailure as exc:
            detail = str(exc).lower()
            unavailable = ("not ready", "not found", "not available")
            if (
                self.retrieval_mode == "hybrid"
                and "index" in detail
                and any(marker in detail for marker in unavailable)
            ):
                try:
                    rows = list(self.collection.aggregate(
                        self._vector_pipeline(query, realm_id, access_principals)
                    ))
                    for row in rows:
                        row.setdefault("metadata", {})["retrieval_reason"] = (
                            "vector_only_lexical_index_unavailable"
                        )
                except OperationFailure:
                    raise SearchIndexNotReady(SOURCE_VECTOR_INDEX) from None
            else:
                raise
        validated = [SourceHit.model_validate(row).model_dump() for row in rows]
        return self._with_contradiction_candidates(validated, realm_id, access_principals)

    @staticmethod
    def _scope(realm_id: str, access_principals: list[str]) -> list[dict]:
        return [
            {"realm_id": realm_id},
            {"access_principals": {"$in": access_principals}},
        ]

    @staticmethod
    def _projection(score: Any) -> dict:
        return {
            "_id": 0, "artifact_id": 1, "source": 1, "title": 1,
            "content": 1, "url": 1, "updated_at": 1,
            "claims": {"$ifNull": ["$claims", {}]},
            "metadata": {"$ifNull": ["$metadata", {}]},
            "governance": {"$ifNull": ["$governance", {}]},
            "vector_score": score,
        }

    def _vector_pipeline(
        self, query: str, realm_id: str, access_principals: list[str],
    ) -> list[dict]:
        return [
            {"$vectorSearch": {
                "index": SOURCE_VECTOR_INDEX, "path": "content", "query": query,
                "numCandidates": max(self.top_k * 20, 50), "limit": self.top_k,
                "filter": {"$and": self._scope(realm_id, access_principals)},
            }},
            {"$project": self._projection({"$meta": "vectorSearchScore"})},
            {"$set": {"metadata.retrieval_reason": "vector_only_search"}},
        ]

    def _lexical_pipeline(
        self, query: str, realm_id: str, access_principals: list[str],
    ) -> list[dict]:
        return [
            {"$search": {
                "index": SOURCE_LEXICAL_INDEX,
                "compound": {
                    "must": [{"text": {
                        "query": query,
                        "path": ["title", "content", "artifact_id"],
                    }}],
                    "filter": [
                        {"equals": {"path": "realm_id", "value": realm_id}},
                        {"in": {"path": "access_principals", "value": access_principals}},
                    ],
                },
            }},
            {"$limit": self.top_k},
            {"$project": {
                **self._projection(0.0),
                "metadata": {"$ifNull": ["$metadata", {}]},
                "_search_score": {"$meta": "searchScore"},
            }},
            {"$set": {
                "vector_score": {"$min": [1.0, {"$divide": ["$_search_score", 10.0]}]},
                "metadata.retrieval_reason": "lexical_only_search",
            }},
            {"$project": {"_search_score": 0}},
        ]

    def _hybrid_pipeline(
        self, query: str, realm_id: str, access_principals: list[str],
    ) -> list[dict]:
        candidate_limit = max(self.top_k * 2, 10)
        return [
            {"$rankFusion": {
                "input": {"pipelines": {
                    "semantic": [{"$vectorSearch": {
                        "index": SOURCE_VECTOR_INDEX, "path": "content", "query": query,
                        "numCandidates": max(self.top_k * 20, 50),
                        "limit": candidate_limit,
                        "filter": {"$and": self._scope(realm_id, access_principals)},
                    }}],
                    "lexical": [
                        {"$search": {
                            "index": SOURCE_LEXICAL_INDEX,
                            "compound": {
                                "must": [{"text": {
                                    "query": query,
                                    "path": ["title", "content", "artifact_id"],
                                }}],
                                "filter": [
                                    {"equals": {"path": "realm_id", "value": realm_id}},
                                    {"in": {"path": "access_principals",
                                            "value": access_principals}},
                                ],
                            },
                        }},
                        {"$limit": candidate_limit},
                    ],
                }},
                "combination": {"weights": {"semantic": 0.7, "lexical": 0.3}},
                "scoreDetails": True,
            }},
            {"$limit": self.top_k},
            {"$set": {"_fusion": {"$meta": "scoreDetails"}}},
            {"$set": {
                "vector_score": {"$min": [
                    1.0, {"$multiply": ["$_fusion.value", 61.0]},
                ]},
                "metadata.retrieval_reason": "hybrid_rank_fusion",
            }},
            {"$project": self._projection("$vector_score")},
        ]

    def _with_contradiction_candidates(
        self, rows: list[dict], realm_id: str, access_principals: list[str]
    ) -> list[dict]:
        if not rows or self.claim_collection is None:
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
            cursor = self.claim_collection.find(
                {
                    "realm_id": realm_id,
                    "source": self.source,
                    "claim_key": claim,
                    "claim_value": {"$nin": sorted(observed_values)},
                    "access_principals": {"$in": access_principals},
                },
                {"_id": 0, "artifact_id": 1, "claim_value": 1, "updated_at": 1},
            ).sort("updated_at", -1).limit(CONTRADICTION_PROBE_SCAN_LIMIT)
            added_values: set[str] = set()
            assertions = []
            for assertion in cursor:
                alternate_value = str(assertion.get("claim_value", ""))
                if not alternate_value or alternate_value in added_values:
                    continue
                assertions.append(assertion)
                added_values.add(alternate_value)
                if len(assertions) >= CONTRADICTION_ALTERNATE_VALUE_LIMIT:
                    break
            artifact_ids = [item["artifact_id"] for item in assertions]
            candidates: Iterable[dict[str, Any]] = self.collection.find(
                {"$and": self._scope(realm_id, access_principals) + [
                    {"artifact_id": {"$in": artifact_ids}},
                ]},
                projection,
            ) if artifact_ids else []
            by_id = {candidate["artifact_id"]: candidate for candidate in candidates}
            for assertion in assertions:
                candidate = by_id.get(assertion["artifact_id"])
                if not candidate or candidate["artifact_id"] in existing_ids:
                    continue
                metadata = dict(candidate.get("metadata", {}))
                metadata["retrieval_reason"] = "contradiction_probe"
                candidate["metadata"] = metadata
                candidate["vector_score"] = 0.0
                expanded.append(SourceHit.model_validate(candidate).model_dump())
                existing_ids.add(candidate["artifact_id"])
        return expanded

import pytest
from pymongo.errors import OperationFailure

from core.source_agents import (
    SOURCE_LEXICAL_INDEX,
    SOURCE_VECTOR_INDEX,
    SearchIndexNotReady,
    SourceAgent,
)


class FakeCollection:
    def __init__(self) -> None:
        self.pipeline = None

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return [{
            "artifact_id": "github-test", "source": "github", "title": "Test",
            "content": "OAuth2", "url": "https://demo/test",
            "updated_at": "2026-08-01T00:00:00Z", "vector_score": 0.9,
            "claims": {}, "metadata": {},
        }]


def test_source_agent_uses_text_query_and_permission_filter():
    collection = FakeCollection()
    agent = SourceAgent(collection, "github", top_k=5)
    rows = agent.search(
        "How does auth work?", "realm-a", ["role:platform-engineer", "user:alice"]
    )
    fusion = collection.pipeline[0]["$rankFusion"]
    vector = fusion["input"]["pipelines"]["semantic"][0]["$vectorSearch"]
    lexical = fusion["input"]["pipelines"]["lexical"][0]["$search"]
    assert vector["query"] == "How does auth work?"
    assert vector["index"] == SOURCE_VECTOR_INDEX
    assert vector["filter"] == {"$and": [
        {"realm_id": "realm-a"},
        {"access_principals": {"$in": ["role:platform-engineer", "user:alice"]}},
    ]}
    assert "queryVector" not in vector
    assert lexical["index"] == SOURCE_LEXICAL_INDEX
    assert lexical["compound"]["filter"] == [
        {"equals": {"path": "realm_id", "value": "realm-a"}},
        {"in": {
            "path": "access_principals",
            "value": ["role:platform-engineer", "user:alice"],
        }},
    ]
    assert rows[0]["artifact_id"] == "github-test"


def test_source_agent_rejects_an_empty_principal_set():
    with pytest.raises(ValueError, match="access principal"):
        SourceAgent(FakeCollection(), "github", 5).search("auth", "realm-a", [])


def test_source_agent_exposes_mcp_shaped_descriptor():
    descriptor = SourceAgent(FakeCollection(), "github", 5).tool_descriptor
    assert descriptor["name"] == "search_github"
    assert descriptor["inputSchema"]["required"] == ["query"]


def test_source_agent_classifies_an_unavailable_search_index():
    class UnavailableCollection:
        def aggregate(self, _pipeline):
            raise OperationFailure("Atlas Search index is not ready")

    with pytest.raises(SearchIndexNotReady):
        SourceAgent(UnavailableCollection(), "github", 5).search(
            "auth", "realm-a", ["role:platform-engineer"]
        )


def test_contradiction_probe_is_permission_scoped_and_conservative():
    class Cursor(list):
        def sort(self, *_args):
            return self

        def limit(self, amount):
            return Cursor(self[:amount])

    class ContradictionCollection:
        def find(self, query, _projection):
            self.query = query
            return Cursor([{
                "artifact_id": "github-old", "source": "github", "title": "Old",
                "content": "OAuth 1", "url": "https://demo/old",
                "updated_at": "2024-01-01T00:00:00Z",
                "claims": {"auth": "oauth1"}, "metadata": {},
            }])

    class ClaimCollection:
        def find(self, query, _projection):
            self.query = query
            return Cursor([{
                "artifact_id": "github-old", "claim_value": "oauth1",
                "updated_at": "2024-01-01T00:00:00Z",
            }])

    collection = ContradictionCollection()
    claims = ClaimCollection()
    current = {
        "artifact_id": "github-current", "source": "github", "title": "Current",
        "content": "OAuth 2", "url": "https://demo/current",
        "updated_at": "2026-08-01T00:00:00Z", "vector_score": 0.9,
        "claims": {"auth": "oauth2"}, "metadata": {},
    }
    rows = SourceAgent(collection, "github", 5, claims)._with_contradiction_candidates(
        [current], "realm-a", ["role:platform-engineer"]
    )
    assert len(rows) == 2
    assert rows[1]["vector_score"] == 0.0
    assert rows[1]["metadata"]["retrieval_reason"] == "contradiction_probe"
    assert claims.query["realm_id"] == "realm-a"
    assert claims.query["access_principals"] == {"$in": ["role:platform-engineer"]}
    assert {"realm_id": "realm-a"} in collection.query["$and"]


def test_contradiction_probe_keeps_one_representative_per_alternate_value():
    class Cursor(list):
        def sort(self, *_args):
            return self

        def limit(self, amount):
            return Cursor(self[:amount])

    class Collection:
        def find(self, _query, _projection):
            return Cursor([
                {
                    "artifact_id": "old-1", "source": "github", "title": "Old one",
                    "content": "OAuth 1", "url": "https://demo/old-1",
                    "updated_at": "2024-01-03T00:00:00Z",
                    "claims": {"auth": "oauth1"}, "metadata": {},
                },
                {
                    "artifact_id": "old-2", "source": "github", "title": "Old duplicate",
                    "content": "OAuth 1", "url": "https://demo/old-2",
                    "updated_at": "2024-01-02T00:00:00Z",
                    "claims": {"auth": "oauth1"}, "metadata": {},
                },
                {
                    "artifact_id": "legacy", "source": "github", "title": "Legacy",
                    "content": "API key", "url": "https://demo/legacy",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "claims": {"auth": "api_key"}, "metadata": {},
                },
            ])

    class Claims:
        def find(self, _query, _projection):
            return Cursor([
                {"artifact_id": "old-1", "claim_value": "oauth1",
                 "updated_at": "2024-01-03T00:00:00Z"},
                {"artifact_id": "old-2", "claim_value": "oauth1",
                 "updated_at": "2024-01-02T00:00:00Z"},
                {"artifact_id": "legacy", "claim_value": "api_key",
                 "updated_at": "2024-01-01T00:00:00Z"},
            ])

    current = {
        "artifact_id": "current", "source": "github", "title": "Current",
        "content": "OAuth 2", "url": "https://demo/current",
        "updated_at": "2026-08-01T00:00:00Z", "vector_score": 0.9,
        "claims": {"auth": "oauth2"}, "metadata": {},
    }
    rows = SourceAgent(Collection(), "github", 5, Claims())._with_contradiction_candidates(
        [current], "realm", ["role:platform-engineer"]
    )
    assert [row["claims"]["auth"] for row in rows] == ["oauth2", "oauth1", "api_key"]

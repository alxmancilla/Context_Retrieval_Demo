from datetime import UTC, datetime
from types import SimpleNamespace

from agent.graph import _dispatch_retrieval
from agent.nodes import AgentNodes
from core.schemas import ALL_SOURCES


def test_empty_source_routing_dispatches_all_sources():
    sends = _dispatch_retrieval({
        "query": "question", "intent": {}, "realm_id": "realm", "user_id": "user",
        "access_principals": ["role:test"],
        "selected_sources": [], "correlation_id": "corr",
    })
    assert sends[0].node == "retrieve_memory"
    assert [send.arg["source"] for send in sends[1:]] == list(ALL_SOURCES)
    assert all(send.arg["correlation_id"] == "corr" for send in sends)


def test_malformed_empty_intent_uses_deterministic_fallback():
    nodes = object.__new__(AgentNodes)
    nodes.chat = SimpleNamespace(
        invoke_typed=lambda *_args: SimpleNamespace(sources=[])
    )
    result = nodes.parse_intent({"query": "enterprise question", "correlation_id": "corr"})
    assert result["selected_sources"] == list(ALL_SOURCES)
    assert "intent_parser_fallback" in result["degraded"]


def test_missing_registry_policy_is_reported_and_excluded():
    class Registry:
        def find(self, *_args, **_kwargs):
            return [{
                "source": "github", "authority": 1.0,
                "freshness_half_life_days": 365,
            }]

    nodes = object.__new__(AgentNodes)
    class Database:
        sources = Registry()

        def __getitem__(self, _name):
            return SimpleNamespace(find=lambda *_args, **_kwargs: [])

    nodes.db = Database()
    result = nodes.reconcile({
        "realm_id": "realm", "correlation_id": "corr",
        "source_results": {"teams": [{"artifact_id": "untrusted"}]},
    })
    assert result["ranked_hits"] == []
    assert result["degraded"] == ["source_registry_missing:teams"]


def test_memory_read_and_write_failures_degrade_without_raising():
    class FailedMemory:
        metrics = SimpleNamespace(record_decision=lambda *_args: None)

        def search(self, *_args):
            raise TimeoutError("read")

        def save(self, *_args):
            raise TimeoutError("write")

    nodes = object.__new__(AgentNodes)
    nodes.memory = FailedMemory()
    state = {
        "query": "I prefer concise answers", "answer": "Understood.", "realm_id": "realm",
        "user_id": "user", "correlation_id": "corr",
    }
    assert nodes.retrieve_memory(state)["degraded"] == ["memory_retrieval:TimeoutError"]
    assert nodes.save_memory(state)["degraded"] == ["memory_save:TimeoutError"]


def test_voyage_failure_falls_back_to_vector_scores():
    class Registry:
        def find(self, *_args, **_kwargs):
            return [{
                "source": "github", "authority": 1.0,
                "freshness_half_life_days": 365,
            }]

    class FailedReranker:
        model = "rerank-3"

        def rerank(self, *_args):
            raise TimeoutError("provider unavailable")

    nodes = object.__new__(AgentNodes)
    class Database:
        sources = Registry()

        def __getitem__(self, _name):
            return SimpleNamespace(find=lambda *_args, **_kwargs: [{
                "artifact_id": "gh-auth", "document_type": "implementation",
                "lifecycle_status": "active", "authority_override": None,
            }])

    nodes.db = Database()
    nodes.reranker = FailedReranker()
    result = nodes.reconcile({
        "query": "current auth", "realm_id": "realm", "correlation_id": "corr",
        "source_results": {"github": [{
            "artifact_id": "gh-auth", "source": "github", "title": "Current auth",
            "content": "OAuth 2", "url": "https://demo/gh-auth",
            "updated_at": datetime.now(UTC), "vector_score": 0.9,
        }]},
    })
    assert result["ranked_hits"][0]["vector_score"] == 0.9
    assert result["ranked_hits"][0]["rerank_score"] is None
    assert result["degraded"] == ["voyage_rerank:TimeoutError"]


def test_runtime_reconciliation_uses_protected_governance_policy():
    class Registry:
        def find(self, *_args, **_kwargs):
            return [{
                "source": "github", "authority": 1.0,
                "freshness_half_life_days": 365,
            }]

    class Database:
        sources = Registry()

        def __getitem__(self, _name):
            return SimpleNamespace(find=lambda *_args, **_kwargs: [{
                "artifact_id": "gh-auth", "document_type": "implementation",
                "lifecycle_status": "active", "authority_override": 0.2,
            }])

    nodes = object.__new__(AgentNodes)
    nodes.db = Database()
    nodes.reranker = None
    result = nodes.reconcile({
        "query": "auth", "realm_id": "realm", "correlation_id": "corr",
        "source_results": {"github": [{
            "artifact_id": "gh-auth", "source": "github", "title": "Auth",
            "content": "OAuth 2", "url": "https://demo/gh-auth",
            "updated_at": datetime.now(UTC), "vector_score": 0.9,
            "governance": {"authority_override": 1.0},
        }]},
    })
    assert result["ranked_hits"][0]["authority"] == 0.2
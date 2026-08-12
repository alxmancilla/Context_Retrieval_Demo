from datetime import UTC, datetime
from types import SimpleNamespace

from agent.graph import _dispatch_sources
from agent.nodes import AgentNodes
from core.schemas import ALL_SOURCES


def test_empty_source_routing_dispatches_all_sources():
    sends = _dispatch_sources({
        "query": "question", "intent": {}, "realm_id": "realm", "user_id": "user",
        "selected_sources": [], "correlation_id": "corr",
    })
    assert [send.arg["source"] for send in sends] == list(ALL_SOURCES)
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
    nodes.db = SimpleNamespace(sources=Registry())
    result = nodes.reconcile({
        "realm_id": "realm", "correlation_id": "corr",
        "source_results": {"teams": [{"artifact_id": "untrusted"}]},
    })
    assert result["ranked_hits"] == []
    assert result["degraded"] == ["source_registry_missing:teams"]


def test_memory_read_and_write_failures_degrade_without_raising():
    class FailedMemory:
        def search(self, *_args):
            raise TimeoutError("read")

        def save(self, *_args):
            raise TimeoutError("write")

    nodes = object.__new__(AgentNodes)
    nodes.memory = FailedMemory()
    state = {
        "query": "question", "answer": "answer", "realm_id": "realm",
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
        model = "rerank-2.5"

        def rerank(self, *_args):
            raise TimeoutError("provider unavailable")

    nodes = object.__new__(AgentNodes)
    nodes.db = SimpleNamespace(sources=Registry())
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
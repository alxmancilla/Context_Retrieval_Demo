from ui.presentation import (
    contradictions_markdown,
    evidence_markdown,
    intent_markdown,
    pipeline_trace_markdown,
    retrieval_pipeline_markdown,
    source_result_markdown,
)


def _hit() -> dict:
    return {
        "source": "github", "artifact_id": "github-auth", "title": "Auth | current",
        "url": "https://demo/auth", "vector_score": 0.91, "authority": 1.0,
        "rerank_score": 0.97, "freshness": 0.98, "truth_score": 0.95,
        "metadata": {"retrieval_reason": "hybrid_rank_fusion"},
    }


def test_evidence_inspector_explains_truth_score():
    rendered = evidence_markdown([_hit()])
    assert "55% semantic relevance" in rendered
    assert "0.970" in rendered
    assert "0.950" in rendered
    assert "https://demo/auth" in rendered


def test_contradiction_inspector_shows_preferred_artifact():
    rendered = contradictions_markdown([{
        "claim": "auth", "values": {"oauth2": ["github-auth"], "oauth1": ["wiki-old"]},
        "preferred_value": "oauth2", "preferred_artifact": "github-auth",
        "representatives": {
            "oauth2": {
                "artifact_id": "github-auth", "document_type": "implementation",
                "lifecycle_status": "active", "updated_at": "2026-08-01", "truth_score": 0.9,
            },
            "oauth1": {
                "artifact_id": "wiki-old", "document_type": "guide",
                "lifecycle_status": "historical", "updated_at": "2024-01-01",
                "truth_score": 0.3,
            },
        },
        "score_margin": 0.6,
        "reason": "GitHub is current and authoritative.",
    }])
    assert "oauth1" in rendered
    assert "github-auth" in rendered
    assert "Preferred" in rendered
    assert "historical" in rendered
    assert "0.600" in rendered


def test_intent_and_source_activity_are_readable():
    intent = intent_markdown({
        "intent": "architecture", "rewritten_query": "current auth",
        "sources": ["github", "jira"], "entities": {"service": "rx"},
    })
    source = source_result_markdown("github", [_hit()])
    assert "GitHub, Jira" in intent
    assert "current auth" in intent
    assert "similarity `0.910`" in source


def test_retrieval_pipeline_inspector_explains_hybrid_search_and_models():
    rendered = retrieval_pipeline_markdown(
        {"github": [_hit()]}, [_hit()], [], [],
        rerank_model="rerank-3",
        embedding_profile="voyage-4:auto-embed:v1",
        source_top_k=5,
        retrieval_mode="hybrid",
        routing_mode="all",
    )
    assert "Atlas `autoEmbed`" in rendered
    assert "$rankFusion" in rendered
    assert "rerank-3" in rendered
    assert "Retrieval mode" in rendered
    assert "Source routing mode" in rendered
    assert "all-source ablations" in rendered
    assert "Hybrid `$rankFusion` hits: `1`" in rendered


def test_pipeline_trace_shows_routing_retrieval_and_reranking_inline():
    rendered = pipeline_trace_markdown(
        {
            "intent": "customer_latency",
            "sources": ["github", "jira"],
            "rewritten_query": "reduce rag latency",
        },
        {"github": [_hit()], "jira": []},
        [_hit()],
        [],
        [],
        rerank_model="rerank-3",
        routing_mode="intent",
    )
    assert "Pipeline trace" in rendered
    assert "evidence, not answers" in rendered
    assert "Source routing" in rendered
    assert "Parallel retrieval" in rendered
    assert "Reranking" in rendered
    assert "rerank-3" in rendered
    assert "Top reranked evidence" in rendered

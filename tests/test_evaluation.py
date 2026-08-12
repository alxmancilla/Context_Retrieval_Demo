from evals.runner import score_result

CASE = {
    "id": "auth", "claim": "auth", "preferred_value": "oauth2",
    "preferred_artifact": "gh-current", "stale_artifacts": ["wiki-old"],
    "required_term_groups": [["oauth 2"], ["pkce"]],
    "representatives": {"oauth2": "gh-current", "oauth1": "wiki-old"},
    "max_source_appendix_artifacts": 2,
}


def test_evaluation_scores_verified_grounded_resolution():
    result = {
        "answer": "OAuth 2 with PKCE [github:gh-current](https://demo/gh).",
        "ranked_hits": [{
            "source": "github", "artifact_id": "gh-current", "url": "https://demo/gh",
            "claims": {"auth": "oauth2"},
        }],
        "contradictions": [{
            "claim": "auth", "preferred_value": "oauth2",
            "preferred_artifact": "gh-current",
            "values": {"oauth2": ["gh-current"], "oauth1": ["wiki-old"]},
            "representatives": {
                "oauth2": {"artifact_id": "gh-current"},
                "oauth1": {"artifact_id": "wiki-old"},
            },
        }],
        "degraded": [],
    }
    metrics = score_result(CASE, result, 1.0, 10.0)
    assert metrics["passed"] is True
    assert metrics["citation_precision"] == 1.0
    assert metrics["supporting_artifact_cited"] is True
    assert metrics["representatives_identified"] is True
    assert metrics["concise_source_appendix"] is True


def test_evaluation_rejects_unverified_citations():
    result = {
        "answer": "OAuth 2 with PKCE [github:invented](https://invented).",
        "ranked_hits": [], "contradictions": [], "degraded": [],
    }
    metrics = score_result(CASE, result, 1.0, 10.0)
    assert metrics["passed"] is False
    assert metrics["citation_precision"] == 0.0


def test_evaluation_recognizes_safe_degraded_response():
    result = {
        "answer": "The evidence was retrieved, but answer generation is temporarily unavailable.",
        "ranked_hits": [], "contradictions": [], "degraded": ["answer_generation:TimeoutError"],
    }
    metrics = score_result(CASE, result, 1.0, 10.0)
    assert metrics["safe_degradation"] is True
    assert metrics["passed"] is False
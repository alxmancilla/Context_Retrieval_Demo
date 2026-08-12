from datetime import UTC, datetime, timedelta

import pytest

from core.reconciliation import ReconciliationWeights, reconcile
from core.settings import configured_reconciliation_weights


def _hit(artifact: str, source: str, value: str, score: float, days: int) -> dict:
    return {
        "artifact_id": artifact, "source": source, "title": artifact,
        "content": "authentication protocol", "url": f"https://demo/{artifact}",
        "updated_at": datetime.now(UTC) - timedelta(days=days),
        "vector_score": score, "claims": {"auth": value},
    }


def test_reconcile_prefers_authoritative_fresh_source_and_surfaces_conflict():
    historical = _hit("teams-old", "teams", "oauth1", 0.95, 500)
    historical["governance"] = {
        "document_type": "incident_thread", "lifecycle_status": "historical",
    }
    results = {
        "github": [_hit("gh-current", "github", "oauth2", 0.9, 5)],
        "teams": [historical],
    }
    registry = {
        "github": {"authority": 1.0, "freshness_half_life_days": 365},
        "teams": {"authority": 0.35, "freshness_half_life_days": 60},
    }
    ranked, conflicts = reconcile(results, registry)
    assert ranked[0]["artifact_id"] == "gh-current"
    assert conflicts[0]["preferred_value"] == "oauth2"
    assert conflicts[0]["preferred_artifact"] == "gh-current"
    assert conflicts[0]["representatives"]["oauth1"]["artifact_id"] == "teams-old"
    assert conflicts[0]["representatives"]["oauth1"]["lifecycle_status"] == "historical"
    assert conflicts[0]["score_margin"] > 0


def test_no_contradiction_when_claim_values_agree():
    results = {
        "github": [_hit("gh", "github", "oauth2", 0.9, 1)],
        "jira": [_hit("jira", "jira", "oauth2", 0.8, 2)],
    }
    registry = {
        "github": {"authority": 1.0, "freshness_half_life_days": 365},
        "jira": {"authority": 0.78, "freshness_half_life_days": 270},
    }
    _, conflicts = reconcile(results, registry)
    assert conflicts == []


def test_reconcile_excludes_results_without_registry_policy():
    results = {"teams": [_hit("unknown-policy", "teams", "oauth1", 0.99, 1)]}
    ranked, conflicts = reconcile(results, {})
    assert ranked == []
    assert conflicts == []


def test_default_weights_preserve_the_truth_score_formula():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    row = _hit("gh", "github", "oauth2", 0.8, 100)
    row["updated_at"] = now - timedelta(days=100)
    ranked, _ = reconcile(
        {"github": [row]},
        {"github": {"authority": 0.6, "freshness_half_life_days": 100}},
        now,
    )
    assert ranked[0]["freshness"] == pytest.approx(0.5)
    assert ranked[0]["truth_score"] == pytest.approx(0.695)


def test_calibrated_weights_can_change_the_preferred_evidence():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    results = {
        "github": [_hit("authoritative", "github", "oauth2", 0.5, 0)],
        "teams": [_hit("semantic", "teams", "oauth1", 0.9, 0)],
    }
    registry = {
        "github": {"authority": 1.0, "freshness_half_life_days": 365},
        "teams": {"authority": 0.2, "freshness_half_life_days": 365},
    }
    semantic_ranked, _ = reconcile(
        results, registry, now, ReconciliationWeights(vector=0.9, authority=0.1, freshness=0)
    )
    authority_ranked, _ = reconcile(
        results, registry, now, ReconciliationWeights(vector=0.1, authority=0.9, freshness=0)
    )
    assert semantic_ranked[0]["artifact_id"] == "semantic"
    assert authority_ranked[0]["artifact_id"] == "authoritative"


def test_voyage_rerank_score_replaces_vector_similarity_component():
    results = {
        "github": [{**_hit("vector", "github", "oauth2", 0.95, 0), "rerank_score": 0.1}],
        "teams": [{**_hit("reranked", "teams", "oauth1", 0.2, 0), "rerank_score": 0.9}],
    }
    registry = {
        "github": {"authority": 1.0, "freshness_half_life_days": 365},
        "teams": {"authority": 0.2, "freshness_half_life_days": 365},
    }
    ranked, _ = reconcile(
        results, registry,
        weights=ReconciliationWeights(vector=1.0, authority=0, freshness=0),
    )
    assert ranked[0]["artifact_id"] == "reranked"
    assert ranked[0]["rerank_score"] == 0.9


def test_configured_weights_reject_an_invalid_total(monkeypatch):
    monkeypatch.setenv("RECONCILIATION_VECTOR_WEIGHT", "0.5")
    monkeypatch.setenv("RECONCILIATION_AUTHORITY_WEIGHT", "0.5")
    monkeypatch.setenv("RECONCILIATION_FRESHNESS_WEIGHT", "0.5")
    with pytest.raises(ValueError, match="sum to 1.0"):
        configured_reconciliation_weights()

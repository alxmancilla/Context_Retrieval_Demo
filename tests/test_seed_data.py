from collections import Counter
from datetime import UTC, datetime

from core.reconciliation import reconcile
from data.seed_data import all_artifacts


def test_seed_has_five_islands_and_planted_conflicts():
    rows = all_artifacts("test-realm")
    counts = Counter(row["source"] for row in rows)
    assert len(rows) == 800
    assert set(counts) == {"github", "confluence", "jira", "sharepoint", "teams"}
    assert set(counts.values()) == {160}
    themes = Counter(row["metadata"]["theme"] for row in rows)
    assert themes == {
        "rx_partner_auth": 200, "pa_status_delivery": 200,
        "eligibility_cache": 200, "phi_logging": 200,
    }
    claim_values = {
        claim: {row["claims"].get(claim) for row in rows}
        for claim in ("rx_auth_protocol", "pa_status_delivery",
                      "eligibility_cache_ttl", "phi_logging")
    }
    assert {"oauth1", "oauth2_pkce"} <= claim_values["rx_auth_protocol"]
    assert {"polling", "events"} <= claim_values["pa_status_delivery"]
    assert {"60_minutes", "5_minutes"} <= claim_values["eligibility_cache_ttl"]
    assert {"raw_payloads", "redacted"} <= claim_values["phi_logging"]
    assert all(row["realm_id"] == "test-realm" for row in rows)
    assert all("role:platform-engineer" in row["access_principals"] for row in rows)
    assert all(len(row["access_principals"]) == 2 for row in rows)
    assert len({row["artifact_id"] for row in rows}) == 800


def test_assurance_expansion_is_balanced_relevant_and_governed():
    rows = [
        row for row in all_artifacts("test-realm")
        if row["metadata"].get("corpus_phase") == "assurance-expansion"
    ]
    assert len(rows) == 160
    assert set(Counter(row["source"] for row in rows).values()) == {32}
    assert set(Counter(row["metadata"]["theme"] for row in rows).values()) == {40}
    assert all(row["metadata"]["assurance_dimension"] for row in rows)
    assert all(row["governance"]["document_type"] for row in rows)
    assert all(row["governance"]["lifecycle_status"] in {"active", "effective"} for row in rows)
    assert {row["governance"]["document_type"] for row in rows} >= {
        "policy", "implementation", "architecture", "runbook", "compliance", "validation",
    }


def test_seed_artifacts_have_required_source_routing_fields():
    for row in all_artifacts("test-realm"):
        assert row["artifact_id"]
        assert row["content"]
        assert row["url"].startswith("https://demo.cmm.local/")
        assert row["created_at"] < row["updated_at"]
        assert len(row["metadata"]["documentation_refs"]) >= 2


def test_seed_has_source_specific_metadata():
    required = {
        "github": {"repo", "branch", "path", "commit", "pull_request"},
        "confluence": {"space", "page_id", "hierarchy", "version", "owner"},
        "jira": {"project", "issue_key", "status", "status_category", "resolution"},
        "sharepoint": {"site", "library", "folder", "owner", "review_cadence"},
        "teams": {"team", "channel", "thread_id", "participants", "reply_count"},
    }
    for row in all_artifacts("test-realm"):
        assert required[row["source"]] <= row["metadata"].keys()


def test_reference_storylines_prefer_governed_current_evidence():
    rows = all_artifacts("test-realm")
    results = {source: [] for source in ("github", "confluence", "jira", "sharepoint", "teams")}
    for row in rows:
        results[row["source"]].append({**row, "vector_score": 0.9})
    registry = {
        "github": {"authority": 1.0, "freshness_half_life_days": 365},
        "sharepoint": {"authority": 0.85, "freshness_half_life_days": 365},
        "jira": {"authority": 0.78, "freshness_half_life_days": 270},
        "confluence": {"authority": 0.65, "freshness_half_life_days": 180},
        "teams": {"authority": 0.35, "freshness_half_life_days": 60},
    }
    _, conflicts = reconcile(results, registry, datetime(2026, 8, 12, tzinfo=UTC))
    preferred = {item["claim"]: item["preferred_artifact"] for item in conflicts}
    assert preferred == {
        "rx_auth_protocol": "github-rx-auth-implementation",
        "pa_status_delivery": "github-pa-status-events",
        "phi_logging": "sharepoint-phi-logging-policy",
        "eligibility_cache_ttl": "github-eligibility-cache",
    }

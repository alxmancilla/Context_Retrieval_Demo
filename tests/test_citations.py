from core.citations import bind_source_links


def _hit(artifact_id: str, source: str) -> dict:
    return {
        "artifact_id": artifact_id, "source": source,
        "url": f"https://demo/{artifact_id}", "title": artifact_id,
    }


def test_binder_links_both_sides_of_a_contradiction():
    hits = [_hit("gh-current", "github"), _hit("conf-old", "confluence")]
    conflicts = [{
        "preferred_artifact": "gh-current",
        "values": {"oauth2": ["gh-current"], "oauth1": ["conf-old"]},
    }]
    answer = "OAuth2 is current [github:gh-current]."
    bound = bind_source_links(answer, hits, conflicts)
    assert "[github:gh-current](https://demo/gh-current)" in bound
    assert "https://demo/conf-old" in bound


def test_binder_limits_contradiction_sources_to_representatives_and_citations():
    hits = [
        _hit("policy", "sharepoint"), _hit("implementation", "github"),
        _hit("supporting-1", "jira"), _hit("supporting-2", "confluence"),
        _hit("historical", "teams"),
    ]
    conflict = {
        "preferred_artifact": "policy",
        "values": {
            "redacted": ["policy", "implementation", "supporting-1", "supporting-2"],
            "raw": ["historical"],
        },
        "representatives": {
            "redacted": {"artifact_id": "policy"},
            "raw": {"artifact_id": "historical"},
        },
    }
    bound = bind_source_links("Current policy [sharepoint:policy].", hits, [conflict])
    assert "https://demo/policy" in bound
    assert "https://demo/historical" in bound
    assert "https://demo/supporting-1" not in bound
    assert "https://demo/supporting-2" not in bound


def test_binder_caps_appendix_while_preserving_contradiction_representatives():
    hits = [_hit(f"artifact-{index}", "github") for index in range(8)]
    conflict = {
        "preferred_artifact": "artifact-0",
        "representatives": {
            "current": {"artifact_id": "artifact-0"},
            "historical": {"artifact_id": "artifact-7"},
        },
    }
    answer = " ".join(f"[github:artifact-{index}]" for index in range(8))
    bound = bind_source_links(answer, hits, [conflict])
    appendix = bound.split("### Sources\n", maxsplit=1)[1]
    assert len(appendix.splitlines()) == 6
    assert "https://demo/artifact-0" in appendix
    assert "https://demo/artifact-7" in appendix


def test_binder_replaces_model_generated_sources_section():
    answer = "Answer [github:gh].\n\n### Sources\n- invented.example"
    bound = bind_source_links(answer, [_hit("gh", "github")], [])
    assert "invented.example" not in bound
    assert bound.count("### Sources") == 1


def test_binder_links_source_only_markers_to_top_ranked_source_hit():
    hits = [_hit("gh-current", "github"), _hit("jira-done", "jira")]
    bound = bind_source_links("Current behavior [GitHub]; rollout [jira].", hits, [])
    assert "[github:gh-current](https://demo/gh-current)" in bound
    assert "[jira:jira-done](https://demo/jira-done)" in bound
    assert "[GitHub]" not in bound


def test_binder_resolves_generic_source_with_verified_artifact_id():
    hits = [_hit("policy", "sharepoint")]
    bound = bind_source_links("Current policy [source:policy].", hits, [])
    assert "[sharepoint:policy](https://demo/policy)" in bound
    assert "[source:policy]" not in bound


def test_binder_does_not_double_link_existing_inline_citation():
    answer = "Current [github:gh](https://demo/gh)."
    bound = bind_source_links(answer, [_hit("gh", "github")], [])
    assert bound.count("[github:gh](https://demo/gh)") == 2


def test_binder_replaces_model_supplied_url_before_binding():
    answer = "Current [github:gh](javascript:alert(1)); old [source:old](https://evil.test)."
    hits = [_hit("gh", "github"), _hit("old", "teams")]
    bound = bind_source_links(answer, hits, [])
    assert "javascript:" not in bound
    assert "evil.test" not in bound
    assert "[github:gh](https://demo/gh)" in bound
    assert "[teams:old](https://demo/old)" in bound


def test_binder_links_literal_multiline_source_placeholders_in_rank_order():
    hits = [_hit("gh-current", "github"), _hit("conf-old", "confluence")]
    answer = "Current behavior. [source\n] [source]\n\nLegacy guidance. [Source 3\n]"
    bound = bind_source_links(answer, hits, [])
    assert "[source" not in bound.lower()
    assert bound.count("[github:gh-current](https://demo/gh-current)") >= 2
    assert bound.count("[confluence:conf-old](https://demo/conf-old)") >= 2

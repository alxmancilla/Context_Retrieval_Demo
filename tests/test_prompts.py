from datetime import UTC, datetime

from agent.prompts import answer_prompt, select_answer_evidence


def _hit(artifact_id: str) -> dict:
    return {
        "artifact_id": artifact_id, "source": "github", "title": artifact_id,
        "content": artifact_id, "url": f"https://demo/{artifact_id}",
        "updated_at": datetime.now(UTC), "truth_score": 1.0, "claims": {},
    }


def test_answer_evidence_includes_low_ranked_conflict_representative():
    hits = [_hit(f"current-{index}") for index in range(20)] + [_hit("historical")]
    conflicts = [{
        "preferred_artifact": "current-0",
        "representatives": {
            "current": {"artifact_id": "current-0"},
            "old": {"artifact_id": "historical"},
        },
    }]
    selected = select_answer_evidence(hits, conflicts, limit=15)
    selected_ids = [hit["artifact_id"] for hit in selected]
    assert len(selected_ids) == 15
    assert "current-0" in selected_ids
    assert "historical" in selected_ids
    assert "current-14" not in selected_ids


def test_answer_prompt_labels_recent_context_as_non_authoritative():
    prompt = answer_prompt(
        "follow up", [], [], [], [{"role": "human", "content": "prior turn"}],
    )
    assert "RECENT CONVERSATION (NON-AUTHORITATIVE)" in prompt
    assert "prior turn" in prompt
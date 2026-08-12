from core.schemas import merge_degraded, merge_source_results


def test_parallel_source_results_merge():
    assert merge_source_results({"github": [1]}, {"jira": [2]}) == {
        "github": [1], "jira": [2]
    }


def test_source_results_reset_between_turns():
    assert merge_source_results({"github": [1]}, {"__RESET__": []}) == {}


def test_degraded_reset_drops_previous_turn_markers():
    assert merge_degraded(["old"], ["__RESET__", "new"]) == ["new"]

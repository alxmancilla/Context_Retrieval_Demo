from evals.retrieval_runner import score_case
from scripts.load_retrieval import percentile


def test_assurance_retrieval_score_requires_theme_and_dimension():
    case = {"id": "key", "theme": "auth", "assurance_dimension": "rotation"}
    passing = [{"metadata": {"theme": "auth", "assurance_dimension": "rotation"}}]
    wrong_dimension = [{"metadata": {"theme": "auth", "assurance_dimension": "scope"}}]
    assert score_case(case, passing)["passed"] is True
    assert score_case(case, wrong_dimension)["passed"] is False


def test_load_percentile_is_deterministic_for_small_samples():
    assert percentile([], 0.95) == 0.0
    assert percentile([0.4, 0.1, 0.3, 0.2], 0.95) == 0.4
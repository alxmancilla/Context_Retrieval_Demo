from scripts.benchmark_modes import RETRIEVAL_MODES, ROUTING_MODES, benchmark_plan


def test_default_benchmark_plan_covers_routing_and_retrieval_ablations():
    plan = benchmark_plan(full_matrix=False)
    assert plan == [
        ("intent", "hybrid"),
        ("all", "hybrid"),
        ("explicit_only", "hybrid"),
        ("intent", "vector"),
        ("intent", "lexical"),
    ]


def test_full_benchmark_plan_covers_all_combinations():
    plan = benchmark_plan(full_matrix=True)
    assert len(plan) == len(ROUTING_MODES) * len(RETRIEVAL_MODES)
    assert ("all", "lexical") in plan
    assert ("explicit_only", "vector") in plan
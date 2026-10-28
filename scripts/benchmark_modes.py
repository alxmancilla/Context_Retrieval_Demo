import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROUTING_MODES = ("intent", "all", "explicit_only")
RETRIEVAL_MODES = ("hybrid", "vector", "lexical")


def benchmark_plan(full_matrix: bool) -> list[tuple[str, str]]:
    if full_matrix:
        return [(routing, retrieval) for routing in ROUTING_MODES for retrieval in RETRIEVAL_MODES]
    routing_ablations = [(mode, "hybrid") for mode in ROUTING_MODES]
    retrieval_ablations = [("intent", mode) for mode in RETRIEVAL_MODES if mode != "hybrid"]
    return routing_ablations + retrieval_ablations


def run_case(routing: str, retrieval: str, output_dir: Path, max_latency: float) -> dict:
    case_output = output_dir / f"rag-{routing}-{retrieval}.json"
    env = {
        **os.environ,
        "SOURCE_ROUTING_MODE": routing,
        "SOURCE_RETRIEVAL_MODE": retrieval,
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evals.runner",
            "--output",
            str(case_output),
            "--max-latency",
            str(max_latency),
        ],
        check=False,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    summary = json.loads(case_output.read_text()) if case_output.exists() else {}
    return {
        "source_routing_mode": routing,
        "source_retrieval_mode": retrieval,
        "returncode": completed.returncode,
        "total": summary.get("total", 0),
        "passed": summary.get("passed", 0),
        "pass_rate": summary.get("pass_rate", 0.0),
        "output": str(case_output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run metric-only RAG evals across routing/retrieval comparison modes."
    )
    parser.add_argument("--output", type=Path, default=Path("evals/results/mode-benchmark-latest.json"))
    parser.add_argument("--case-output-dir", type=Path, default=Path("evals/results/mode-benchmark"))
    parser.add_argument("--max-latency", type=float, default=45.0)
    parser.add_argument("--full-matrix", action="store_true")
    args = parser.parse_args()

    args.case_output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        run_case(routing, retrieval, args.case_output_dir, args.max_latency)
        for routing, retrieval in benchmark_plan(args.full_matrix)
    ]
    result = {"rows": rows, "total_runs": len(rows), "all_passed": all(row["returncode"] == 0 for row in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"total_runs": result["total_runs"], "all_passed": result["all_passed"], "output": str(args.output)}))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
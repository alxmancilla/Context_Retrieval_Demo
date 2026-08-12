import argparse
import json
import re
import time
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage

from agent.graph import build_graph
from agent.nodes import AgentNodes
from core.observability import configure_logging
from core.providers.chat import GroveChatProvider
from core.providers.rerank import create_voyage_reranker
from core.settings import get_settings
from db.bootstrap import connect

CITATION_PATTERN = re.compile(r"\[([a-z]+):([^\]]+)\]\(([^)]+)\)")
SAFE_FALLBACKS = (
    "I don't have enough retrieved enterprise context",
    "The evidence was retrieved, but answer generation is temporarily unavailable",
)


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def score_result(case: dict, result: dict, latency_seconds: float, max_latency: float) -> dict:
    answer = result.get("answer", "")
    answer_lower = answer.lower()
    ranked = result.get("ranked_hits", [])
    verified = {(hit["source"], hit["artifact_id"], hit["url"]) for hit in ranked}
    hits_by_artifact = {hit["artifact_id"]: hit for hit in ranked}
    citations = set(CITATION_PATTERN.findall(answer))
    sources_section = re.split(
        r"\n#{2,4}\s+Sources\s*\n", answer, maxsplit=1, flags=re.IGNORECASE
    )
    source_appendix_citations = (
        set(CITATION_PATTERN.findall(sources_section[1])) if len(sources_section) == 2 else set()
    )
    citation_precision = (
        len(citations & verified) / len(citations) if citations else 0.0
    )
    expected_citation = any(
        artifact_id == case["preferred_artifact"] for _, artifact_id, _ in citations
    )
    supporting_citation = any(
        hits_by_artifact.get(artifact_id, {}).get("claims", {}).get(case["claim"])
        == case["preferred_value"]
        for _, artifact_id, _ in citations
    )
    contradiction = next(
        (item for item in result.get("contradictions", []) if item["claim"] == case["claim"]),
        None,
    )
    stale_evidence = set()
    if contradiction:
        for artifacts in contradiction.get("values", {}).values():
            stale_evidence.update(artifacts)
    expected_representatives = case.get("representatives", {})
    representatives = contradiction.get("representatives", {}) if contradiction else {}
    representatives_identified = all(
        representatives.get(value, {}).get("artifact_id") == artifact_id
        for value, artifact_id in expected_representatives.items()
    )
    canonical_artifact_won = bool(
        contradiction and contradiction["preferred_artifact"] == case["preferred_artifact"]
    )
    concise_source_appendix = len(source_appendix_citations) <= case.get(
        "max_source_appendix_artifacts", 10_000
    )
    term_coverage = sum(
        any(term.lower() in answer_lower for term in group)
        for group in case["required_term_groups"]
    ) / len(case["required_term_groups"])
    degraded = result.get("degraded", [])
    safe_degradation = not degraded or (
        not citations and answer.startswith(SAFE_FALLBACKS)
    )
    metrics = {
        "case_id": case["id"],
        "latency_seconds": round(latency_seconds, 3),
        "within_latency_budget": latency_seconds <= max_latency,
        "term_coverage": term_coverage,
        "citation_precision": citation_precision,
        "source_appendix_artifacts": len(source_appendix_citations),
        "concise_source_appendix": concise_source_appendix,
        "preferred_artifact_cited": expected_citation,
        "supporting_artifact_cited": supporting_citation,
        "contradiction_value_resolved": bool(
            contradiction
            and contradiction["preferred_value"] == case["preferred_value"]
        ),
        "canonical_artifact_won": canonical_artifact_won,
        "representatives_identified": representatives_identified,
        "stale_evidence_identified": set(case["stale_artifacts"]) <= stale_evidence,
        "degraded_count": len(degraded),
        "safe_degradation": safe_degradation,
    }
    metrics["passed"] = bool(
        metrics["within_latency_budget"]
        and metrics["term_coverage"] == 1.0
        and metrics["citation_precision"] == 1.0
        and metrics["supporting_artifact_cited"]
        and metrics["contradiction_value_resolved"]
        and metrics["representatives_identified"]
        and metrics["stale_evidence_identified"]
        and metrics["concise_source_appendix"]
        and (
            not case.get("require_canonical_winner", False)
            or metrics["canonical_artifact_won"]
        )
        and metrics["degraded_count"] == 0
        and metrics["safe_degradation"]
    )
    return metrics


def run(cases_path: Path, output_path: Path, max_latency: float) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level)
    client, db = connect(
        settings.mongodb_uri, settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
    )
    evaluation_user = f"evaluation-{uuid4()}"
    try:
        chat = GroveChatProvider(
            api_key=settings.grove_api_key, base_url=settings.grove_base_url,
            model=settings.grove_model, timeout_seconds=settings.grove_timeout_seconds,
            max_retries=settings.grove_max_retries,
        )
        nodes = AgentNodes(
            db, chat, settings.source_top_k, settings.memory_top_k,
            settings.memory_retention_days, settings.memory_max_per_user,
            reconciliation_weights=settings.reconciliation_weights,
            reranker=create_voyage_reranker(
                api_key=settings.voyage_api_key,
                model=settings.voyage_rerank_model,
                timeout_seconds=settings.voyage_rerank_timeout_seconds,
                max_retries=settings.voyage_rerank_max_retries,
            ),
        )
        graph = build_graph(nodes)
        scores = []
        for case in load_cases(cases_path):
            started = time.monotonic()
            result = graph.invoke({
                "query": case["prompt"],
                "messages": [HumanMessage(content=case["prompt"])],
                "realm_id": settings.realm_id,
                "user_id": evaluation_user,
                "access_principals": list(settings.access_principals),
                "correlation_id": str(uuid4()),
            })
            scores.append(score_result(
                case, result, time.monotonic() - started, max_latency
            ))
        summary = {
            "cases": scores,
            "total": len(scores),
            "passed": sum(score["passed"] for score in scores),
            "pass_rate": sum(score["passed"] for score in scores) / len(scores),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2) + "\n")
        return summary
    finally:
        if "nodes" in locals():
            nodes.memory.delete_user(settings.realm_id, evaluation_user)
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic live RAG evaluations")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/results/latest.json"))
    parser.add_argument("--max-latency", type=float, default=45.0)
    args = parser.parse_args()
    summary = run(args.cases, args.output, args.max_latency)
    print(json.dumps({
        "total": summary["total"], "passed": summary["passed"],
        "pass_rate": summary["pass_rate"], "output": str(args.output),
    }))
    if summary["pass_rate"] < 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
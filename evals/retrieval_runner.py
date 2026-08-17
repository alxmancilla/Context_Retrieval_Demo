import json
from pathlib import Path

from core.schemas import ALL_SOURCES
from core.settings import get_settings
from core.source_agents import SourceAgent
from db.bootstrap import connect


def score_case(case: dict, hits: list[dict]) -> dict:
    matching = [
        hit for hit in hits
        if hit.get("metadata", {}).get("theme") == case["theme"]
    ]
    dimension_found = any(
        hit.get("metadata", {}).get("assurance_dimension")
        == case["assurance_dimension"]
        for hit in matching
    )
    return {
        "case_id": case["id"],
        "theme_hits": len(matching),
        "assurance_dimension_found": dimension_found,
        "passed": bool(matching and dimension_found),
    }


def run(cases_path: Path, output_path: Path) -> dict:
    settings = get_settings()
    client, db = connect(
        settings.mongodb_uri, settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
    )
    try:
        scores = []
        for case in json.loads(cases_path.read_text()):
            hits = [
                hit
                for source in ALL_SOURCES
                for hit in SourceAgent(db[source], source, settings.source_top_k).search(
                    case["query"], settings.realm_id, list(settings.access_principals)
                )
            ]
            scores.append(score_case(case, hits))
        result = {
            "cases": scores,
            "total": len(scores),
            "passed": sum(score["passed"] for score in scores),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        client.close()


def main() -> None:
    result = run(
        Path("evals/retrieval_cases.json"),
        Path("evals/results/retrieval-latest.json"),
    )
    print(json.dumps({"total": result["total"], "passed": result["passed"]}))
    if result["passed"] != result["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
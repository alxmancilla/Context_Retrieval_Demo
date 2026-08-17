import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.schemas import ALL_SOURCES, SourceName
from core.settings import get_settings
from core.source_agents import SourceAgent
from db.bootstrap import connect

QUERIES = (
    "current Rx partner authentication and key rotation controls",
    "prior authorization event dead-letter replay and idempotency",
    "eligibility cache invalidation and stale response prevention",
    "PHI break-glass logging and redacted troubleshooting",
)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded metric-only Atlas retrieval load smoke")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 20 or not 1 <= args.workers <= 20:
        raise SystemExit("rounds and workers must be between 1 and 20")

    settings = get_settings()
    client, db = connect(
        settings.mongodb_uri, settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
    )
    jobs: list[tuple[SourceName, str]] = [
        (source, QUERIES[round_index % len(QUERIES)])
        for round_index in range(args.rounds)
        for source in ALL_SOURCES
    ]

    def search(source: SourceName, query: str) -> tuple[float, int]:
        started = time.monotonic()
        hits = SourceAgent(db[source], source, settings.source_top_k).search(
            query, settings.realm_id, list(settings.access_principals)
        )
        return time.monotonic() - started, len(hits)

    latencies: list[float] = []
    hit_count = 0
    errors = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(search, source, query) for source, query in jobs]
            for future in as_completed(futures):
                try:
                    latency, hits = future.result()
                    latencies.append(latency)
                    hit_count += hits
                except Exception:
                    errors += 1
    finally:
        client.close()
    result = {
        "operations": len(jobs), "workers": args.workers, "errors": errors,
        "hits": hit_count,
        "mean_ms": round(statistics.fmean(latencies) * 1000, 2) if latencies else 0.0,
        "p95_ms": round(percentile(latencies, 0.95) * 1000, 2),
    }
    print(json.dumps(result))
    if errors or hit_count == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
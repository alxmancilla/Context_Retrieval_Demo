from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from math import exp, isclose, log

from core.schemas import Contradiction, ContradictionRepresentative, SourceHit


@dataclass(frozen=True)
class ReconciliationWeights:
    vector: float = 0.55
    authority: float = 0.30
    freshness: float = 0.15

    def __post_init__(self) -> None:
        values = (self.vector, self.authority, self.freshness)
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("Reconciliation weights must each be between 0 and 1")
        if not isclose(sum(values), 1.0, abs_tol=1e-9):
            raise ValueError("Reconciliation weights must sum to 1.0")


DEFAULT_RECONCILIATION_WEIGHTS = ReconciliationWeights()


def _freshness(updated_at: datetime, half_life_days: float, now: datetime) -> float:
    value = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    age_days = max((now - value).total_seconds() / 86400, 0)
    return exp(-log(2) * age_days / half_life_days)


def reconcile(
    results: dict[str, list[dict]], registry: dict[str, dict], now: datetime | None = None,
    weights: ReconciliationWeights = DEFAULT_RECONCILIATION_WEIGHTS,
) -> tuple[list[dict], list[dict]]:
    now = now or datetime.now(UTC)
    ranked: list[SourceHit] = []
    for source, rows in results.items():
        config = registry.get(source)
        if config is None:
            continue
        for row in rows:
            hit = SourceHit.model_validate(row)
            hit.authority = (
                hit.governance.authority_override
                if hit.governance.authority_override is not None
                else float(config["authority"])
            )
            hit.freshness = _freshness(
                hit.updated_at, float(config["freshness_half_life_days"]), now
            )
            semantic_score = (
                hit.rerank_score if hit.rerank_score is not None else hit.vector_score
            )
            hit.truth_score = round(
                weights.vector * semantic_score
                + weights.authority * hit.authority
                + weights.freshness * hit.freshness,
                6,
            )
            ranked.append(hit)
    ranked.sort(key=lambda hit: hit.truth_score, reverse=True)
    contradictions = detect_contradictions(ranked)
    return (
        [hit.model_dump() for hit in ranked],
        [conflict.model_dump() for conflict in contradictions],
    )


def detect_contradictions(hits: list[SourceHit]) -> list[Contradiction]:
    grouped: dict[str, dict[str, list[SourceHit]]] = defaultdict(lambda: defaultdict(list))
    for hit in hits:
        for claim, value in hit.claims.items():
            grouped[claim][str(value)].append(hit)
    conflicts: list[Contradiction] = []
    for claim, values in grouped.items():
        if len(values) < 2:
            continue
        representatives = {
            value: max(group, key=lambda hit: hit.truth_score)
            for value, group in values.items()
        }
        preferred_value, preferred = max(
            representatives.items(), key=lambda item: item[1].truth_score
        )
        competing_score = max(
            hit.truth_score for value, hit in representatives.items()
            if value != preferred_value
        )
        score_margin = round(preferred.truth_score - competing_score, 6)
        conflicts.append(
            Contradiction(
                claim=claim,
                values={value: [hit.artifact_id for hit in group] for value, group in values.items()},
                preferred_value=preferred_value,
                preferred_artifact=preferred.artifact_id,
                representatives={
                    value: ContradictionRepresentative(
                        artifact_id=hit.artifact_id,
                        source=hit.source,
                        truth_score=hit.truth_score,
                        updated_at=hit.updated_at,
                        lifecycle_status=hit.governance.lifecycle_status,
                        document_type=hit.governance.document_type,
                    )
                    for value, hit in representatives.items()
                },
                score_margin=score_margin,
                reason=(
                    f"{preferred.source} artifact {preferred.artifact_id} has the highest "
                    "combined semantic, artifact/source-authority, and freshness score; "
                    f"its margin over the best competing value is {score_margin:.3f}."
                ),
            )
        )
    return conflicts

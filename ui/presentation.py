import json

SOURCE_LABELS = {
    "github": "GitHub", "confluence": "Confluence", "jira": "Jira",
    "sharepoint": "SharePoint", "teams": "Teams",
}


def solution_architecture_markdown() -> str:
    return """
## Solution architecture

```mermaid
flowchart LR
    U[User] --> UI[Chainlit UI]
    UI --> AUTH[Fail-closed identity\nrealm + user + principals]
    AUTH --> LG[LangGraph coordinator]
    LG --> INT[Source routing\nintent | all | explicit]
    INT --> MEM[Recent context +\ngoverned memory]
    INT --> SRC[Parallel retrieval tools\nsource-scoped, evidence only]
    SRC --> HS[Atlas hybrid search\nvector + lexical + ACL + $rankFusion]
    HS --> RR[Voyage rerank-3\nglobal candidate ordering]
    RR --> REC[Deterministic reconciliation\nauthority + freshness + claims]
    REC --> GEN[Single chat provider writer\nGrove or OpenAI]
    GEN --> CIT[Verified citation binding]
    CIT --> TRACE[Pipeline trace +\nfinal cited answer]
    TRACE --> UI
    MEM --> GEN
    LG --> CKPT[(MongoDB checkpoints)]
    MEM --> M[(MongoDB memory nodes)]
    HS --> A[(Atlas source artifacts,\ngovernance, and claims)]
```

### Implementation map

- **State:** LangGraph checkpoints store execution state and recent turns.
- **Memory:** governed memory nodes store only selected preferences, decisions, and task context.
- **Routing:** `intent`, `all`, and `explicit_only` modes make source-selection tradeoffs measurable.
- **Retrieval:** source-specific tools run ACL-filtered Atlas Vector Search + lexical Search, fused with `$rankFusion` before reranking.
- **Generation:** retrieval tools return evidence only; the final answer is generated once after reconciliation.
- **Truth:** protected governance and indexed claims drive authority, lifecycle, and contradictions.
- **Trace:** the main answer shows source routing, parallel retrieval, reranking, and reconciliation before the final cited answer.
- **Security:** missing identity scope fails closed; retrieval filters apply before ranking.
- **Operations:** `/ready` verifies MongoDB, all 11 indexes, pool counters, memory metrics, and versions.
""".strip()


def intent_markdown(intent: dict) -> str:
    sources = ", ".join(SOURCE_LABELS.get(item, item) for item in intent.get("sources", []))
    entities = json.dumps(intent.get("entities", {}), indent=2)
    return (
        f"**Intent:** `{intent.get('intent', 'unknown')}`\n\n"
        f"**Search:** {intent.get('rewritten_query', '')}\n\n"
        f"**Routed to:** {sources}\n\n**Entities:**\n```json\n{entities}\n```"
    )


def source_result_markdown(source: str, hits: list[dict]) -> str:
    label = SOURCE_LABELS.get(source, source.title())
    if not hits:
        return f"{label} returned no artifacts."
    lines = [f"{label} returned **{len(hits)}** artifacts:"]
    lines.extend(
        f"- [{hit['title']}]({hit['url']}) — similarity `{hit['vector_score']:.3f}`"
        for hit in hits[:5]
    )
    return "\n".join(lines)


def evidence_markdown(hits: list[dict]) -> str:
    if not hits:
        return "No enterprise evidence was retrieved."
    rows = [
        "| # | Source | Artifact | Vector | Rerank | Authority | Freshness | Truth |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for rank, hit in enumerate(hits[:15], 1):
        title = str(hit["title"]).replace("|", "\\|")
        rerank = hit.get("rerank_score")
        rerank_display = f"{rerank:.3f}" if rerank is not None else "—"
        rows.append(
            f"| {rank} | {SOURCE_LABELS.get(hit['source'], hit['source'])} | "
            f"[{title}]({hit['url']}) | {hit['vector_score']:.3f} | "
            f"{rerank_display} | {hit['authority']:.2f} | {hit['freshness']:.2f} | "
            f"**{hit['truth_score']:.3f}** |"
        )
    rows.append(
        "\nTruth = 55% semantic relevance + 30% authority + 15% freshness. "
        "Semantic relevance uses Voyage reranking when available and Atlas vector "
        "similarity as fallback."
    )
    return "\n".join(rows)


def pipeline_trace_markdown(
    intent: dict, source_results: dict[str, list[dict]], ranked_hits: list[dict],
    contradictions: list[dict], degraded: list[str], *, rerank_model: str,
    routing_mode: str = "intent",
) -> str:
    """Customer-facing trace from routing through reranking."""
    selected = intent.get("sources") or sorted(source_results)
    routed = ", ".join(SOURCE_LABELS.get(source, source) for source in selected) or "none"
    source_counts = {
        SOURCE_LABELS.get(source, source.title()): len(hits)
        for source, hits in sorted(source_results.items())
    }
    retrieved = sum(source_counts.values())
    reranked = sum(1 for hit in ranked_hits if hit.get("rerank_score") is not None)
    rows = [
        "## Pipeline trace",
        "This shows how the assistant merged **evidence, not answers**, before writing the final response.",
        "",
        "| Stage | What happened |",
        "|---|---|",
        f"| 1. Source routing | Mode `{routing_mode}` selected **{routed}** for intent `{intent.get('intent', 'unknown')}`. |",
        f"| 2. Parallel retrieval | Retrieved **{retrieved}** authorized candidate(s) across **{len(source_counts)}** source(s). |",
        f"| 3. Reranking | Voyage `{rerank_model}` reranked **{reranked}** candidate(s); Atlas vector score remains fallback. |",
        f"| 4. Reconciliation | Ranked **{len(ranked_hits)}** evidence item(s) and found **{len(contradictions)}** contradiction group(s). |",
    ]
    if source_counts:
        rows.extend(["", "**Retrieved by source:**"])
        rows.append(", ".join(f"{source}: `{count}`" for source, count in source_counts.items()))
    if ranked_hits:
        rows.extend([
            "",
            "**Top reranked evidence:**",
            "| # | Source | Artifact | Rerank | Truth |",
            "|---:|---|---|---:|---:|",
        ])
        for rank, hit in enumerate(ranked_hits[:5], 1):
            title = str(hit.get("title", "Untitled")).replace("|", "\\|")
            source = str(hit.get("source", "unknown"))
            rerank = hit.get("rerank_score")
            rerank_display = f"{rerank:.3f}" if rerank is not None else "—"
            rows.append(
                f"| {rank} | {SOURCE_LABELS.get(source, source)} | "
                f"[{title}]({hit.get('url', '#')}) | {rerank_display} | "
                f"{float(hit.get('truth_score', 0.0)):.3f} |"
            )
    if degraded:
        rows.extend(["", f"**Degraded markers:** `{', '.join(degraded)}`"])
    return "\n".join(rows)


def retrieval_pipeline_markdown(
    source_results: dict[str, list[dict]], ranked_hits: list[dict],
    contradictions: list[dict], degraded: list[str], *, rerank_model: str,
    embedding_profile: str, source_top_k: int, retrieval_mode: str = "hybrid",
    routing_mode: str = "intent",
) -> str:
    source_counts = {
        SOURCE_LABELS.get(source, source.title()): len(hits)
        for source, hits in sorted(source_results.items())
    }
    retrieved = sum(source_counts.values())
    reranked = sum(1 for hit in ranked_hits if hit.get("rerank_score") is not None)
    hybrid = sum(
        1 for hits in source_results.values() for hit in hits
        if hit.get("metadata", {}).get("retrieval_reason") == "hybrid_rank_fusion"
    )
    fallback = sum(
        1 for hits in source_results.values() for hit in hits
        if hit.get("metadata", {}).get("retrieval_reason")
        == "vector_only_lexical_index_unavailable"
    )
    rows = [
        "## Retrieval pipeline",
        "| Stage | What happened |",
        "|---|---|",
        f"| Automated Embedding | Atlas `autoEmbed` profile `{embedding_profile}` indexes source `content`; documents do not carry visible embedding arrays. |",
        f"| Source routing mode | `{routing_mode}`. Use `intent` for LLM routing, `all` for all-source ablations, or `explicit_only` for rules-based comparisons. |",
        f"| Retrieval mode | `{retrieval_mode}`. Use `hybrid` for the production-style path, or `vector` / `lexical` for demo comparisons. |",
        f"| Candidate generation | Atlas Vector Search + lexical Search + ACL filters + `$rankFusion` when hybrid is enabled; target top-k per source is `{source_top_k}`. |",
        f"| Source fan-out | Retrieved `{retrieved}` authorized candidate(s) across `{len(source_counts)}` source(s). |",
        f"| Reranking | Voyage `{rerank_model}` scored `{reranked}` candidate(s); Atlas vector score remains the fallback. |",
        f"| Reconciliation | Ranked `{len(ranked_hits)}` evidence item(s) and found `{len(contradictions)}` contradiction group(s). |",
    ]
    if source_counts:
        rows.extend(["", "### Source counts"])
        rows.extend(f"- **{source}:** {count}" for source, count in source_counts.items())
    rows.extend([
        "",
        "### Retrieval signals",
        f"- Hybrid `$rankFusion` hits: `{hybrid}`",
        f"- Vector-only fallback hits: `{fallback}`",
        f"- Degraded markers: `{', '.join(degraded) if degraded else 'none'}`",
    ])
    return "\n".join(rows)


def contradictions_markdown(conflicts: list[dict]) -> str:
    if not conflicts:
        return "No normalized claim contradictions were detected in retrieved evidence."
    sections = []
    for conflict in conflicts:
        representatives = conflict.get("representatives", {})
        if representatives:
            values = "\n".join(
                f"- `{value}` ({len(artifacts)} artifact(s)): representative "
                f"`{representatives[value]['artifact_id']}` — "
                f"{representatives[value]['document_type']}, "
                f"{representatives[value]['lifecycle_status']}, updated "
                f"{str(representatives[value]['updated_at'])[:10]}, truth "
                f"`{representatives[value]['truth_score']:.3f}`"
                for value, artifacts in conflict["values"].items()
            )
        else:
            values = "\n".join(
                f"- `{value}`: {', '.join(artifacts)}"
                for value, artifacts in conflict["values"].items()
            )
        margin = conflict.get("score_margin")
        margin_text = f"\n\n**Cross-value margin:** `{margin:.3f}`" if margin is not None else ""
        sections.append(
            f"### `{conflict['claim']}`\n\n{values}\n\n"
            f"**Preferred:** `{conflict['preferred_value']}` from "
            f"`{conflict['preferred_artifact']}`{margin_text}\n\n{conflict['reason']}"
        )
    return "\n\n---\n\n".join(sections)


def memories_markdown(memories: list[dict]) -> str:
    if not memories:
        return "No relevant long-term memory was used for this turn."
    sections = ["Memory is user-scoped conversational context, not factual authority."]
    for index, memory in enumerate(memories[:3], 1):
        content = str(memory.get("summary") or memory.get("content", ""))[:900]
        memory_type = memory.get("memory_type", "legacy_context")
        importance = float(memory.get("importance", 0.0))
        sections.append(
            f"### Memory {index}: {memory_type} ({importance:.2f})\n\n{content}"
        )
    return "\n\n".join(sections)

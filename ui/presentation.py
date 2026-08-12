import json

SOURCE_LABELS = {
    "github": "GitHub", "confluence": "Confluence", "jira": "Jira",
    "sharepoint": "SharePoint", "teams": "Teams",
}


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
        content = str(memory.get("content", ""))[:900]
        sections.append(f"### Memory {index}\n\n{content}")
    return "\n\n".join(sections)
